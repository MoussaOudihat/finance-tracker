"""
config.py — Constantes globales de l'application
"""
import os
import sys

APP_TITLE = "Fintrack"

# ── Chemin de base ───────────────────────────────────────────
# Fonctionne en mode script (.py) ET en mode .exe (PyInstaller --onedir)
if getattr(sys, "frozen", False):
    # Exécutable PyInstaller : base = dossier contenant le .exe
    _BASE_DIR    = os.path.dirname(sys.executable)
    _BUNDLE_DIR  = sys._MEIPASS          # répertoire des fichiers bundlés
else:
    # Mode script normal
    _BASE_DIR    = os.path.dirname(os.path.abspath(__file__))
    _BUNDLE_DIR  = _BASE_DIR

# ── Version lue depuis le fichier VERSION (écrit par le CI au moment de la release) ──
try:
    with open(os.path.join(_BUNDLE_DIR, "VERSION"), encoding="utf-8") as _vf:
        APP_VERSION = _vf.read().strip() or "dev"
except Exception:
    APP_VERSION = "dev"

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

LIABILITY_TYPES = [
    ("Prêt voiture",     "voiture"),
    ("Prêt conso/perso", "conso"),
    ("Autre",            "autre"),
]
LIABILITY_LABEL = {key: label for label, key in LIABILITY_TYPES}

# ── Valeurs des filtres "Tout afficher" ──────────────────────
# Centralisées ici pour éviter les typos qui cassent le reset silencieusement.
FILTER_ALL_CATS   = "Toutes catégories"
FILTER_ALL_PAYEES = "Toutes enseignes"
FILTER_ALL_TYPES  = "Tous types"

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
    "bg":           "#F0F4F8",
    "sidebar":      "#1E1B4B",   # indigo très foncé — cohérent avec l'icône
    "sidebar2":     "#2D2A6E",
    "card":         "#FFFFFF",
    "border":       "#E2E8F0",
    "primary":      "#4F46E5",   # indigo #4F46E5 — Option D
    "primary_hover":"#4338CA",
    "green":        "#22C55E",
    "green_soft":   "#DCFCE7",
    "red":          "#EF4444",
    "red_soft":     "#FEE2E2",
    "blue":         "#3B82F6",
    "amber":        "#F59E0B",
    "text":         "#1E293B",
    "muted":        "#64748B",
    "light":        "#F8FAFC",
}

# Palettes light / dark (muter C en place pour un effet immédiat)
_C_LIGHT = {
    "bg":           "#F0F4F8",
    "sidebar":      "#1E1B4B",
    "sidebar2":     "#2D2A6E",
    "card":         "#FFFFFF",
    "border":       "#E2E8F0",
    "primary":      "#4F46E5",
    "primary_hover":"#4338CA",
    "green":        "#22C55E",
    "green_soft":   "#DCFCE7",
    "red":          "#EF4444",
    "red_soft":     "#FEE2E2",
    "blue":         "#3B82F6",
    "amber":        "#F59E0B",
    "text":         "#1E293B",
    "muted":        "#64748B",
    "light":        "#F8FAFC",
}

_C_DARK = {
    "bg":           "#0F0E1F",
    "sidebar":      "#0C0A1E",
    "sidebar2":     "#1A1740",
    "card":         "#1A1740",
    "border":       "#2D2A6E",
    "primary":      "#6D63F5",   # indigo plus clair en dark
    "primary_hover":"#5B52E8",
    "green":        "#22C55E",
    "green_soft":   "#14532D",
    "red":          "#EF4444",
    "red_soft":     "#7F1D1D",
    "blue":         "#3B82F6",
    "amber":        "#F59E0B",
    "text":         "#E2E8F0",
    "muted":        "#94A3B8",
    "light":        "#1E1B4B",
}


def apply_palette(dark: bool):
    """Met à jour le dict C en place → tous les modules voient le changement."""
    C.update(_C_DARK if dark else _C_LIGHT)


def apply_chart_theme():
    """
    Aligne les couleurs par défaut de matplotlib (texte, labels, ticks,
    légende) sur le thème courant (C["muted"]). À appeler au début du
    render() de chaque page contenant des graphiques — les nombreux appels
    set_xticklabels()/set_ylabel()/tick_params() sans couleur explicite
    héritent sinon du noir par défaut de matplotlib, invisible sur un fond
    de graphique sombre. N'importe matplotlib que s'il est déjà chargé
    (pages sans graphique jamais visitées ne paient pas ce coût).
    """
    import sys
    if "matplotlib" not in sys.modules:
        return
    import matplotlib
    matplotlib.rcParams.update({
        "text.color":        C["muted"],
        "axes.labelcolor":   C["muted"],
        "xtick.color":       C["muted"],
        "ytick.color":       C["muted"],
        "legend.labelcolor": C["muted"],
    })
