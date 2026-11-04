"""Formatage et calendrier partagés (une seule implémentation pour tous
les services : pages web, notifications, API)."""
from __future__ import annotations

MONTHS_FR = ["janvier", "février", "mars", "avril", "mai", "juin", "juillet", "août",
             "septembre", "octobre", "novembre", "décembre"]


def month_name(month: int, capitalize: bool = False) -> str:
    name = MONTHS_FR[month - 1]
    return name.capitalize() if capitalize else name


def shift_month(year: int, month: int, delta: int) -> tuple[int, int]:
    """(année, mois) décalé de `delta` mois (négatif = passé)."""
    idx = year * 12 + (month - 1) + delta
    return idx // 12, idx % 12 + 1


def fmt_eur(value, sign: bool = False) -> str:
    """1234.5 -> '1 234,50 €' (sign=True : '+' devant les montants positifs)."""
    v = float(value or 0)
    prefix = "+" if sign and v > 0 else ""
    return f"{prefix}{v:,.2f} €".replace(",", " ").replace(".", ",")
