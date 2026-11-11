"""
mcp — Serveur MCP (Model Context Protocol) de Fintrack, en LECTURE SEULE.

Permet d'interroger ses données depuis un client MCP (Claude Code, Claude
Desktop / claude.ai, opencode…) via le transport « Streamable HTTP ».

Authentification : serveur de ressources OAuth 2.1 (spécification MCP).
  • Le serveur d'autorisation est Supabase Auth (serveur OAuth 2.1, PKCE,
    enregistrement dynamique des clients). La page de consentement est
    servie par web (/oauth/consent).
  • Ce service publie les métadonnées RFC 9728
    (/.well-known/oauth-protected-resource/mcp) et répond 401 +
    WWW-Authenticate aux appels sans jeton : le client découvre seul où
    s'authentifier.
  • Chaque jeton est vérifié LOCALEMENT (JWKS : signature, expiration,
    émetteur, audience, rôle) et doit porter un `client_id` OAuth : un jeton
    de session web ou desktop n'est pas accepté ici.
  • Il est ensuite retransmis tel quel à finance-api : la RLS PostgreSQL
    s'applique (l'utilisateur ne voit que ses lignes) et la migration
    supabase/migration_mcp_readonly.sql interdit toute écriture à un jeton
    OAuth — lecture seule garantie par la base, pas seulement par ce code.

Sans état (stateless_http, réponses JSON) : réplicable sans affinité de
session. Ne touche jamais la base directement.
"""
from __future__ import annotations

import logging
from typing import Annotated, Any, Literal, Optional
from urllib.parse import urlsplit

import anyio.to_thread
import httpx
from fastapi import HTTPException
from mcp.server.auth.middleware.auth_context import get_access_token
from mcp.server.auth.provider import AccessToken
from mcp.server.auth.settings import AuthSettings
from mcp.server.mcpserver import MCPServer
from mcp.server.mcpserver.exceptions import ToolError
from mcp.server.transport_security import TransportSecuritySettings
from mcp.types import ToolAnnotations
from pydantic import Field
from starlette.applications import Starlette
from starlette.requests import Request
from starlette.responses import JSONResponse

from fintrack_common.auth import TokenVerifier
from fintrack_common.config import VERSION, ConfigError, env, env_bool
from fintrack_common.http import RequestContextMiddleware
from fintrack_common.logs import request_id_var, setup_logging

setup_logging("mcp")
# Pas le logger « mcp » : c'est l'espace de noms du SDK (limité à WARNING plus bas).
log = logging.getLogger("fintrack.mcp")

Year = Annotated[Optional[int], Field(ge=2000, le=2100, description="Année (ex. 2026). Omis : dernier mois saisi.")]
Month = Annotated[Optional[int], Field(ge=1, le=12, description="Mois 1-12. Omis : dernier mois saisi.")]
READ_ONLY = ToolAnnotations(read_only_hint=True, destructive_hint=False, idempotent_hint=True,
                            open_world_hint=False)

INSTRUCTIONS = (
    "Fintrack : finances personnelles d'un foyer français (montants en euros). "
    "Accès en lecture seule aux données de l'utilisateur connecté.\n"
    "- Données mensuelles : revenus, dépenses (par catégorie et enseigne), épargne "
    "(versements). Solde du mois = revenus - dépenses - épargne.\n"
    "- Un mois sans aucune saisie n'est PAS un mois à 0 € : ne le compte pas dans "
    "une moyenne et ne conclus pas à une baisse.\n"
    "- Le mois calendaire en cours est en général incomplet.\n"
    "- Patrimoine : valeur actuelle de chaque actif (dernier instantané mensuel) et "
    "capital restant dû des passifs ; patrimoine net = actifs - passifs.\n"
    "- Pour une question générale, commence par get_financial_context ; pour un "
    "mois précis, get_month_summary ; pour retrouver une opération, search_entries.\n"
    "- Sans année/mois, les outils prennent le dernier mois contenant des saisies.\n"
    "- Cite toujours la période concernée et n'invente aucun chiffre."
)


# ── Authentification ─────────────────────────────────────────

class AuthUnavailable(Exception):
    """Clés publiques (JWKS) injoignables : ce n'est PAS un jeton invalide."""


class AuthUnavailableMiddleware:
    """Panne JWKS -> 503 + Retry-After. Un 401 ferait croire au client MCP que
    son jeton est invalide : il l'abandonnerait et relancerait tout le
    parcours OAuth (consentement compris) pour chaque utilisateur."""

    def __init__(self, app):
        self.app = app

    async def __call__(self, scope, receive, send):
        try:
            await self.app(scope, receive, send)
        except AuthUnavailable:
            if scope["type"] != "http":
                raise
            await JSONResponse({"error": "temporarily_unavailable",
                                "error_description": "Vérification d'identité momentanément "
                                                     "indisponible, réessayez."},
                               status_code=503, headers={"Retry-After": "5"})(scope, receive, send)


class SupabaseTokenVerifier:
    """Adaptateur entre le vérificateur commun (synchrone, JWKS) et le
    protocole `TokenVerifier` du SDK MCP."""

    def __init__(self, verifier: TokenVerifier, *, require_oauth_client: bool = True):
        self.verifier = verifier
        self.require_oauth_client = require_oauth_client

    async def verify_token(self, token: str) -> AccessToken | None:
        try:
            # Récupération JWKS bloquante (mise en cache) : hors de la boucle.
            user = await anyio.to_thread.run_sync(self.verifier.verify, token)
        except HTTPException as exc:
            if exc.status_code == 503:          # JWKS injoignable (journalisé par le vérificateur)
                raise AuthUnavailable() from exc
            log.info("Jeton MCP refusé (HTTP %s)", exc.status_code)
            return None
        if self.require_oauth_client and not user.client_id:
            log.info("Jeton MCP refusé : pas de client OAuth (jeton de session)")
            return None
        return AccessToken(token=token, client_id=user.client_id or "session",
                           scopes=[], expires_at=user.expires_at, subject=user.id)


# ── Accès à finance-api ──────────────────────────────────────

def _strip_internal(data: Any) -> Any:
    """Retire les champs techniques sans intérêt pour le modèle."""
    if isinstance(data, list):
        return [_strip_internal(x) for x in data]
    if isinstance(data, dict):
        return {k: _strip_internal(v) for k, v in data.items() if k != "user_id"}
    return data


class Finance:
    def __init__(self, http: httpx.AsyncClient):
        self.http = http

    async def get(self, path: str, **params: Any) -> Any:
        token = get_access_token()
        if token is None:                    # garde-fou : le middleware l'impose déjà
            raise ToolError("Authentification requise.")
        try:
            r = await self.http.get(
                path, params={k: v for k, v in params.items() if v is not None},
                headers={"Authorization": f"Bearer {token.token}",
                         "X-Request-ID": request_id_var.get()})
        except httpx.HTTPError as exc:
            log.warning("finance-api injoignable : %s", exc.__class__.__name__)
            raise ToolError("Service de données momentanément indisponible.") from exc
        if r.status_code == 401:
            raise ToolError("Session expirée : reconnectez le serveur MCP.")
        if r.status_code >= 400:
            try:
                detail = r.json().get("detail")
            except ValueError:
                detail = None
            raise ToolError(detail if isinstance(detail, str) else "Données indisponibles.")
        return _strip_internal(r.json())

    async def period(self, year: Optional[int], month: Optional[int]) -> tuple[int, int]:
        if year is not None and month is not None:
            return year, month
        if year is not None or month is not None:
            raise ToolError("Indiquez l'année ET le mois, ou aucun des deux.")
        last = await self.get("/v1/last-month")
        if not last:
            raise ToolError("Aucune saisie : précisez l'année et le mois.")
        return last["year"], last["month"]


# ── Outils (lecture seule) ───────────────────────────────────

def register_tools(server: MCPServer, fin: Finance, *, expose_details: bool) -> None:
    def tool(title: str):
        return server.tool(title=title, annotations=READ_ONLY)

    @tool("Contexte financier")
    async def get_financial_context(
        year: Year = None, month: Month = None,
        months: Annotated[int, Field(ge=1, le=12, description="Nombre de mois saisis à résumer")] = 3,
    ) -> dict:
        """Résumé agrégé des derniers mois saisis jusqu'au mois indiqué : totaux et
        solde par mois, moyennes mensuelles (mois complets uniquement), top
        catégories / postes / enseignes, sources de revenus, épargne par compte,
        budgets, patrimoine par type et dépenses inhabituelles. Point de départ
        recommandé pour une question générale."""
        y, m = await fin.period(year, month)
        return await fin.get("/v1/ai-context", year=y, month=m, months=months)

    @tool("Bilan d'un mois")
    async def get_month_summary(year: Year = None, month: Month = None) -> dict:
        """Bilan d'un mois : revenus, dépenses, épargne, solde, dépenses par
        catégorie, état des budgets (pct = part consommée), mois clôturé ou non."""
        y, m = await fin.period(year, month)
        return await fin.get(f"/v1/months/{y}/{m}/summary")

    @tool("Historique mensuel")
    async def get_history(
        months: Annotated[int, Field(ge=1, le=60, description="Nombre de mois")] = 12,
    ) -> list[dict]:
        """Totaux revenus (rev), dépenses (exp) et épargne (sav) des derniers mois
        existants, du plus ancien au plus récent."""
        return await fin.get("/v1/history", limit=months)

    @tool("Analyses et tendances")
    async def get_analytics(
        year: Year = None, month: Month = None,
        months: Annotated[int, Field(ge=1, le=24, description="Profondeur des séries")] = 12,
    ) -> dict:
        """Tendances par catégorie (mois courant, mois précédent, même mois l'an
        dernier, moyenne des 6 mois précédents ayant des données), séries
        mensuelles, catégories inhabituelles et grosses dépenses isolées."""
        y, m = await fin.period(year, month)
        return await fin.get("/v1/analytics", year=y, month=m, months=months)

    @tool("Patrimoine")
    async def get_net_worth() -> dict:
        """Patrimoine actuel : actifs (valeur, montant investi, par type), passifs
        (capital restant dû, mensualité, échéance), totaux et patrimoine net."""
        return await fin.get("/v1/patrimoine")

    @tool("Vue d'ensemble de l'épargne")
    async def get_savings_overview(
        year: Year = None, month: Month = None,
        months: Annotated[int, Field(ge=1, le=24)] = 12,
    ) -> dict:
        """Épargne sur la période : versements et taux d'épargne par mois, total,
        moyenne, répartition par compte, soldes des comptes, objectifs d'épargne."""
        y, m = await fin.period(year, month)
        return await fin.get("/v1/savings-overview", year=y, month=m, months=months)

    @tool("Catégories de dépenses")
    async def list_categories() -> list[dict]:
        """Catégories de dépenses de l'utilisateur (id et nom). L'id sert de
        filtre à search_entries."""
        return await fin.get("/v1/categories")

    @tool("Transactions récurrentes")
    async def get_recurring(year: Year = None, month: Month = None) -> dict:
        """Dépenses et revenus récurrents (abonnements, loyer, salaire…) avec
        leur statut pour le mois : pending = pas encore appliquée ce mois-ci."""
        y, m = await fin.period(year, month)
        return await fin.get("/v1/recurring", year=y, month=m)

    if not expose_details:
        return

    # ── Détail des opérations (désactivable : MCP_EXPOSE_DETAILS=false) ──

    @tool("Opérations d'un mois")
    async def get_month_entries(
        year: Year = None, month: Month = None,
        kind: Literal["all", "expenses", "revenues", "savings"] = "all",
    ) -> dict:
        """Liste détaillée des opérations d'un mois (libellé, enseigne,
        catégorie, montant)."""
        y, m = await fin.period(year, month)
        data = await fin.get(f"/v1/months/{y}/{m}/entries")
        if kind != "all":
            data = {"closed": data.get("closed"), kind: data.get(kind, [])}
        return {"year": y, "month": m, **data}

    @tool("Recherche d'opérations")
    async def search_entries(
        kind: Literal["expenses", "revenues", "savings"] = "expenses",
        query: Annotated[str, Field(max_length=80, description="Texte cherché dans le libellé, "
                                                               "l'enseigne, la source ou le compte")] = "",
        category_id: Annotated[Optional[int], Field(description="Filtre catégorie (dépenses)")] = None,
        min_amount: Annotated[Optional[float], Field(ge=0, le=1e9)] = None,
        max_amount: Annotated[Optional[float], Field(ge=0, le=1e9)] = None,
        limit: Annotated[int, Field(ge=1, le=200)] = 50,
    ) -> dict:
        """Recherche dans tout l'historique, des plus récentes aux plus anciennes
        (chaque résultat indique son année et son mois). `truncated` = true :
        la liste n'est PAS complète, ne pas en tirer de total."""
        # Une ligne de plus que demandé : seul moyen de savoir s'il en reste.
        rows = await fin.get(f"/v1/search/{kind}", q=query, category_id=category_id,
                             min_amount=min_amount, max_amount=max_amount, limit=limit + 1)
        truncated = len(rows) > limit
        return {"returned": min(len(rows), limit), "truncated": truncated,
                "note": ("Liste incomplète : d'autres opérations correspondent. Affinez la "
                         "recherche (montants, catégorie) ; pour un total, utilisez "
                         "get_analytics ou get_month_summary.") if truncated else "",
                "results": rows[:limit]}

    @tool("Enseignes")
    async def list_payees() -> list[str]:
        """Enseignes (commerçants) des dépenses, des plus fréquentes aux moins
        fréquentes."""
        return await fin.get("/v1/payees")


# ── Application ──────────────────────────────────────────────

def _public_url(raw: str) -> str:
    p = urlsplit(raw)
    local = p.hostname in ("localhost", "127.0.0.1")
    if p.scheme != "https" and not (p.scheme == "http" and local):
        raise ConfigError("MCP_PUBLIC_URL doit être en https:// (http accepté pour localhost).")
    if not p.netloc or p.query or p.fragment or not p.path.startswith("/") or p.path == "/":
        raise ConfigError("MCP_PUBLIC_URL attendu : https://<hôte>/mcp")
    return raw.rstrip("/")


def create_app(*, verifier: Optional[TokenVerifier] = None,
               finance_http: Optional[httpx.AsyncClient] = None) -> Starlette:
    supabase_url = env("SUPABASE_URL", required=True).rstrip("/")
    public_url = _public_url(env("MCP_PUBLIC_URL", required=True))
    expose_details = env_bool("MCP_EXPOSE_DETAILS", True)
    require_client = env_bool("MCP_REQUIRE_OAUTH_CLIENT", True)
    pub = urlsplit(public_url)
    extra_hosts = [h.strip() for h in env("MCP_EXTRA_ALLOWED_HOSTS", "").split(",") if h.strip()]

    server = MCPServer(
        name="fintrack", title="Fintrack", version=VERSION, instructions=INSTRUCTIONS,
        token_verifier=SupabaseTokenVerifier(verifier or TokenVerifier(supabase_url),
                                             require_oauth_client=require_client),
        auth=AuthSettings(
            issuer_url=f"{supabase_url}/auth/v1",
            resource_server_url=public_url,
            # L'audience Supabase est « authenticated » (pas l'URL de ce
            # serveur) : le vérificateur commun la contrôle lui-même.
            validate_token_resource=False,
        ),
    )
    finance = finance_http or httpx.AsyncClient(
        base_url=env("FINANCE_API_URL", required=True).rstrip("/"),
        timeout=httpx.Timeout(15.0, connect=3.0), follow_redirects=False,
        headers={"User-Agent": f"fintrack-mcp/{VERSION}"})
    register_tools(server, Finance(finance), expose_details=expose_details)

    @server.custom_route("/healthz", methods=["GET"], include_in_schema=False)
    async def healthz(_: Request):
        return JSONResponse({"status": "ok", "version": VERSION})

    @server.custom_route("/readyz", methods=["GET"], include_in_schema=False)
    async def readyz(_: Request):
        return JSONResponse({"status": "ok"})

    app = server.streamable_http_app(
        streamable_http_path=pub.path,
        stateless_http=True,           # aucune session serveur : réplicable (HPA)
        json_response=True,            # pas de flux SSE à maintenir derrière l'Ingress
        max_request_body_size=256 * 1024,
        # Anti DNS-rebinding : seul l'hôte public est accepté ; les clients
        # MCP natifs n'envoient pas d'Origin, un navigateur tiers est refusé.
        transport_security=TransportSecuritySettings(
            enable_dns_rebinding_protection=True,
            allowed_hosts=[pub.netloc, *extra_hosts],
            allowed_origins=[f"{pub.scheme}://{pub.netloc}"]),
    )
    app.add_middleware(AuthUnavailableMiddleware)     # sous le middleware de requêtes (logs)
    app.add_middleware(RequestContextMiddleware)
    logging.getLogger("mcp").setLevel(logging.WARNING)      # pas d'arguments d'outils dans les logs
    log.info("MCP prêt : %s (détail des opérations %s)", public_url,
             "exposé" if expose_details else "masqué")
    return app


app = create_app() if not env("FINTRACK_NO_AUTOAPP") else None
