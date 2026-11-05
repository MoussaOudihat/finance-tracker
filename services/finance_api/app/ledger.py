"""
ledger.py — Règles métier de finance-api (portage de database.py) :
saisies, synchronisation Épargne → Patrimoine, budgets, agrégats.
"""
from __future__ import annotations

import logging
import statistics
from collections import defaultdict
from dataclasses import dataclass

from fastapi import HTTPException

from fintrack_common.fmt import shift_month

from .repo import Repo, in_filter

log = logging.getLogger(__name__)

ENTRY_TABLES = {"expenses": "expenses", "revenues": "revenues", "savings": "savings"}
_MIN_MATCH_LEN = 3


# ── Mois / clôture ───────────────────────────────────────────

def ensure_open(repo: Repo, year: int, month: int) -> dict:
    mo = repo.month(year, month, create=True)
    if mo.get("closed"):
        raise HTTPException(409, "Ce mois est clôturé : saisie verrouillée.")
    return mo


def entry_with_month(repo: Repo, table: str, entry_id: int) -> tuple[dict, dict]:
    entry = repo.get_one(table, entry_id)
    if entry is None:
        raise HTTPException(404, "Élément introuvable.")
    mo = repo.months_by_id([entry["month_id"]]).get(entry["month_id"])
    if mo is None:
        raise HTTPException(404, "Mois introuvable.")
    return entry, mo


# ── Catégories ───────────────────────────────────────────────

def categories(repo: Repo) -> list[dict]:
    return sorted(repo.select("categories", columns="id,name,is_default"),
                  key=lambda c: c["name"])


def category_id_or_404(repo: Repo, cat_id: int) -> dict:
    rows = repo.select("categories", {"id": f"eq.{cat_id}"}, limit=1)
    if not rows:
        raise HTTPException(422, "Catégorie inconnue.")
    return rows[0]


# ── Lecture d'un mois ────────────────────────────────────────

def month_entries(repo: Repo, year: int, month: int) -> dict:
    mo = repo.month(year, month, create=False)
    if mo is None:
        return {"closed": False, "expenses": [], "revenues": [], "savings": []}
    cats = {c["id"]: c["name"] for c in categories(repo)}
    exp = repo.rows_for_months("expenses", [mo["id"]])
    for e in exp:
        e["category"] = cats.get(e["category_id"], "?")
    exp.sort(key=lambda e: (e["category"], e.get("payee") or "", -e["amount"]))
    rev = sorted(repo.rows_for_months("revenues", [mo["id"]]), key=lambda r: r["source"])
    sav = sorted(repo.rows_for_months("savings", [mo["id"]]), key=lambda r: r.get("account") or "")
    return {"closed": bool(mo.get("closed")), "expenses": exp, "revenues": rev, "savings": sav}


def budget_status(repo: Repo, year: int, month: int, spent_by_cat: dict[str, float]) -> list[dict]:
    budgets = repo.select("budgets", {"year": f"eq.{year}", "month": f"eq.{month}"})
    out = []
    for b in budgets:
        if b["amount"] <= 0:
            continue
        spent = spent_by_cat.get(b["category"], 0.0)
        out.append({"category": b["category"], "budget": b["amount"], "spent": spent,
                    "pct": spent / b["amount"] * 100})
    return sorted(out, key=lambda b: -b["pct"])


def month_summary(repo: Repo, year: int, month: int) -> dict:
    data = month_entries(repo, year, month)
    by_cat: dict[str, float] = defaultdict(float)
    for e in data["expenses"]:
        by_cat[e["category"]] += e["amount"]
    rev = sum(r["amount"] for r in data["revenues"])
    exp = sum(e["amount"] for e in data["expenses"])
    sav = sum(s["amount"] for s in data["savings"])
    return {
        "year": year, "month": month, "closed": data["closed"],
        "revenues": rev, "expenses": exp, "savings": sav, "balance": rev - exp - sav,
        "by_category": sorted(({"name": k, "total": v} for k, v in by_cat.items()),
                              key=lambda c: -c["total"]),
        "budgets": budget_status(repo, year, month, by_cat),
    }


def history(repo: Repo, limit: int = 12) -> list[dict]:
    months = repo.select("months", order="year.desc,month.desc", limit=limit)
    ids = [m["id"] for m in months]
    sums: dict[str, dict[int, float]] = {}
    for table in ("revenues", "expenses", "savings"):
        acc: dict[int, float] = defaultdict(float)
        for r in repo.rows_for_months(table, ids, columns="month_id,amount"):
            acc[r["month_id"]] += r["amount"]
        sums[table] = acc
    return [{"year": m["year"], "month": m["month"],
             "rev": sums["revenues"][m["id"]], "exp": sums["expenses"][m["id"]],
             "sav": sums["savings"][m["id"]]} for m in reversed(months)]


def payees(repo: Repo, limit: int = 200) -> list[str]:
    counts: dict[str, int] = defaultdict(int)
    for r in repo.select("expenses", {"payee": "neq."}, columns="payee"):
        if r["payee"]:
            counts[r["payee"]] += 1
    return [p for p, _ in sorted(counts.items(), key=lambda kv: -kv[1])[:limit]]


# ── Patrimoine ───────────────────────────────────────────────

def assets_current(repo: Repo) -> list[dict]:
    latest: dict[tuple[str, str], dict] = {}
    for a in repo.select("assets"):
        k = (a["asset_type"], a["asset_name"])
        if k not in latest or (a["year"], a["month"]) > (latest[k]["year"], latest[k]["month"]):
            latest[k] = a
    return sorted(latest.values(), key=lambda a: (a["asset_type"], a["asset_name"]))


def liabilities_current(repo: Repo) -> list[dict]:
    latest: dict[str, dict] = {}
    for li in repo.select("liabilities"):
        k = li["liability_name"]
        if k not in latest or (li["year"], li["month"]) > (latest[k]["year"], latest[k]["month"]):
            latest[k] = li
    return sorted(latest.values(), key=lambda x: (x["liability_type"], x["liability_name"]))


def patrimoine(repo: Repo) -> dict:
    assets = assets_current(repo)
    liabilities = liabilities_current(repo)
    by_type: dict[str, float] = defaultdict(float)
    for a in assets:
        by_type[a["asset_type"]] += a["value"]
    total_a = sum(by_type.values())
    total_l = sum(x["remaining_capital"] for x in liabilities)
    return {"assets": assets, "liabilities": liabilities,
            "by_type": sorted(({"type": t, "total": v} for t, v in by_type.items()),
                              key=lambda x: -x["total"]),
            "total_assets": total_a, "total_liabilities": total_l,
            "net_worth": total_a - total_l}


# ── Épargne → Patrimoine (même règle que database.py) ────────

def _norm(name: str) -> str:
    return "".join(ch for ch in (name or "").lower() if ch.isalnum())


def match_compte_asset(account: str, assets: list[dict]) -> dict | None:
    """Correspondance UNIQUE avec un actif de type 'compte', sinon None."""
    n = _norm(account)
    if len(n) < _MIN_MATCH_LEN:
        return None
    match = None
    for a in assets:
        if a["asset_type"] != "compte":
            continue
        na = _norm(a["asset_name"])
        if na and (n in na or na in n):
            if match is not None:
                return None
            match = a
    return match


def apply_saving_to_asset(repo: Repo, year: int, month: int, asset_name: str,
                          delta: float) -> None:
    current = next((a for a in assets_current(repo)
                    if a["asset_type"] == "compte" and a["asset_name"] == asset_name), None)
    if current is None:
        log.warning("Épargne liée à un compte introuvable — ajustement ignoré.")
        return
    if (year, month) < (current["year"], current["month"]):
        return   # mois antérieur au dernier instantané : on ne réécrit pas l'historique
    repo.upsert("assets", {
        "id": current["id"] if (current["year"], current["month"]) == (year, month)
        else repo._next_id("assets"),
        "year": year, "month": month, "asset_type": "compte", "asset_name": asset_name,
        "value": max(0.0, (current["value"] or 0) + delta),
        "cost_basis": max(0.0, (current["cost_basis"] or 0) + delta),
        "notes": current.get("notes") or "",
    }, "user_id,year,month,asset_type,asset_name")


# ── Saisies ──────────────────────────────────────────────────

@dataclass
class BudgetCheck:
    """Dépense d'une catégorie avant/après une écriture, pour les alertes."""
    category: str
    year: int
    month: int
    budget: float
    before: float
    after: float


def _spent(repo: Repo, month_id: int, category_id: int) -> float:
    return sum(r["amount"] for r in repo.select(
        "expenses", {"month_id": f"eq.{month_id}", "category_id": f"eq.{category_id}"},
        columns="amount"))


def _budget_amount(repo: Repo, year: int, month: int, category: str) -> float:
    b = repo.select("budgets", {"year": f"eq.{year}", "month": f"eq.{month}",
                                "category": f"eq.{category}"}, columns="amount", limit=1)
    return b[0]["amount"] if b else 0.0


def add_expense(repo: Repo, year: int, month: int, category_id: int, amount: float,
                label: str, payee: str) -> tuple[dict, BudgetCheck]:
    """Une seule lecture de la catégorie, du mois et du budget (avant : ~12
    allers-retours PostgREST par saisie)."""
    cat = category_id_or_404(repo, category_id)
    mo = ensure_open(repo, year, month)
    before = _spent(repo, mo["id"], category_id)
    row = repo.insert("expenses", {"month_id": mo["id"], "category_id": category_id,
                                   "amount": amount, "label": label,
                                   "payee": payee.strip().upper()})
    repo.touch_sync_ts()
    return row, BudgetCheck(cat["name"], year, month,
                            _budget_amount(repo, year, month, cat["name"]),
                            before, before + amount)


def update_expense(repo: Repo, entry_id: int, category_id: int, amount: float,
                   label: str, payee: str) -> tuple[dict, BudgetCheck]:
    entry, mo = entry_with_month(repo, "expenses", entry_id)
    if mo.get("closed"):
        raise HTTPException(409, "Ce mois est clôturé : saisie verrouillée.")
    cat = category_id_or_404(repo, category_id)
    current = _spent(repo, mo["id"], category_id)        # inclut l'ancienne ligne si même catégorie
    before = current
    after = current - (entry["amount"] if entry["category_id"] == category_id else 0) + amount
    row = repo.update("expenses", {"id": f"eq.{entry_id}"},
                      {"category_id": category_id, "amount": amount, "label": label,
                       "payee": payee.strip().upper()})[0]
    repo.touch_sync_ts()
    return row, BudgetCheck(cat["name"], mo["year"], mo["month"],
                            _budget_amount(repo, mo["year"], mo["month"], cat["name"]),
                            before, after)


def add_revenue(repo: Repo, year: int, month: int, source: str, amount: float,
                label: str) -> dict:
    mo = ensure_open(repo, year, month)
    row = repo.insert("revenues", {"month_id": mo["id"], "source": source,
                                   "amount": amount, "label": label})
    repo.touch_sync_ts()
    return row


def update_revenue(repo: Repo, entry_id: int, source: str, amount: float, label: str) -> dict:
    _, mo = entry_with_month(repo, "revenues", entry_id)
    if mo.get("closed"):
        raise HTTPException(409, "Ce mois est clôturé : saisie verrouillée.")
    row = repo.update("revenues", {"id": f"eq.{entry_id}"},
                      {"source": source, "amount": amount, "label": label})[0]
    repo.touch_sync_ts()
    return row


def add_saving(repo: Repo, year: int, month: int, account: str, amount: float,
               label: str) -> dict:
    mo = ensure_open(repo, year, month)
    matched = match_compte_asset(account, assets_current(repo))
    linked = matched["asset_name"] if matched else ""
    row = repo.insert("savings", {"month_id": mo["id"], "account": account, "amount": amount,
                                  "label": label, "linked_asset_name": linked})
    if linked:
        apply_saving_to_asset(repo, year, month, linked, amount)
    repo.touch_sync_ts()
    return row


def update_saving(repo: Repo, entry_id: int, account: str, amount: float, label: str) -> dict:
    old, mo = entry_with_month(repo, "savings", entry_id)
    if mo.get("closed"):
        raise HTTPException(409, "Ce mois est clôturé : saisie verrouillée.")
    y, m = mo["year"], mo["month"]
    linked = old.get("linked_asset_name") or ""
    if old["account"] != account:
        if linked:
            apply_saving_to_asset(repo, y, m, linked, -old["amount"])
        matched = match_compte_asset(account, assets_current(repo))
        linked = matched["asset_name"] if matched else ""
        if linked:
            apply_saving_to_asset(repo, y, m, linked, amount)
    elif linked and old["amount"] != amount:
        apply_saving_to_asset(repo, y, m, linked, amount - old["amount"])
    row = repo.update("savings", {"id": f"eq.{entry_id}"},
                      {"account": account, "amount": amount, "label": label,
                       "linked_asset_name": linked})[0]
    repo.touch_sync_ts()
    return row


def delete_entry(repo: Repo, table: str, entry_id: int) -> dict:
    entry, mo = entry_with_month(repo, table, entry_id)
    if mo.get("closed"):
        raise HTTPException(409, "Ce mois est clôturé : saisie verrouillée.")
    repo.delete(table, {"id": f"eq.{entry_id}"})
    if table == "savings" and entry.get("linked_asset_name"):
        apply_saving_to_asset(repo, mo["year"], mo["month"], entry["linked_asset_name"],
                              -entry["amount"])
    repo.touch_sync_ts()
    return {"year": mo["year"], "month": mo["month"]}


# ── Budgets ──────────────────────────────────────────────────

def set_budget(repo: Repo, year: int, month: int, category: str, amount: float) -> None:
    existing = repo.select("budgets", {"year": f"eq.{year}", "month": f"eq.{month}",
                                       "category": f"eq.{category}"}, limit=1)
    if amount <= 0:
        if existing:
            repo.delete("budgets", {"id": f"eq.{existing[0]['id']}"})
    elif existing:
        repo.update("budgets", {"id": f"eq.{existing[0]['id']}"}, {"amount": amount})
    else:
        repo.insert("budgets", {"year": year, "month": month, "category": category,
                                "amount": amount})
    repo.touch_sync_ts()


def copy_budgets(repo: Repo, year: int, month: int) -> int:
    py, pm = shift_month(year, month, -1)
    prev = repo.select("budgets", {"year": f"eq.{py}", "month": f"eq.{pm}"})
    for b in prev:
        set_budget(repo, year, month, b["category"], b["amount"])
    return len(prev)


# ── Contexte agrégé pour l'IA (jamais les lignes brutes) ─────

def ai_context(repo: Repo, year: int, month: int, nb_months: int) -> dict:
    periods = [shift_month(year, month, -i) for i in range(nb_months - 1, -1, -1)]
    rows = repo.select("months", {"year": in_filter(sorted({p[0] for p in periods}))})
    months = [m for m in rows if (m["year"], m["month"]) in set(periods)]
    ids = [m["id"] for m in months]
    cats = {c["id"]: c["name"] for c in categories(repo)}
    exp = repo.rows_for_months("expenses", ids, "month_id,category_id,amount,label,payee")
    rev = repo.rows_for_months("revenues", ids, "month_id,source,amount")
    sav = repo.rows_for_months("savings", ids, "month_id,amount")
    n = max(len(months), 1)

    by_cat: dict[str, float] = defaultdict(float)
    by_label: dict[str, float] = defaultdict(float)
    by_payee: dict[str, float] = defaultdict(float)
    for e in exp:
        by_cat[cats.get(e["category_id"], "?")] += e["amount"]
        key = (e.get("label") or "").strip() or (e.get("payee") or "").strip()
        if key:
            by_label[key] += e["amount"]
        if e.get("payee"):
            by_payee[e["payee"]] += e["amount"]
    by_src: dict[str, float] = defaultdict(float)
    for r in rev:
        by_src[r["source"]] += r["amount"]

    per_month = []
    mid_to_month = {m["id"]: m for m in months}
    for m in sorted(months, key=lambda x: (x["year"], x["month"])):
        per_month.append({
            "period": f"{m['year']}-{m['month']:02d}",
            "rev": round(sum(r["amount"] for r in rev if r["month_id"] == m["id"]), 2),
            "exp": round(sum(e["amount"] for e in exp if e["month_id"] == m["id"]), 2),
            "sav": round(sum(s["amount"] for s in sav if s["month_id"] == m["id"]), 2),
        })

    def top(d: dict, k: int) -> list[dict]:
        return [{"name": name, "per_month": round(v / n, 2)}
                for name, v in sorted(d.items(), key=lambda kv: -kv[1])[:k]]

    # Budgets du mois courant à partir des dépenses déjà chargées (pas de
    # second aller-retour via month_summary).
    cur_ids = {m["id"] for m in months if (m["year"], m["month"]) == (year, month)}
    spent_cur: dict[str, float] = defaultdict(float)
    for e in exp:
        if e["month_id"] in cur_ids:
            spent_cur[cats.get(e["category_id"], "?")] += e["amount"]
    budgets_cur = budget_status(repo, year, month, spent_cur)
    pat = patrimoine(repo)
    an = analytics(repo, year, month, months=1)
    return {
        "period_end": f"{year}-{month:02d}", "months_with_data": len(mid_to_month),
        "per_month": per_month,
        "top_categories": top(by_cat, 8), "top_expenses": top(by_label, 8),
        "top_payees": top(by_payee, 8), "revenue_sources": top(by_src, 5),
        "current_month_budgets": [{k: round(v, 2) if isinstance(v, float) else v
                                   for k, v in b.items()} for b in budgets_cur],
        "patrimoine": {"by_type": pat["by_type"], "net_worth": round(pat["net_worth"], 2),
                       "liabilities_total": round(pat["total_liabilities"], 2)},
        # Signaux déjà calculés (seuils prudents) : l'IA s'appuie dessus au
        # lieu de deviner ce qui est « inhabituel ».
        "unusual_this_month": {k: an[k] for k in ("unusual", "large_expenses")},
    }


# ── Saisie groupée (atomique) ────────────────────────────────

def add_expenses_batch(repo: Repo, year: int, month: int, rows: list[dict]) -> tuple[list[dict], list[BudgetCheck]]:
    """rows : [{category_id, amount, label, payee}]. Une seule insertion
    PostgREST : tout ou rien. Renvoie aussi le bilan budget par catégorie."""
    mo = ensure_open(repo, year, month)
    cats = {c["id"]: c["name"] for c in categories(repo)}
    unknown = sorted({r["category_id"] for r in rows} - set(cats))
    if unknown:
        raise HTTPException(422, f"Catégorie inconnue : {unknown[0]}.")
    used = sorted({r["category_id"] for r in rows})
    before = {cid: _spent(repo, mo["id"], cid) for cid in used}
    created = repo.insert_many("expenses", [
        {"month_id": mo["id"], "category_id": r["category_id"], "amount": r["amount"],
         "label": r.get("label", ""), "payee": (r.get("payee") or "").strip().upper()}
        for r in rows])
    repo.touch_sync_ts()
    added: dict[int, float] = defaultdict(float)
    for r in rows:
        added[r["category_id"]] += r["amount"]
    checks = [BudgetCheck(cats[cid], year, month, _budget_amount(repo, year, month, cats[cid]),
                          before[cid], before[cid] + added[cid]) for cid in used]
    return created, checks


def add_revenues_batch(repo: Repo, year: int, month: int, rows: list[dict]) -> list[dict]:
    mo = ensure_open(repo, year, month)
    created = repo.insert_many("revenues", [
        {"month_id": mo["id"], "source": r["source"], "amount": r["amount"], "label": r.get("label", "")}
        for r in rows])
    repo.touch_sync_ts()
    return created


# ── Transactions récurrentes (même règle que l'app desktop) ──
# « En attente » pour un mois = active ET pas déjà appliquée CE mois-là.

def recurring(repo: Repo, year: int, month: int) -> list[dict]:
    cats = {c["id"]: c["name"] for c in categories(repo)}
    out = []
    for r in repo.select("recurring_transactions"):
        r["category"] = cats.get(r.get("category_id"), "")
        r["pending"] = bool(r.get("active")) and not (
            r.get("last_applied_year") == year and r.get("last_applied_month") == month)
        out.append(r)
    return sorted(out, key=lambda r: (r["type"], r["label"].lower()))


def add_recurring(repo: Repo, data: dict) -> dict:
    if data["type"] == "expense":
        category_id_or_404(repo, data["category_id"])
    row = repo.insert("recurring_transactions", {
        "label": data["label"], "amount": data["amount"], "type": data["type"],
        "category_id": data.get("category_id") if data["type"] == "expense" else None,
        "source": data.get("source", "") if data["type"] == "revenue" else "",
        "payee": (data.get("payee") or "").strip().upper() if data["type"] == "expense" else "",
        "active": 1, "last_applied_year": 0, "last_applied_month": 0})
    repo.touch_sync_ts()
    return row


def set_recurring_active(repo: Repo, rec_id: int, active: bool) -> dict:
    rows = repo.update("recurring_transactions", {"id": f"eq.{rec_id}"}, {"active": int(active)})
    if not rows:
        raise HTTPException(404, "Récurrente introuvable.")
    repo.touch_sync_ts()
    return rows[0]


def delete_recurring(repo: Repo, rec_id: int) -> None:
    if not repo.delete("recurring_transactions", {"id": f"eq.{rec_id}"}):
        raise HTTPException(404, "Récurrente introuvable.")
    repo.touch_sync_ts()


def apply_recurring(repo: Repo, year: int, month: int, items: list[dict]) -> tuple[int, list[BudgetCheck]]:
    """items : [{id, amount}]. Toutes doivent être en attente pour ce mois ;
    les écritures de chaque type partent en une insertion groupée."""
    by_id = {r["id"]: r for r in recurring(repo, year, month)}
    expenses, revenues = [], []
    for it in items:
        r = by_id.get(it["id"])
        if r is None:
            raise HTTPException(404, "Récurrente introuvable.")
        if not r["pending"]:
            raise HTTPException(409, f"« {r['label']} » est déjà appliquée ce mois-ci (ou inactive).")
        if r["type"] == "expense":
            if not r.get("category_id"):
                raise HTTPException(422, f"« {r['label']} » n'a pas de catégorie.")
            expenses.append({"category_id": r["category_id"], "amount": it["amount"],
                             "label": r["label"], "payee": r.get("payee") or ""})
        else:
            revenues.append({"source": r.get("source") or r["label"], "amount": it["amount"],
                             "label": r["label"]})
    checks: list[BudgetCheck] = []
    if expenses:
        _, checks = add_expenses_batch(repo, year, month, expenses)
    if revenues:
        add_revenues_batch(repo, year, month, revenues)
    for it in items:
        repo.update("recurring_transactions", {"id": f"eq.{it['id']}"},
                    {"last_applied_year": year, "last_applied_month": month})
    repo.touch_sync_ts()
    return len(items), checks


# ── Recherche dans tout l'historique ─────────────────────────

def _like(text: str) -> str:
    # Jokers et séparateurs PostgREST neutralisés : la saisie reste du texte.
    cleaned = "".join(ch for ch in text if ch not in "*,()\\\"")
    return f"*{cleaned}*"


def search(repo: Repo, kind: str, q: str = "", category_id: int | None = None,
           min_amount: float | None = None, max_amount: float | None = None,
           limit: int = 200) -> list[dict]:
    table = ENTRY_TABLES[kind]
    filters: dict = {}
    q = q.strip()
    if q:
        pattern = _like(q)
        fields = {"expenses": ("label", "payee"), "revenues": ("source", "label"),
                  "savings": ("account", "label")}[kind]
        filters["or"] = "(" + ",".join(f"{f}.ilike.{pattern}" for f in fields) + ")"
    if category_id is not None and kind == "expenses":
        filters["category_id"] = f"eq.{category_id}"
    if min_amount is not None:
        filters["amount"] = f"gte.{min_amount}"
    rows = repo.select(table, filters, order="id.desc", limit=2000)
    if max_amount is not None:                     # deux bornes sur la même colonne
        rows = [r for r in rows if r["amount"] <= max_amount]
    months = repo.months_by_id(r["month_id"] for r in rows)
    cats = {c["id"]: c["name"] for c in categories(repo)} if kind == "expenses" else {}
    out = []
    for r in rows:
        mo = months.get(r["month_id"])
        if mo is None:
            continue
        r["year"], r["month"] = mo["year"], mo["month"]
        if kind == "expenses":
            r["category"] = cats.get(r["category_id"], "?")
        out.append(r)
    out.sort(key=lambda r: (r["year"], r["month"], r["id"]), reverse=True)
    return out[:limit]


# ── Analyses : tendances, comparaisons, dépenses inhabituelles ──
# Référence = les 6 mois précédents AYANT des données (un mois absent n'est
# pas compté comme un mois à 0 €). Seuils volontairement prudents : une
# alerte doit être rare pour rester utile.
REF_MONTHS = 6
UNUSUAL_RATIO = 1.5            # catégorie : mois courant ≥ 1,5 × la moyenne…
UNUSUAL_MIN_DIFF = 30.0        # … et au moins 30 € au-dessus
UNUSUAL_MIN_HISTORY = 3        # mois de référence avec données, au minimum
LARGE_RATIO = 3.0              # dépense isolée ≥ 3 × la médiane de sa catégorie…
LARGE_MIN_AMOUNT = 50.0        # … et ≥ 50 €
LARGE_MIN_SAMPLES = 5          # dépenses de référence, au minimum


def _period_months(repo: Repo, periods: set[tuple[int, int]]) -> dict[tuple[int, int], dict]:
    rows = repo.select("months", {"year": in_filter(sorted({p[0] for p in periods}))})
    return {(m["year"], m["month"]): m for m in rows if (m["year"], m["month"]) in periods}


def analytics(repo: Repo, year: int, month: int, months: int = 12) -> dict:
    cur = (year, month)
    periods = [shift_month(year, month, -i) for i in range(months - 1, -1, -1)]
    ref = [shift_month(year, month, -i) for i in range(1, REF_MONTHS + 1)]
    yoy = (year - 1, month)
    mo = _period_months(repo, set(periods) | set(ref) | {yoy})
    id2p = {m["id"]: p for p, m in mo.items()}
    ids = sorted(id2p)
    cats = {c["id"]: c["name"] for c in categories(repo)}
    exp = repo.rows_for_months("expenses", ids, "id,month_id,category_id,amount,label,payee")
    totals: dict[str, dict[tuple[int, int], float]] = {
        k: defaultdict(float) for k in ("rev", "exp", "sav")}
    for table, key in (("revenues", "rev"), ("savings", "sav")):
        for r in repo.rows_for_months(table, ids, "month_id,amount"):
            totals[key][id2p[r["month_id"]]] += r["amount"]
    by_cat: dict[str, dict[tuple[int, int], float]] = defaultdict(lambda: defaultdict(float))
    samples: dict[str, list[float]] = defaultdict(list)       # dépenses de référence
    months_with_exp: set[tuple[int, int]] = set()
    for e in exp:
        p = id2p[e["month_id"]]
        name = cats.get(e["category_id"], "?")
        by_cat[name][p] += e["amount"]
        totals["exp"][p] += e["amount"]
        months_with_exp.add(p)
        if p in ref:
            samples[name].append(e["amount"])
    ref_data = [p for p in ref if p in months_with_exp]
    n_ref = len(ref_data)

    rows, unusual = [], []
    for name, series in by_cat.items():
        avg = sum(series[p] for p in ref_data) / n_ref if n_ref else 0.0
        c = series[cur]
        row = {"category": name, "current": round(c, 2), "prev": round(series[ref[0]], 2),
               "yoy": round(series[yoy], 2), "average": round(avg, 2),
               "series": [round(series[p], 2) for p in periods]}
        if not any(row["series"]) and not row["yoy"]:
            continue
        row["unusual"] = (n_ref >= UNUSUAL_MIN_HISTORY and c >= avg * UNUSUAL_RATIO
                          and c - avg >= UNUSUAL_MIN_DIFF)
        if row["unusual"]:
            unusual.append({"category": name, "spent": row["current"], "average": row["average"],
                            "ratio": round(c / avg, 2) if avg else None})
        rows.append(row)
    rows.sort(key=lambda r: (-r["current"], -r["average"], r["category"]))
    unusual.sort(key=lambda u: -(u["spent"] - u["average"]))

    large = []
    for e in exp:
        if id2p[e["month_id"]] != cur:
            continue
        name = cats.get(e["category_id"], "?")
        ref_samples = samples.get(name, [])
        if len(ref_samples) < LARGE_MIN_SAMPLES:
            continue
        med = statistics.median(ref_samples)
        if e["amount"] >= LARGE_MIN_AMOUNT and e["amount"] >= LARGE_RATIO * med:
            large.append({"id": e["id"], "category": name, "amount": round(e["amount"], 2),
                          "label": e.get("label") or "", "payee": e.get("payee") or "",
                          "median": round(med, 2)})
    large.sort(key=lambda x: -x["amount"])

    def total(key: str, p: tuple[int, int]) -> float | None:
        return round(totals[key][p], 2) if p in mo else None

    return {
        "year": year, "month": month, "reference_months": n_ref,
        "per_month": [{"year": p[0], "month": p[1], "rev": round(totals["rev"][p], 2),
                       "exp": round(totals["exp"][p], 2), "sav": round(totals["sav"][p], 2)}
                      for p in periods],
        "totals": {k: {"current": total(k, cur), "prev": total(k, ref[0]), "yoy": total(k, yoy),
                       "average": round(sum(totals[k][p] for p in ref_data) / n_ref, 2)
                       if n_ref else None}
                   for k in ("rev", "exp", "sav")},
        "categories": rows, "unusual": unusual, "large_expenses": large[:10],
    }
