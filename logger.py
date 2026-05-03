"""
logger.py — Logging centralisé pour Finance Tracker

Usage dans n'importe quel module :
    from logger import log
    log.info("Démarrage")
    log.warning("Attention : %s", msg)
    log.error("Erreur critique", exc_info=True)

En mode .exe PyInstaller : écrit dans data/app.log (à côté de l'exe).
En mode script : écrit dans data/app.log (à côté de main.py).
Rotation automatique : 2 fichiers de 500 Ko max.

Niveaux disponibles : DEBUG, INFO, WARNING, ERROR
Configurable depuis les Paramètres de l'app (app_settings: log_level, log_enabled).
"""
import logging
import os
import sys
from logging.handlers import RotatingFileHandler

# ── Chemin du fichier log ────────────────────────────────────
if getattr(sys, "frozen", False):
    _BASE = os.path.dirname(sys.executable)
else:
    _BASE = os.path.dirname(os.path.abspath(__file__))

_LOG_DIR  = os.path.join(_BASE, "data")
_LOG_FILE = os.path.join(_LOG_DIR, "app.log")

os.makedirs(_LOG_DIR, exist_ok=True)

# ── Format ───────────────────────────────────────────────────
_FMT      = "%(asctime)s [%(levelname)s] %(name)s — %(message)s"
_DATE_FMT = "%Y-%m-%d %H:%M:%S"
_formatter = logging.Formatter(_FMT, datefmt=_DATE_FMT)

# ── Handler fichier (toujours actif) ─────────────────────────
_file_handler = RotatingFileHandler(
    _LOG_FILE,
    maxBytes=500_000,   # 500 Ko par fichier
    backupCount=2,
    encoding="utf-8",
)
_file_handler.setFormatter(_formatter)

# ── Handler console (uniquement en mode dev — pas d'exe sans console) ──
_IS_FROZEN = getattr(sys, "frozen", False)
_handlers: list = [_file_handler]
if not _IS_FROZEN:
    _console = logging.StreamHandler(sys.stdout)
    _console.setFormatter(_formatter)
    _handlers.append(_console)

# ── Niveau par défaut ─────────────────────────────────────────
_DEFAULT_LEVEL = logging.DEBUG if not _IS_FROZEN else logging.INFO

logging.basicConfig(level=_DEFAULT_LEVEL, handlers=_handlers)

# ── Logger racine de l'application ───────────────────────────
log = logging.getLogger("FinanceTracker")

# ── Niveaux disponibles (pour l'UI Settings) ─────────────────
LOG_LEVELS = ["DEBUG", "INFO", "WARNING", "ERROR"]


def configure_log_level(level_str: str, enabled: bool = True) -> None:
    """
    Reconfigure le niveau de log à chaud — appelé depuis les Paramètres.

    :param level_str: "DEBUG" | "INFO" | "WARNING" | "ERROR"
    :param enabled:   False = désactive complètement les logs fichier
    """
    level = getattr(logging, level_str.upper(), logging.INFO)

    if enabled:
        _file_handler.setLevel(logging.NOTSET)   # laisse le root filter décider
        logging.getLogger().setLevel(level)
        log.setLevel(level)
    else:
        # Désactiver = passer au niveau CRITICAL (laisse presque rien passer)
        logging.getLogger().setLevel(logging.CRITICAL)
        log.setLevel(logging.CRITICAL)

    log.info("Niveau de log → %s (activé=%s)", level_str.upper(), enabled)


def apply_log_config_from_db(db) -> None:
    """
    Lit log_level et log_enabled depuis la DB et applique la configuration.
    Appelé au démarrage depuis main.py (après init DB).
    """
    level   = db.get_setting("log_level",   "INFO")
    enabled = db.get_setting("log_enabled", "1") == "1"
    configure_log_level(level, enabled)


def get_log_file_path() -> str:
    """Retourne le chemin absolu du fichier de log courant."""
    return _LOG_FILE
