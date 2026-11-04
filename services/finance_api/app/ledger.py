"""
ledger.py — Règles métier de finance-api (portage de database.py) :
saisies, synchronisation Épargne → Patrimoine, budgets, agrégats.
"""
from __future__ import annotations

import logging
from collections import defaultdict

from fastapi import HTTPException

from .repo import Repo, in_filter

log = logging.getLogger(__name__)

ENTRY_TABLES = {"expenses": "expenses", "revenues": "revenues", "savings": "savings"}
_MIN_MATCH_LEN = 3


def _shift(y: int, m: int, delta: int) -> tuple[int, int]:
    idx = y * 12 + (m - 1) + delta
    return idx // 12, idx % 12 + 1


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

def add_expense(repo: Repo, year: int, month: int, category_id: int, amount: float,
                label: str, payee: str) -> dict:
    mo = ensure_open(repo, year, month)
    category_id_or_404(repo, category_id)
    row = repo.insert("expenses", {"month_id": mo["id"], "category_id": category_id,
                                   "amount": amount, "label": label,
                                   "payee": payee.strip().upper()})
    repo.touch_sync_ts()
    return row


def update_expense(repo: Repo, entry_id: int, category_id: int, amount: float,
                   label: str, payee: str) -> dict:
    entry, mo = entry_with_month(repo, "expenses", entry_id)
    if mo.get("closed"):
        raise HTTPException(409, "Ce mois est clôturé : saisie verrouillée.")
    category_id_or_404(repo, category_id)
    row = repo.update("expenses", {"id": f"eq.{entry_id}"},
                      {"category_id": category_id, "amount": amount, "label": label,
                       "payee": payee.strip().upper()})[0]
    repo.touch_sync_ts()
    return row


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
    py, pm = _shift(year, month, -1)
    prev = repo.select("budgets", {"year": f"eq.{py}", "month": f"eq.{pm}"})
    for b in prev:
        set_budget(repo, year, month, b["category"], b["amount"])
    return len(prev)


def category_spend(repo: Repo, year: int, month: int, category_id: int) -> tuple[str, float, float]:
    """(nom catégorie, dépensé ce mois, budget) — pour les alertes."""
    cat = category_id_or_404(repo, category_id)
    mo = repo.month(year, month, create=False)
    spent = 0.0
    if mo:
        spent = sum(r["amount"] for r in repo.select(
            "expenses", {"month_id": f"eq.{mo['id']}", "category_id": f"eq.{category_id}"},
            columns="amount"))
    b = repo.select("budgets", {"year": f"eq.{year}", "month": f"eq.{month}",
                                "category": f"eq.{cat['name']}"}, limit=1)
    return cat["name"], spent, (b[0]["amount"] if b else 0.0)


# ── Contexte agrégé pour l'IA (jamais les lignes brutes) ─────

def ai_context(repo: Repo, year: int, month: int, nb_months: int) -> dict:
    periods = [_shift(year, month, -i) for i in range(nb_months - 1, -1, -1)]
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

    cur = month_summary(repo, year, month)
    pat = patrimoine(repo)
    return {
        "period_end": f"{year}-{month:02d}", "months_with_data": len(mid_to_month),
        "per_month": per_month,
        "top_categories": top(by_cat, 8), "top_expenses": top(by_label, 8),
        "top_payees": top(by_payee, 8), "revenue_sources": top(by_src, 5),
        "current_month_budgets": [{k: round(v, 2) if isinstance(v, float) else v
                                   for k, v in b.items()} for b in cur["budgets"]],
        "patrimoine": {"by_type": pat["by_type"], "net_worth": round(pat["net_worth"], 2),
                       "liabilities_total": round(pat["total_liabilities"], 2)},
    }
