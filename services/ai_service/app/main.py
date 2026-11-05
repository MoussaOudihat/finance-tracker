"""
ai-service — Analyses et assistant IA (Claude, Gemini).

Sans état, réplicable. Ne lit JAMAIS la base : il demande à finance-api un
contexte AGRÉGÉ (totaux mensuels, top catégories/postes, budgets,
patrimoine par type) avec le jeton de l'utilisateur, puis interroge le
fournisseur choisi. Quota quotidien par utilisateur (coûts maîtrisés).
"""
from __future__ import annotations

import datetime as dt
import json
from typing import Annotated, Literal, Optional

import httpx
from fastapi import Depends, FastAPI, HTTPException
from pydantic import BaseModel, Field

from fintrack_common.auth import TokenVerifier, User, user_dependency
from fintrack_common.config import VERSION, env, env_int
from fintrack_common.http import RequestContextMiddleware, add_health_routes, service_client
from fintrack_common.logs import setup_logging
from fintrack_common.ratelimit import Counter, redis_from_url

from .providers import ProviderConfig, ProviderError, Providers

log = setup_logging("ai-service")

Provider = Literal["claude", "gemini"]
Year = Annotated[int, Field(ge=2000, le=2100)]
Month = Annotated[int, Field(ge=1, le=12)]

SYSTEM_ADVISOR = (
    "Tu es un conseiller en finances personnelles pour un foyer français. "
    "Tu reçois un résumé AGRÉGÉ en JSON (montants en euros) : totaux par mois "
    "(rev = revenus, exp = dépenses, sav = épargne), principales catégories, "
    "postes et enseignes de dépense en moyenne par mois, sources de revenus, "
    "budgets du mois en cours (pct = part consommée) et patrimoine par type. "
    "Réponds en français, de façon concrète et chiffrée, en citant les postes "
    "réels du résumé. N'invente aucun chiffre absent du résumé ; si une "
    "information manque, dis-le. Pas de conseil d'investissement sur un titre "
    "précis. Mise en forme : paragraphes courts et listes à puces (« - »), "
    "gras avec **…** avec parcimonie, pas de tableau ni de titre."
)

INSIGHTS_PROMPT = (
    "Voici mon résumé financier :\n{context}\n\n"
    "Fais le point sur la période : 1) ce qui va bien, 2) les 3 postes où "
    "agir en priorité avec l'économie mensuelle réaliste estimée, 3) l'état "
    "des budgets du mois et 4) une action concrète pour le mois prochain."
)

SYSTEM_CATEGORIZER = (
    "Tu classes une dépense d'un foyer français dans UNE catégorie de la liste "
    "fournie, d'après son libellé et son enseigne. Choisis la plus spécifique ; "
    "en cas de doute réel, choisis « AUTRES » si elle existe."
)


class InsightsIn(BaseModel):
    provider: Provider = "claude"
    year: Year
    month: Month
    months: Annotated[int, Field(ge=1, le=12)] = 3


class ChatMessage(BaseModel):
    role: Literal["user", "assistant"]
    # Les réponses de l'assistant, renvoyées en historique, dépassent souvent
    # 2000 caractères ; la question utilisateur est bornée côté web (2000).
    content: Annotated[str, Field(min_length=1, max_length=20_000)]


class ChatIn(BaseModel):
    provider: Provider = "claude"
    year: Year
    month: Month
    messages: Annotated[list[ChatMessage], Field(min_length=1, max_length=20)]


class CategorizeIn(BaseModel):
    provider: Provider = "claude"
    label: Annotated[str, Field(max_length=120)] = ""
    payee: Annotated[str, Field(max_length=60)] = ""


def create_app(*, verifier: Optional[TokenVerifier] = None,
               finance_http: Optional[httpx.Client] = None,
               providers: Optional[Providers] = None,
               counter: Optional[Counter] = None) -> FastAPI:
    supabase_url = env("SUPABASE_URL", required=True)
    daily_limit = env_int("AI_DAILY_LIMIT", 40)

    app = FastAPI(title="fintrack-ai-service", version=VERSION,
                  docs_url=None, redoc_url=None, openapi_url=None)
    app.add_middleware(RequestContextMiddleware)
    app.state.verifier = verifier or TokenVerifier(supabase_url)
    finance = finance_http or service_client(env("FINANCE_API_URL", required=True), timeout=15.0)
    prov = providers or Providers(ProviderConfig(
        anthropic_api_key=env("ANTHROPIC_API_KEY", ""),
        gemini_api_key=env("GEMINI_API_KEY", ""),
        claude_model=env("CLAUDE_MODEL", "claude-opus-5-5"),
        gemini_model=env("GEMINI_MODEL", "gemini-2.5-flash"),
    ))
    quota = counter or Counter(redis_from_url(env("REDIS_URL", "")), prefix="ai")
    add_health_routes(app)
    current_user = user_dependency()

    def _finance_get(user: User, path: str, **params):
        try:
            r = finance.get(path, params=params, headers={"Authorization": f"Bearer {user.token}"})
        except httpx.HTTPError as exc:
            raise HTTPException(503, "Service de données indisponible.") from exc
        if r.status_code == 401:
            raise HTTPException(401, "Session expirée.")
        if r.status_code >= 400:
            raise HTTPException(502, "Données indisponibles.")
        return r.json()

    def _quota(user: User):
        """Vérifie le quota AVANT l'appel, ne le décompte qu'APRÈS succès :
        une panne du fournisseur ne consomme pas les requêtes du jour."""
        day = dt.date.today().isoformat()
        if quota.get("daily", user.id, day) >= daily_limit:
            raise HTTPException(429, f"Limite quotidienne de {daily_limit} requêtes IA atteinte.")
        return lambda: quota.incr("daily", user.id, day, window=86_400)

    def _run(fn):
        try:
            return fn()
        except ProviderError as exc:
            raise HTTPException(502, str(exc)) from exc

    @app.get("/v1/providers")
    def get_providers(user: User = Depends(current_user)):
        day = dt.date.today().isoformat()
        used = quota.get("daily", user.id, day)
        return {"providers": prov.cfg.available(), "daily_limit": daily_limit,
                "remaining": max(0, daily_limit - used)}

    @app.post("/v1/insights")
    def insights(body: InsightsIn, user: User = Depends(current_user)):
        charge = _quota(user)
        ctx = _finance_get(user, "/v1/ai-context", year=body.year, month=body.month,
                           months=body.months)
        prompt = INSIGHTS_PROMPT.format(context=json.dumps(ctx, ensure_ascii=False))
        text = _run(lambda: prov.complete(body.provider, SYSTEM_ADVISOR,
                                          [{"role": "user", "content": prompt}],
                                          effort="medium", max_tokens=6000))
        charge()
        return {"provider": body.provider, "text": text}

    @app.post("/v1/chat")
    def chat(body: ChatIn, user: User = Depends(current_user)):
        if body.messages[-1].role != "user":
            raise HTTPException(422, "Le dernier message doit venir de l'utilisateur.")
        charge = _quota(user)
        ctx = _finance_get(user, "/v1/ai-context", year=body.year, month=body.month, months=6)
        # Le contexte ouvre la conversation ; l'historique suit (append-only).
        msgs = [{"role": "user", "content":
                 "Mon résumé financier (6 derniers mois) :\n"
                 + json.dumps(ctx, ensure_ascii=False)
                 + "\n\nRéponds à mes questions à partir de ce résumé."},
                {"role": "assistant", "content": "C'est noté, je vous écoute."}]
        msgs += [m.model_dump() for m in body.messages]
        text = _run(lambda: prov.complete(body.provider, SYSTEM_ADVISOR, msgs,
                                          effort="low", max_tokens=3000))
        charge()
        return {"provider": body.provider, "text": text}

    @app.post("/v1/categorize")
    def categorize(body: CategorizeIn, user: User = Depends(current_user)):
        if not (body.label.strip() or body.payee.strip()):
            raise HTTPException(422, "Libellé ou enseigne requis.")
        charge = _quota(user)
        cats = _finance_get(user, "/v1/categories")
        names = [c["name"] for c in cats]
        if not names:
            raise HTTPException(409, "Aucune catégorie définie.")
        prompt = (f"Catégories : {json.dumps(names, ensure_ascii=False)}\n"
                  f"Libellé : {body.label.strip() or '—'}\n"
                  f"Enseigne : {body.payee.strip() or '—'}")
        name = _run(lambda: prov.choose(body.provider, SYSTEM_CATEGORIZER, prompt, names))
        cat = next(c for c in cats if c["name"] == name)
        charge()
        return {"category_id": cat["id"], "category": name, "provider": body.provider}

    return app


app = create_app() if not env("FINTRACK_NO_AUTOAPP") else None
