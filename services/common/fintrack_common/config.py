"""Lecture de la configuration depuis l'environnement (12-factor)."""
from __future__ import annotations

import os


class ConfigError(RuntimeError):
    """Configuration invalide : le service refuse de démarrer."""


def env(name: str, default: str | None = None, *, required: bool = False,
        min_len: int = 0) -> str:
    """Lit une variable d'environnement. Supporte aussi NAME_FILE (secret
    monté en fichier, convention Docker/Kubernetes)."""
    value = os.environ.get(name)
    file_path = os.environ.get(f"{name}_FILE")
    if not value and file_path:
        try:
            with open(file_path, encoding="utf-8") as f:
                value = f.read().strip()
        except OSError as exc:
            raise ConfigError(f"{name}_FILE illisible : {exc}") from exc
    value = (value or "").strip() or (default or "")
    if required and not value:
        raise ConfigError(f"Variable d'environnement obligatoire manquante : {name}")
    if value and min_len and len(value) < min_len:
        raise ConfigError(f"{name} trop courte ({min_len} caractères minimum).")
    return value


def env_int(name: str, default: int) -> int:
    raw = os.environ.get(name, "").strip()
    if not raw:
        return default
    try:
        return int(raw)
    except ValueError as exc:
        raise ConfigError(f"{name} doit être un entier (reçu : {raw!r})") from exc


def env_bool(name: str, default: bool) -> bool:
    raw = os.environ.get(name, "").strip().lower()
    if not raw:
        return default
    return raw in ("1", "true", "yes", "on")


VERSION = os.environ.get("FINTRACK_VERSION", "dev")
