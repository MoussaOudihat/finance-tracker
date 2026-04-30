"""
config.py — Constantes globales de l'application
"""
import os
import sys

APP_TITLE   = "Finance Tracker"
APP_VERSION = "2.1"

# ── Chemin de base ───────────────────────────────────────────
# Fonctionne en mode script (.py) ET en mode .exe (PyInstaller --onedir)
if getattr(sys, "frozen", False):
    # Exécutable PyInstaller : base = dossier contenant le .exe
    _BASE_DIR = os.path.dirname(sys.executable)
else:
    # Mode script normal
    _BASE_DIR = os.path.dirname(os.path.abspath(__file__))

DB_PATH = os.path.join(_BASE_DIR, "data", "finance_tracker.db")

MONTHS_FR = [
    "Janvier", "Février", "Mars", "Avril", "Mai", "Juin",
    "Juillet", "Août", "Septembre", "Octobre", "Novembre", "Décembre",
]

MONTH_NAME_TO_NUM = {
    "janvier": 1,  "fevrier": 2,  "février": 2,  "mars": 3,
    "avril": 4,    "mai": 5,      "juin": 6,      "juillet": 7,
    "aout": 8,     "août": 8,     "septembre": 9, "octobre": 10,
    "novembre": 11,"decembre": 12,"décembre": 12,
}

ASSET_TYPES = [
    ("Bourse / ETF / PEA", "bourse"),
    ("Immobilier",          "immobilier"),
    ("Crypto",              "crypto"),
    ("Or & Métaux",         "or_metaux"),
    ("Compte / Épargne",    "compte"),
    ("Autre",               "autre"),
]
ASSET_LABEL = {key: label for label, key in ASSET_TYPES}

DEFAULT_CATEGORIES = [
    "ABONNEMENT", "ALIMENTATION", "AUTRES", "BANQUE", "BRICOLAGE",
    "CADEAUX", "DONS", "FAMILLE", "FORMATION", "IMPÔT",
    "LOGEMENT", "LOISIR ET SORTIES", "MUTUELLE", "PEA",
    "RESTAURANTS", "SANTÉ", "SHOPPING", "SPORT ET FITNESS",
    "TRANSPORT", "VOITURE", "VOYAGE", "VÊTEMENTS",
]

PALETTE = [
    "#3B6FE8", "#22C55E", "#F59E0B", "#EF4444", "#8B5CF6",
    "#06B6D4", "#EC4899", "#14B8A6", "#F97316", "#6366F1",
    "#84CC16", "#F43F5E", "#0EA5E9", "#A78BFA", "#FB923C",
]

C = {
    "bg":      "#F0F4F8",
    "sidebar": "#1A2340",
    "sidebar2":"#243050",
    "card":    "#FFFFFF",
    "border":  "#E2E8F0",
    "primary": "#3B6FE8",
    "green":   "#22C55E",
    "red":     "#EF4444",
    "blue":    "#3B82F6",
    "amber":   "#F59E0B",
    "text":    "#1E293B",
    "muted":   "#64748B",
    "light":   "#F8FAFC",
}

# Palettes light / dark (muter C en place pour un effet immédiat)
_C_LIGHT = {
    "bg":      "#F0F4F8",
    "sidebar": "#1A2340",
    "sidebar2":"#243050",
    "card":    "#FFFFFF",
    "border":  "#E2E8F0",
    "primary": "#3B6FE8",
    "green":   "#22C55E",
    "red":     "#EF4444",
    "blue":    "#3B82F6",
    "amber":   "#F59E0B",
    "text":    "#1E293B",
    "muted":   "#64748B",
    "light":   "#F8FAFC",
}

_C_DARK = {
    "bg":      "#0F1623",
    "sidebar": "#0A0F1A",
    "sidebar2":"#141E30",
    "card":    "#1A2340",
    "border":  "#2D3F5E",
    "primary": "#4F8EF7",
    "green":   "#22C55E",
    "red":     "#EF4444",
    "blue":    "#3B82F6",
    "amber":   "#F59E0B",
    "text":    "#E2E8F0",
    "muted":   "#94A3B8",
    "light":   "#243050",
}


def apply_palette(dark: bool):
    """Met à jour le dict C en place → tous les modules voient le changement."""
    C.update(_C_DARK if dark else _C_LIGHT)
