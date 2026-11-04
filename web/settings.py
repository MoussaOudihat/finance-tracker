"""
web/settings.py — Configuration de l'interface web, lue depuis l'environnement.

Toute la configuration passe par des variables d'environnement (12-factor) :
ConfigMap/Secret Kubernetes, `env_file` docker compose, etc.

Variables :
  FINTRACK_DATA_DIR            Dossier de données (volume). Défaut : ./data
  FINTRACK_SECRET_KEY          Clé de signature des cookies de session (OBLIGATOIRE,
                               32+ caractères aléatoires).
  FINTRACK_AUTH_MODE           "supabase" (défaut) ou "local".
  SUPABASE_URL                 URL du projet Supabase (mode supabase).
  SUPABASE_ANON_KEY            Clé anon du projet Supabase (mode supabase).
  FINTRACK_WEB_USER            Identifiant (mode local).
  FINTRACK_WEB_PASSWORD_HASH   Hash bcrypt du mot de passe (mode local).
  FINTRACK_COOKIE_SECURE       "1" (défaut) : cookie envoyé uniquement en HTTPS.
                               Mettre "0" pour un test en http://localhost.
  FINTRACK_SESSION_MAX_AGE     Durée de vie de la session en secondes (défaut 8 h).
  FINTRACK_SYNC_DELAY          Délai (s) avant l'envoi vers Supabase après une
                               modification — regroupe les saisies (défaut 20).
  FINTRACK_IDLE_TIMEOUT        Inactivité (s) après laquelle l'espace d'un
                               utilisateur est synchronisé puis fermé (défaut 3600).
"""
from __future__ import annotations

import os
from dataclasses import dataclass


class ConfigError(RuntimeError):
    """Configuration invalide — l'application refuse de démarrer."""


def _env_int(name: str, default: int) -> int:
    raw = os.environ.get(name, "").strip()
    if not raw:
        return default
    try:
        return int(raw)
    except ValueError as exc:
        raise ConfigError(f"{name} doit être un entier (reçu : {raw!r})") from exc


@dataclass(frozen=True)
class WebSettings:
    data_dir: str
    secret_key: str
    auth_mode: str
    supabase_url: str
    supabase_anon_key: str
    local_user: str
    local_password_hash: str
    cookie_secure: bool
    session_max_age: int
    sync_delay: int
    idle_timeout: int

    @property
    def users_dir(self) -> str:
        return os.path.join(self.data_dir, "users")

    @classmethod
    def from_env(cls) -> "WebSettings":
        data_dir = os.environ.get("FINTRACK_DATA_DIR") or os.path.join(
            os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "data"
        )
        s = cls(
            data_dir=data_dir,
            secret_key=os.environ.get("FINTRACK_SECRET_KEY", ""),
            auth_mode=os.environ.get("FINTRACK_AUTH_MODE", "supabase").strip().lower(),
            supabase_url=os.environ.get("SUPABASE_URL", "").strip(),
            supabase_anon_key=os.environ.get("SUPABASE_ANON_KEY", "").strip(),
            local_user=os.environ.get("FINTRACK_WEB_USER", "").strip(),
            local_password_hash=os.environ.get("FINTRACK_WEB_PASSWORD_HASH", "").strip(),
            cookie_secure=os.environ.get("FINTRACK_COOKIE_SECURE", "1").strip() != "0",
            session_max_age=_env_int("FINTRACK_SESSION_MAX_AGE", 8 * 3600),
            sync_delay=_env_int("FINTRACK_SYNC_DELAY", 20),
            idle_timeout=_env_int("FINTRACK_IDLE_TIMEOUT", 3600),
        )
        s.validate()
        return s

    def validate(self) -> None:
        if len(self.secret_key) < 32:
            raise ConfigError(
                "FINTRACK_SECRET_KEY est absente ou trop courte (32 caractères "
                "minimum). Générez-en une : python -c \"import secrets; "
                "print(secrets.token_urlsafe(48))\""
            )
        if self.auth_mode == "supabase":
            if not (self.supabase_url and self.supabase_anon_key):
                raise ConfigError(
                    "Mode supabase : SUPABASE_URL et SUPABASE_ANON_KEY sont obligatoires."
                )
        elif self.auth_mode == "local":
            if not (self.local_user and self.local_password_hash.startswith("$2")):
                raise ConfigError(
                    "Mode local : FINTRACK_WEB_USER et FINTRACK_WEB_PASSWORD_HASH "
                    "(hash bcrypt) sont obligatoires. Générez le hash : "
                    "python -m web.hash_password"
                )
        else:
            raise ConfigError(
                f"FINTRACK_AUTH_MODE inconnu : {self.auth_mode!r} (attendu : supabase | local)"
            )
