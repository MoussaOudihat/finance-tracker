"""
bulk.py — Saisie en masse : analyse d'un collage (Excel, relevé bancaire,
CSV) et validation des lignes de la grille. Fonctions pures, sans E/S.

Colonnes reconnues de deux façons :
1. une ligne d'en-tête (« Catégorie », « Montant », « Libellé »…) ;
2. sinon, cellule par cellule : la première valeur numérique est le
   montant, une cellule égale à un nom de catégorie est la catégorie, les
   dates sont ignorées, les autres textes sont pris dans l'ordre
   (libellé puis enseigne pour une dépense, source puis libellé pour un
   revenu).
"""
from __future__ import annotations

import math
import re
import unicodedata
from dataclasses import dataclass, field

MAX_ROWS = 200                 # limite de l'API (une seule insertion)
AI_BATCH_MAX = 50              # lignes envoyées à l'IA par suggestion (1 requête du quota)
MAX_PASTE_CHARS = 100_000
GRID_BLANK_ROWS = 12
GRID_ADD_ROWS = 10             # lignes ajoutées par « + Ajouter des lignes »

_DATE_RE = re.compile(r"^\d{1,4}[/.-]\d{1,2}[/.-]\d{1,4}$")
_AMOUNT_RE = re.compile(r"^[-+]?\(?\d[\d.,]*\)?-?$")

HEADERS = {
    "amount": ("montant", "amount", "somme", "prix", "debit", "valeur", "total"),
    "category": ("categorie", "category", "cat", "rubrique", "poste"),
    "label": ("libelle", "label", "description", "designation", "intitule", "motif",
              "operation", "detail", "details", "note"),
    "payee": ("enseigne", "commercant", "marchand", "payee", "beneficiaire", "tiers",
              "magasin", "fournisseur"),
    "source": ("source", "origine", "emetteur", "employeur", "provenance"),
    "date": ("date", "jour", "date operation", "date de valeur"),
}
LIMITS = {"label": 120, "payee": 60, "source": 120}


def norm(text: str) -> str:
    """Minuscules, sans accents ni espaces superflus (comparaisons)."""
    t = unicodedata.normalize("NFKD", text or "")
    t = "".join(ch for ch in t if not unicodedata.combining(ch))
    return " ".join(t.lower().replace("_", " ").split())


def parse_amount(raw: str) -> float | None:
    """'1 234,56 €', '-12,50', '1.234,56', '(8.90)', '12.5' -> valeur absolue
    (les relevés bancaires notent les débits en négatif). None si ce n'est
    pas un montant."""
    s = (raw or "").strip()
    for junk in ("\xa0", " ", " ", "€", "EUR", "eur"):
        s = s.replace(junk, "")
    if not s or not _AMOUNT_RE.match(s):
        return None
    s = s.strip("()+-")
    if "," in s and "." in s:                      # le dernier séparateur est décimal
        dec = "," if s.rfind(",") > s.rfind(".") else "."
        s = s.replace("." if dec == "," else ",", "").replace(dec, ".")
    elif s.count(",") == 1:
        s = s.replace(",", ".")
    elif s.count(",") > 1 or s.count(".") > 1:     # séparateurs de milliers
        s = s.replace(",", "").replace(".", "")
    try:
        v = float(s)
    except ValueError:
        return None
    if not math.isfinite(v):
        return None
    return round(v, 2)


def fmt_amount(v: float | None) -> str:
    return "" if v is None else f"{v:.2f}".replace(".", ",")


@dataclass
class Row:
    amount: str = ""                 # tel qu'affiché/saisi ("12,50")
    category_id: int | None = None
    label: str = ""
    extra: str = ""                  # enseigne (dépense) ou source (revenu)
    keep: bool = True
    suggested: bool = False          # catégorie proposée par l'IA (à vérifier)
    errors: list[str] = field(default_factory=list)

    @property
    def blank(self) -> bool:
        return not (self.amount.strip() or self.label.strip() or self.extra.strip())


def _split(line: str) -> list[str]:
    if "\t" in line:
        sep = "\t"
    elif ";" in line:
        sep = ";"
    elif line.count(",") >= 2 and not re.search(r"\d,\d{1,2}(?!\d)", line):
        sep = ","                                   # CSV « anglais » sans virgule décimale
    else:
        return [line.strip()]
    return [c.strip().strip('"').strip() for c in line.split(sep)]


def _header_map(cells: list[str]) -> dict[int, str] | None:
    if any(parse_amount(c) is not None for c in cells):
        return None
    mapping = {}
    for i, c in enumerate(cells):
        n = norm(c)
        for key, words in HEADERS.items():
            if n in words and key not in mapping.values():
                mapping[i] = key
                break
    return mapping if "amount" in mapping.values() else None


def match_category(text: str, categories: list[dict]) -> int | None:
    n = norm(text)
    if not n:
        return None
    by_name = {norm(c["name"]): c["id"] for c in categories}
    if n in by_name:
        return by_name[n]
    starts = [cid for name, cid in by_name.items() if name.startswith(n) and len(n) >= 3]
    return starts[0] if len(starts) == 1 else None


def parse_paste(text: str, kind: str, categories: list[dict]) -> tuple[list[Row], list[str]]:
    """Collage -> lignes de grille (non encore validées) + avertissements."""
    warnings: list[str] = []
    lines = [ln for ln in (text or "").replace("\r\n", "\n").replace("\r", "\n").split("\n")
             if ln.strip()]
    if not lines:
        return [], ["Rien à analyser : collez des lignes copiées depuis Excel ou un relevé."]
    header = _header_map(_split(lines[0]))
    if header:
        lines = lines[1:]
    rows: list[Row] = []
    for ln in lines:
        cells = _split(ln)
        row = Row()
        texts: list[str] = []
        amount = None
        for i, cell in enumerate(cells):
            if not cell:
                continue
            role = header.get(i) if header else None
            if header and role is None:
                continue                            # colonne non reconnue : ignorée
            if role == "date" or (role is None and _DATE_RE.match(cell)):
                continue
            if role == "amount" or (role is None and amount is None
                                    and parse_amount(cell) is not None):
                if amount is None:
                    amount = parse_amount(cell)
                    if amount is None:
                        row.amount = cell           # laissé tel quel : sera signalé
                continue
            if role == "category" or (role is None and kind == "expenses"
                                      and row.category_id is None
                                      and match_category(cell, categories) is not None):
                row.category_id = match_category(cell, categories)
                if row.category_id is None:
                    row.errors.append(f"Catégorie « {cell[:40]} » inconnue.")
                continue
            if role == "label":
                row.label = cell
            elif role in ("payee", "source"):
                row.extra = cell
            else:
                texts.append(cell)
        if not header:
            first, second = (texts + ["", ""])[:2]
            if kind == "expenses":
                row.label, row.extra = first, second
            else:
                row.extra, row.label = first, second
        if amount is not None:
            row.amount = fmt_amount(amount)
        row.label = row.label[:LIMITS["label"]]
        row.extra = row.extra[:LIMITS["payee" if kind == "expenses" else "source"]]
        if not row.blank:
            rows.append(row)
    if len(rows) > MAX_ROWS:
        warnings.append(f"{len(rows)} lignes collées : seules les {MAX_ROWS} premières sont "
                        "reprises (limite par enregistrement).")
        rows = rows[:MAX_ROWS]
    return rows, warnings


def rows_from_form(keep: list[str], amounts: list[str], cats: list[str], labels: list[str],
                   extras: list[str]) -> list[Row]:
    n = len(amounts)
    if not (len(cats) == len(labels) == len(extras) == n):
        raise ValueError("Formulaire incomplet — rechargez la page.")
    kept = set(keep)
    rows = []
    for i in range(n):
        try:
            cid = int(cats[i]) if cats[i] else None
        except ValueError:
            cid = None
        rows.append(Row(amount=amounts[i].strip(), category_id=cid, label=labels[i].strip(),
                        extra=extras[i].strip(), keep=str(i) in kept))
    return rows


def validate(rows: list[Row], kind: str, categories: list[dict]) -> list[dict]:
    """Remplit row.errors ; renvoie le corps de l'API pour les lignes cochées
    et non vides (liste vide si au moins une erreur)."""
    cat_ids = {c["id"] for c in categories}
    payload: list[dict] = []
    for r in rows:
        r.errors = []
        if not r.keep or r.blank:
            continue
        v = parse_amount(r.amount)
        if v is None or v <= 0 or v > 1e9:
            r.errors.append("Montant invalide.")
        else:
            r.amount = fmt_amount(v)
        if len(r.label) > LIMITS["label"]:
            r.errors.append("Libellé trop long (120 caractères max).")
        if kind == "expenses":
            if r.category_id not in cat_ids:
                r.errors.append("Catégorie à choisir.")
            if len(r.extra) > LIMITS["payee"]:
                r.errors.append("Enseigne trop longue (60 caractères max).")
            body = {"category_id": r.category_id, "amount": v, "label": r.label, "payee": r.extra}
        else:
            source = r.extra or r.label
            if not source:
                r.errors.append("Source requise.")
            if len(source) > LIMITS["source"]:
                r.errors.append("Source trop longue (120 caractères max).")
            body = {"source": source, "amount": v, "label": r.label}
        payload.append(body)
    if any(r.errors for r in rows):
        return []
    return payload
