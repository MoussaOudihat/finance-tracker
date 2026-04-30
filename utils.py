"""
utils.py — Fonctions utilitaires pures
"""
from config import MONTH_NAME_TO_NUM


def parse_notion_month(raw: str) -> tuple[int | None, int | None]:
    """
    Parse un champ mois Notion.
    Ex: 'Septembre 25 (https://notion.so/...)' → (2025, 9)
    """
    clean = raw.split("(")[0].strip()
    parts = clean.split()
    if len(parts) < 2:
        return None, None
    month_num = MONTH_NAME_TO_NUM.get(parts[0].lower())
    try:
        year = int(parts[1])
        year = 2000 + year if year < 100 else year
    except ValueError:
        return None, None
    return (year, month_num) if month_num else (None, None)


def parse_amount(raw: str) -> float:
    """
    Parse un montant Notion.
    Ex: '3\u202f924,50\xa0€' → 3924.50
    """
    cleaned = (
        raw
        .replace("\u202f", "")   # narrow no-break space (séparateur de milliers)
        .replace("\xa0", "")     # no-break space avant €
        .replace("€", "")
        .replace(" ", "")
        .replace(",", ".")
        .strip()
    )
    try:
        return float(cleaned)
    except ValueError:
        return 0.0


def fmt_amount(value: float, sign: bool = False) -> str:
    """Formate un montant en euros lisible."""
    prefix = "+" if sign and value > 0 else ""
    return f"{prefix}{value:,.2f} €".replace(",", " ").replace(".", ",")


def pct_color(value: float, colors: dict) -> str:
    """Retourne une couleur selon le signe d'une valeur."""
    if value > 0:
        return colors["green"]
    if value < 0:
        return colors["red"]
    return colors["muted"]
