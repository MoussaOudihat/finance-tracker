"""
common.py — Constantes et fonctions utilitaires du BFF web, partagées par
main.py (application, session, rendu) et les modules routes_*.py.
"""
from __future__ import annotations

import hashlib
import html
import os
import re
from typing import Annotated
from urllib.parse import urlsplit

from pydantic import BaseModel, Field

from markupsafe import Markup

from fintrack_common.fmt import MONTHS_FR as _MONTHS
from fintrack_common.logs import setup_logging


log = setup_logging("web")
_HERE = os.path.dirname(os.path.abspath(__file__))

MONTHS_FR = [n.capitalize() for n in _MONTHS]
ASSET_LABEL = {"bourse": "Bourse / ETF / PEA", "immobilier": "Immobilier", "crypto": "Crypto",
               "or_metaux": "Or & Métaux", "compte": "Compte / Épargne", "autre": "Autre"}
LIABILITY_LABEL = {"voiture": "Prêt voiture", "conso": "Prêt conso/perso", "autre": "Autre"}
SECTIONS = {"depenses": ("expenses", "Dépenses"), "revenus": ("revenues", "Revenus"),
            "epargne": ("savings", "Épargne")}
COOKIE = "fintrack_sid"
THEME_COOKIE = "fintrack_theme"      # préférence d'affichage par appareil (non sensible)
THEME_LABEL = {"auto": "Auto", "light": "Clair", "dark": "Sombre"}
CSP = ("default-src 'self'; img-src 'self' data:; style-src 'self'; script-src 'self'; "
       "connect-src 'self'; form-action 'self' https://ticktick.com; "
       "frame-ancestors 'none'; base-uri 'none'; object-src 'none'")
LOGIN_MAX_PER_IP_ID = 5        # échecs / 15 min pour un couple (IP, identifiant)
LOGIN_MAX_PER_IP = 30          # échecs / 15 min pour une IP, tous comptes confondus
CHAT_MAX_MESSAGES = 20
# Consentement OAuth (serveur MCP) : identifiant de demande émis par Supabase Auth
OAUTH_AUTH_ID_RE = re.compile(r"^[A-Za-z0-9_-]{1,128}$")
OAUTH_LOOPBACK = ("localhost", "127.0.0.1", "::1")
OAUTH_DEFAULT_REDIRECT_HOSTS = "claude.ai,claude.com"


def oauth_redirect_allowed(url: str, allowed_hosts: tuple[str, ...]) -> bool:
    """Adresse de retour d'un client OAuth acceptable ? L'enregistrement
    dynamique permet à n'importe qui de déclarer un client : sans cette
    liste, un lien piégé pourrait faire approuver l'envoi d'un code vers un
    site tiers. Acceptés : boucle locale en http (clients CLI : Claude Code,
    opencode) et hôtes https de la liste (OAUTH_ALLOWED_REDIRECT_HOSTS)."""
    try:
        p = urlsplit(url or "")
        host = (p.hostname or "").lower()
    except ValueError:
        return False
    if p.username or p.password or not host:
        return False
    if p.scheme == "http":
        return host in OAUTH_LOOPBACK
    if p.scheme == "https":
        return host in OAUTH_LOOPBACK or any(host == h or host.endswith("." + h)
                                             for h in allowed_hosts)
    return False


def safe_next(raw: str | None) -> str:
    """SEULE règle anti open-redirect du site (redirections et retour après
    connexion) : un chemin absolu local — jamais « //hôte », ni barre oblique
    inverse en tête, ni caractère de contrôle (CR/LF…) ; sinon l'accueil."""
    raw = raw or ""
    if (len(raw) > 2048 or not raw.startswith("/") or raw.startswith(("//", "/\\"))
            or any(ord(ch) < 32 or ord(ch) == 127 for ch in raw)):
        return "/"
    return raw


class CategorizeReq(BaseModel):
    label: Annotated[str, Field(max_length=120)] = ""
    payee: Annotated[str, Field(max_length=60)] = ""


class _Redirect(Exception):
    def __init__(self, url: str):
        self.url = url


def render_ai_text(text: str) -> Markup:  # sûr : chaque ligne passe par html.escape()
    """Mise en forme MINIMALE et sûre d'une réponse IA : tout est échappé,
    seuls **gras** et les listes « - » sont rendus."""
    out, in_list = [], False
    for line in (text or "").splitlines():
        esc = html.escape(line.strip())
        esc = re.sub(r"\*\*(.+?)\*\*", r"<strong>\1</strong>", esc)
        if esc.startswith(("- ", "• ", "* ")):
            if not in_list:
                out.append("<ul>")
                in_list = True
            out.append(f"<li>{esc[2:]}</li>")
            continue
        if in_list:
            out.append("</ul>")
            in_list = False
        if esc:
            out.append(f"<p>{esc}</p>")
    if in_list:
        out.append("</ul>")
    return Markup("".join(out))  # noqa: S704  # nosec B704


def _static_hashes(directory: str) -> dict[str, str]:
    """Empreinte (12 caractères hexadécimaux du SHA-256) de chaque fichier
    statique, calculée une fois au démarrage."""
    out = {}
    for name in sorted(os.listdir(directory)):
        full = os.path.join(directory, name)
        if os.path.isfile(full):
            with open(full, "rb") as f:
                out[name] = hashlib.sha256(f.read()).hexdigest()[:12]
    return out


def line_points(values: list[float], vmax: float, *, width: float = 100.0,
                height: float = 40.0, pad: float = 2.0) -> str:
    """Attribut `points` d'une polyline SVG (viewBox 0 0 width height)."""
    if not values:
        return ""
    vmax = vmax or 1.0
    step = width / max(len(values) - 1, 1)
    def y(v: float) -> float:
        ratio = min(max(v / vmax, 0.0), 1.0)         # écrêté : jamais hors du cadre
        return height - pad - ratio * (height - 2 * pad)
    return " ".join(f"{i * step:.2f},{y(v):.2f}" for i, v in enumerate(values))


def parse_amount(raw: str) -> str:
    """Normalise la saisie ('1 234,50') ; la validation (> 0, fini) est
    faite par finance-api (pydantic : NaN/inf refusés)."""
    return (raw or "").replace(" ", "").replace("\xa0", "").replace(" ", "") \
        .replace("€", "").replace(",", ".").strip()
