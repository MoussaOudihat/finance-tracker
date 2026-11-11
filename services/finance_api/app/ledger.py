"""
ledger.py — Règles métier de finance-api (portage de database.py) :
saisies, synchronisation Épargne → Patrimoine, budgets, agrégats.

Chaque écriture construit une liste d'opérations exécutée en UNE
transaction par Repo.apply (voir repo.py) : pas d'état intermédiaire
visible ni de demi-écriture en cas de panne.
"""
from __future__ import annotations

import logging
import statistics
from collections import defaultdict
from dataclasses import dataclass
from datetime import date

from fastapi import HTTPException

from fintrack_common.fmt import shift_month

from .repo import CLOSED_MSG, Repo, in_filter, ref

log = logging.getLogger(__name__)

ENTRY_TABLES = {"expenses": "expenses", "revenues": "revenues", "savings": "savings"}
_MIN_MATCH_LEN = 3
ASSET_KEY = ["year", "month", "asset_type", "asset_name"]
LIABILITY_KEY = ["year", "month", "liability_name"]
BUDGET_KEY = ["year", "month", "category"]


# ── Mois / clôture ───────────────────────────────────────────

def open_month_op(year: int, month: int) -> dict:
    """Crée le mois si besoin et refuse l'écriture s'il est clôturé — dans
    la transaction (pas de course avec une clôture simultanée)."""
    return {"op": "month", "year": year, "month": month, "require_open": True}


def assert_open_op(mo: dict) -> dict:
    return {"op": "assert_open", "month_id": mo["id"]}


def existing_month(repo: Repo, year: int, month: int) -> dict | None:
    """Mois existant (ou None), refusé tout de suite s'il est clôturé : le
    message arrive avant tout calcul. La vérification qui fait foi reste
    celle de la transaction."""
    mo = repo.month(year, month)
    if mo and mo.get("closed"):
        raise HTTPException(409, CLOSED_MSG)
    return mo


def _require_open(mo: dict) -> None:
    if mo.get("closed"):
        raise HTTPException(409, CLOSED_MSG)


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
    """Lues une fois par requête (contexte IA, analyses, saisies groupées…
    les demandaient chacun)."""
    rows = repo.cached("categories", lambda: sorted(
        repo.select("categories", columns="id,name,is_default"), key=lambda c: c["name"]))
    return [dict(c) for c in rows]


def category_id_or_404(repo: Repo, cat_id: int) -> dict:
    rows = repo.select("categories", {"id": f"eq.{cat_id}"}, limit=1)
    if not rows:
        raise HTTPException(422, "Catégorie inconnue.")
    return rows[0]


# ── Lecture d'un mois ────────────────────────────────────────

def month_entries(repo: Repo, year: int, month: int) -> dict:
    mo = repo.month(year, month)
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


def months_with_entries(repo: Repo, month_ids: list[int]) -> set[int]:
    """Mois qui contiennent au moins une saisie : une ligne `months` survit
    à la suppression de ses saisies (et la clôture en crée une vide)."""
    used: set[int] = set()
    for table in ENTRY_TABLES.values():
        used.update(r["month_id"] for r in repo.rows_for_months(table, month_ids, "month_id"))
    return used


def last_month(repo: Repo, today: date | None = None) -> dict | None:
    """Dernier mois NON VIDE et non futur : mois affiché par défaut. Une
    saisie de test datée de 2030 ou un mois vidé ne doivent pas s'imposer."""
    t = today or date.today()
    candidates = [m for m in repo.select("months", order="year.desc,month.desc", limit=60)
                  if (m["year"], m["month"]) <= (t.year, t.month)]
    used = months_with_entries(repo, [m["id"] for m in candidates])
    return next(({"year": m["year"], "month": m["month"]}
                 for m in candidates if m["id"] in used), None)


def set_month_closed(repo: Repo, year: int, month: int, closed: bool) -> dict:
    repo.apply([{"op": "month", "year": year, "month": month},
                {"op": "update", "table": "months", "where": {"id": ref(0)},
                 "set": {"closed": 1 if closed else 0}}])
    return {"year": year, "month": month, "closed": closed}


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
    """Dernier instantané de chaque actif. Lu une seule fois par requête
    (patrimoine, épargne, contexte IA le demandent chacun)."""
    def load() -> list[dict]:
        latest: dict[tuple[str, str], dict] = {}
        for a in repo.select("assets"):
            k = (a["asset_type"], a["asset_name"])
            if k not in latest or (a["year"], a["month"]) > (latest[k]["year"], latest[k]["month"]):
                latest[k] = a
        return sorted(latest.values(), key=lambda a: (a["asset_type"], a["asset_name"]))
    return [dict(a) for a in repo.cached("assets_current", load)]


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


def saving_asset_ops(year: int, month: int, deltas: dict[str, float]) -> list[dict]:
    """Ajustements des comptes liés : UNE opération par compte (variations
    d'un même compte cumulées). La nouvelle valeur est calculée PAR LA BASE,
    dans la transaction et sous le verrou de l'utilisateur, à partir du
    dernier instantané : deux versements simultanés s'additionnent (une
    valeur absolue calculée ici, avant la transaction, faisait perdre l'un
    des deux)."""
    return [{"op": "adjust_asset", "asset_name": name, "year": year, "month": month,
             "delta": delta}
            for name, delta in deltas.items() if name and delta]


# ── Patrimoine : saisie (instantanés mensuels, comme le desktop) ──

def _latest(rows: list[dict]) -> dict | None:
    return max(rows, key=lambda r: (r["year"], r["month"]), default=None)


def set_asset_value(repo: Repo, year: int, month: int, asset_type: str, name: str,
                    value: float, cost_basis: float | None, notes: str | None) -> dict:
    """Valeur d'un actif pour un mois : met à jour l'instantané du mois ou en
    crée un (l'historique des mois précédents est conservé). Montant investi
    et notes repris du dernier instantané s'ils ne sont pas fournis."""
    snaps = repo.select("assets", {"asset_type": f"eq.{asset_type}",
                                   "asset_name": f"eq.{name}"})
    prev = _latest(snaps)
    values = {"value": value,
              "cost_basis": cost_basis if cost_basis is not None
              else (prev or {}).get("cost_basis") or 0.0,
              "notes": notes if notes is not None else (prev or {}).get("notes") or ""}
    return repo.apply([{"op": "upsert", "table": "assets", "conflict": ASSET_KEY,
                        "row": {"year": year, "month": month, "asset_type": asset_type,
                                "asset_name": name, **values}}])[0]


def delete_asset(repo: Repo, asset_type: str, name: str) -> int:
    """Arrête le suivi d'un actif : supprime tous ses instantanés."""
    gone = repo.apply([{"op": "delete", "table": "assets",
                        "where": {"asset_type": asset_type, "asset_name": name}}])[0]
    if not gone:
        raise HTTPException(404, "Actif introuvable.")
    return len(gone)


def set_liability(repo: Repo, year: int, month: int, liability_type: str, name: str,
                  remaining_capital: float, monthly_payment: float | None,
                  end_date: str | None) -> dict:
    snaps = repo.select("liabilities", {"liability_name": f"eq.{name}"})
    prev = _latest(snaps) or {}
    values = {"liability_type": liability_type, "remaining_capital": remaining_capital,
              "monthly_payment": monthly_payment if monthly_payment is not None
              else prev.get("monthly_payment") or 0.0,
              "end_date": end_date if end_date is not None else prev.get("end_date") or "",
              "notes": prev.get("notes") or ""}
    return repo.apply([{"op": "upsert", "table": "liabilities", "conflict": LIABILITY_KEY,
                        "row": {"year": year, "month": month, "liability_name": name,
                                **values}}])[0]


def delete_liability(repo: Repo, name: str) -> int:
    gone = repo.apply([{"op": "delete", "table": "liabilities",
                        "where": {"liability_name": name}}])[0]
    if not gone:
        raise HTTPException(404, "Passif introuvable.")
    return len(gone)


# ── Vue d'ensemble de l'épargne ──────────────────────────────

def savings_overview(repo: Repo, year: int, month: int, months: int = 12) -> dict:
    periods = [shift_month(year, month, -i) for i in range(months - 1, -1, -1)]
    mo = _period_months(repo, set(periods))
    id2p = {m["id"]: p for p, m in mo.items()}
    ids = sorted(id2p)
    sav = repo.rows_for_months("savings", ids, "month_id,account,amount")
    rev = repo.rows_for_months("revenues", ids, "month_id,amount")
    exp_months = {r["month_id"] for r in repo.rows_for_months("expenses", ids, "month_id")}
    s_by_p: dict[tuple[int, int], float] = defaultdict(float)
    r_by_p: dict[tuple[int, int], float] = defaultdict(float)
    by_account: dict[str, float] = defaultdict(float)
    for s in sav:
        s_by_p[id2p[s["month_id"]]] += s["amount"]
        by_account[(s.get("account") or "").strip() or "Sans compte"] += s["amount"]
    for r in rev:
        r_by_p[id2p[r["month_id"]]] += r["amount"]
    active = {id2p[i] for i in exp_months} | set(s_by_p) | set(r_by_p)   # mois saisis

    def rate(s: float, r: float) -> float | None:
        return round(s / r * 100, 1) if r > 0 else None

    per_month = [{"year": p[0], "month": p[1], "sav": round(s_by_p[p], 2),
                  "rev": round(r_by_p[p], 2), "rate": rate(s_by_p[p], r_by_p[p]),
                  "has_data": p in active} for p in periods]
    total_s, total_r = sum(s_by_p.values()), sum(r_by_p.values())
    n = len(active)
    accounts = [a for a in assets_current(repo) if a["asset_type"] == "compte"]
    goals = []
    for g in repo.select("savings_goals"):
        target = g.get("target_amount") or 0
        cur = g.get("current_amount") or 0
        goals.append({**g, "pct": round(min(cur / target * 100, 100), 1) if target > 0 else None})
    return {
        "year": year, "month": month, "months": months, "months_with_data": n,
        "per_month": per_month,
        "total": round(total_s, 2), "average": round(total_s / n, 2) if n else None,
        "rate": rate(total_s, total_r),
        "by_account": [{"account": k, "total": round(v, 2)}
                       for k, v in sorted(by_account.items(), key=lambda kv: -kv[1])],
        "accounts": accounts, "accounts_total": round(sum(a["value"] for a in accounts), 2),
        "goals": goals,
    }


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


def _expense_row(r: dict, month_ref) -> dict:
    return {"month_id": month_ref, "category_id": r["category_id"], "amount": r["amount"],
            "label": r.get("label", ""), "payee": (r.get("payee") or "").strip().upper()}


def _budget_checks(repo: Repo, year: int, month: int, mo: dict | None,
                   rows: list[dict], cats: dict[int, str]) -> list[BudgetCheck]:
    """Dépense par catégorie avant / après l'ajout de `rows` (alertes)."""
    added: dict[int, float] = defaultdict(float)
    for r in rows:
        added[r["category_id"]] += r["amount"]
    checks = []
    for cid in sorted(added):
        before = _spent(repo, mo["id"], cid) if mo else 0.0
        checks.append(BudgetCheck(cats[cid], year, month,
                                  _budget_amount(repo, year, month, cats[cid]),
                                  before, before + added[cid]))
    return checks


def add_expense(repo: Repo, year: int, month: int, category_id: int, amount: float,
                label: str, payee: str) -> tuple[dict, BudgetCheck]:
    cat = category_id_or_404(repo, category_id)
    mo = existing_month(repo, year, month)
    row_in = {"category_id": category_id, "amount": amount, "label": label, "payee": payee}
    [chk] = _budget_checks(repo, year, month, mo, [row_in], {category_id: cat["name"]})
    res = repo.apply([open_month_op(year, month),
                      {"op": "insert", "table": "expenses", "row": _expense_row(row_in, ref(0))}])
    return res[1], chk


def update_expense(repo: Repo, entry_id: int, category_id: int, amount: float,
                   label: str, payee: str) -> tuple[dict, BudgetCheck]:
    entry, mo = entry_with_month(repo, "expenses", entry_id)
    _require_open(mo)
    cat = category_id_or_404(repo, category_id)
    current = _spent(repo, mo["id"], category_id)        # inclut l'ancienne ligne si même catégorie
    before = current
    after = current - (entry["amount"] if entry["category_id"] == category_id else 0) + amount
    res = repo.apply([assert_open_op(mo),
                      {"op": "update", "table": "expenses", "where": {"id": entry_id}, "require": True,
                       "set": {"category_id": category_id, "amount": amount, "label": label,
                               "payee": payee.strip().upper()}}])
    return res[1][0], BudgetCheck(cat["name"], mo["year"], mo["month"],
                                  _budget_amount(repo, mo["year"], mo["month"], cat["name"]),
                                  before, after)


def add_revenue(repo: Repo, year: int, month: int, source: str, amount: float,
                label: str) -> dict:
    return repo.apply([open_month_op(year, month),
                       {"op": "insert", "table": "revenues",
                        "row": {"month_id": ref(0), "source": source, "amount": amount,
                                "label": label}}])[1]


def update_revenue(repo: Repo, entry_id: int, source: str, amount: float, label: str) -> dict:
    _, mo = entry_with_month(repo, "revenues", entry_id)
    _require_open(mo)
    return repo.apply([assert_open_op(mo),
                       {"op": "update", "table": "revenues", "where": {"id": entry_id},
                        "require": True,
                        "set": {"source": source, "amount": amount, "label": label}}])[1][0]


def add_saving(repo: Repo, year: int, month: int, account: str, amount: float,
               label: str) -> dict:
    """Versement + ajustement du compte lié (patrimoine) : même transaction."""
    assets = assets_current(repo)
    matched = match_compte_asset(account, assets)
    linked = matched["asset_name"] if matched else ""
    ops = [open_month_op(year, month),
           {"op": "insert", "table": "savings",
            "row": {"month_id": ref(0), "account": account, "amount": amount,
                    "label": label, "linked_asset_name": linked}}]
    ops += saving_asset_ops(year, month, {linked: amount})
    return repo.apply(ops)[1]


def update_saving(repo: Repo, entry_id: int, account: str, amount: float, label: str) -> dict:
    old, mo = entry_with_month(repo, "savings", entry_id)
    _require_open(mo)
    assets = assets_current(repo)
    linked = old.get("linked_asset_name") or ""
    deltas: dict[str, float] = defaultdict(float)
    if old["account"] != account:
        deltas[linked] -= old["amount"]
        matched = match_compte_asset(account, assets)
        linked = matched["asset_name"] if matched else ""
        deltas[linked] += amount
    elif linked:
        deltas[linked] += amount - old["amount"]
    ops = [assert_open_op(mo),
           *saving_asset_ops(mo["year"], mo["month"], deltas),
           {"op": "update", "table": "savings", "where": {"id": entry_id}, "require": True,
            "set": {"account": account, "amount": amount, "label": label,
                    "linked_asset_name": linked}}]
    return repo.apply(ops)[-1][0]


def delete_entry(repo: Repo, table: str, entry_id: int) -> dict:
    entry, mo = entry_with_month(repo, table, entry_id)
    _require_open(mo)
    ops = [assert_open_op(mo),
           {"op": "delete", "table": table, "where": {"id": entry_id}, "require": True}]
    if table == "savings" and entry.get("linked_asset_name"):
        ops += saving_asset_ops(mo["year"], mo["month"],
                                {entry["linked_asset_name"]: -entry["amount"]})
    repo.apply(ops)
    return {"year": mo["year"], "month": mo["month"]}


# ── Budgets ──────────────────────────────────────────────────

def _budget_op(year: int, month: int, category: str, amount: float) -> dict:
    if amount <= 0:                 # 0 = suppression du plafond
        return {"op": "delete", "table": "budgets",
                "where": {"year": year, "month": month, "category": category}}
    return {"op": "upsert", "table": "budgets", "conflict": BUDGET_KEY,
            "row": {"year": year, "month": month, "category": category, "amount": amount}}


def set_budget(repo: Repo, year: int, month: int, category: str, amount: float) -> None:
    repo.apply([_budget_op(year, month, category, amount)])


def copy_budgets(repo: Repo, year: int, month: int) -> int:
    """Tous les plafonds du mois précédent, en une transaction."""
    py, pm = shift_month(year, month, -1)
    prev = repo.select("budgets", {"year": f"eq.{py}", "month": f"eq.{pm}"})
    if prev:
        repo.apply([_budget_op(year, month, b["category"], b["amount"]) for b in prev])
    return len(prev)


# ── Contexte agrégé pour l'IA (jamais les lignes brutes) ─────

AI_LOOKBACK = 24          # mois parcourus pour trouver les N derniers mois saisis


def ai_context(repo: Repo, year: int, month: int, nb_months: int,
               today: date | None = None) -> dict:
    """Résumé agrégé des `nb_months` derniers mois SAISIS jusqu'à year/month.

    - les mois sans aucune saisie sont écartés (et signalés), ils ne
      faussent plus les moyennes ;
    - le mois calendaire en cours est « partiel » : affiché à part, exclu
      des moyennes (sauf s'il est le seul mois disponible) ;
    - jamais de mois futur.
    """
    t = today or date.today()
    cur_cal = (t.year, t.month)
    end = min((year, month), cur_cal)
    lookback = [shift_month(end[0], end[1], -i) for i in range(AI_LOOKBACK)]
    mo = _period_months(repo, set(lookback))
    id2p = {m["id"]: p for p, m in mo.items()}
    ids = sorted(id2p)
    cats = {c["id"]: c["name"] for c in categories(repo)}
    exp = repo.rows_for_months("expenses", ids, "month_id,category_id,amount,label,payee")
    rev = repo.rows_for_months("revenues", ids, "month_id,source,amount")
    sav = repo.rows_for_months("savings", ids, "month_id,account,amount")
    filled = {id2p[r["month_id"]] for r in (*exp, *rev, *sav)}

    chosen = sorted([p for p in lookback if p in filled][:nb_months])
    partial = {p for p in chosen if p == cur_cal}
    basis = [p for p in chosen if p not in partial] or chosen      # base des moyennes
    n = max(len(basis), 1)
    in_basis = set(basis)
    skipped = [p for p in lookback if chosen and chosen[0] <= p <= end and p not in filled]

    def fmt(p: tuple[int, int]) -> str:
        return f"{p[0]}-{p[1]:02d}"

    by_cat: dict[str, float] = defaultdict(float)
    by_label: dict[str, float] = defaultdict(float)
    by_payee: dict[str, float] = defaultdict(float)
    cat_month: dict[tuple[int, int], dict[str, float]] = defaultdict(lambda: defaultdict(float))
    tot: dict[str, dict[tuple[int, int], float]] = {k: defaultdict(float)
                                                     for k in ("rev", "exp", "sav")}
    for e in exp:
        p = id2p[e["month_id"]]
        name = cats.get(e["category_id"], "?")
        tot["exp"][p] += e["amount"]
        cat_month[p][name] += e["amount"]
        if p not in in_basis:
            continue
        by_cat[name] += e["amount"]
        key = (e.get("label") or "").strip() or (e.get("payee") or "").strip()
        if key:
            by_label[key] += e["amount"]
        if e.get("payee"):
            by_payee[e["payee"]] += e["amount"]
    by_src: dict[str, float] = defaultdict(float)
    for r in rev:
        p = id2p[r["month_id"]]
        tot["rev"][p] += r["amount"]
        if p in in_basis:
            by_src[r["source"]] += r["amount"]
    by_acc: dict[str, float] = defaultdict(float)
    for s in sav:
        p = id2p[s["month_id"]]
        tot["sav"][p] += s["amount"]
        if p in in_basis:
            by_acc[(s.get("account") or "").strip() or "Sans compte"] += s["amount"]

    def top(d: dict, k: int) -> list[dict]:
        return [{"name": name, "per_month": round(v / n, 2)}
                for name, v in sorted(d.items(), key=lambda kv: -kv[1])[:k]]

    per_month = []
    for p in chosen:
        top_cats = sorted(cat_month[p].items(), key=lambda kv: -kv[1])[:10]
        per_month.append({
            "period": fmt(p), "partial": p in partial,
            "rev": round(tot["rev"][p], 2), "exp": round(tot["exp"][p], 2),
            "sav": round(tot["sav"][p], 2),
            "solde": round(tot["rev"][p] - tot["exp"][p] - tot["sav"][p], 2),
            "categories": {k: round(v, 2) for k, v in top_cats},
        })
    avg = {k: round(sum(tot[k][p] for p in basis) / n, 2) if chosen else None
           for k in ("rev", "exp", "sav")}

    # Budgets et signaux du dernier mois retenu (pas d'un mois vide).
    last = chosen[-1] if chosen else end
    spent_last: dict[str, float] = dict(cat_month.get(last, {}))
    budgets_last = budget_status(repo, last[0], last[1], spent_last)
    pat = patrimoine(repo)
    an = analytics(repo, last[0], last[1], months=1)
    notes = [f"Moyennes calculées sur {len(basis)} mois saisi(s) : "
             + ", ".join(fmt(p) for p in basis) + "."] if chosen else             ["Aucune saisie sur la période : aucune moyenne disponible."]
    if partial:
        notes.append(f"{fmt(cur_cal)} est le mois en cours (jour {t.day}) : données "
                     "partielles, exclues des moyennes.")
    if skipped:
        notes.append("Mois sans aucune saisie ignorés : " + ", ".join(fmt(p) for p in skipped) + ".")
    return {
        "today": t.isoformat(), "period_end": fmt(last),
        "months_with_data": len(chosen), "averages_months": len(basis), "notes": notes,
        "per_month": per_month, "averages_per_month": avg,
        "savings_rate_pct": round(avg["sav"] / avg["rev"] * 100, 1)
        if chosen and avg["rev"] else None,
        "top_categories": top(by_cat, 10), "top_expenses": top(by_label, 8),
        "top_payees": top(by_payee, 8), "revenue_sources": top(by_src, 5),
        "savings_by_account": top(by_acc, 6),
        "budgets_of_period_end": [{k: round(v, 2) if isinstance(v, float) else v
                                   for k, v in b.items()} for b in budgets_last],
        "patrimoine": {"by_type": pat["by_type"], "net_worth": round(pat["net_worth"], 2),
                       "liabilities_total": round(pat["total_liabilities"], 2)},
        # Signaux déjà calculés (seuils prudents) : l'IA s'appuie dessus au
        # lieu de deviner ce qui est « inhabituel ».
        "unusual_period_end": {k: an[k] for k in ("unusual", "large_expenses")},
    }


# ── Saisie groupée (atomique) ────────────────────────────────

def add_expenses_batch(repo: Repo, year: int, month: int,
                       rows: list[dict]) -> tuple[list[dict], list[BudgetCheck]]:
    """rows : [{category_id, amount, label, payee}]. Une transaction : tout
    ou rien. Renvoie aussi le bilan budget par catégorie."""
    mo = existing_month(repo, year, month)
    cats = {c["id"]: c["name"] for c in categories(repo)}
    unknown = sorted({r["category_id"] for r in rows} - set(cats))
    if unknown:
        raise HTTPException(422, f"Catégorie inconnue : {unknown[0]}.")
    checks = _budget_checks(repo, year, month, mo, rows, cats)
    res = repo.apply([open_month_op(year, month),
                      {"op": "insert", "table": "expenses",
                       "rows": [_expense_row(r, ref(0)) for r in rows]}])
    return res[1], checks


def _revenue_row(r: dict, month_ref) -> dict:
    return {"month_id": month_ref, "source": r["source"], "amount": r["amount"],
            "label": r.get("label", "")}


def add_revenues_batch(repo: Repo, year: int, month: int, rows: list[dict]) -> list[dict]:
    return repo.apply([open_month_op(year, month),
                       {"op": "insert", "table": "revenues",
                        "rows": [_revenue_row(r, ref(0)) for r in rows]}])[1]


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
    return repo.apply([{"op": "insert", "table": "recurring_transactions", "row": {
        "label": data["label"], "amount": data["amount"], "type": data["type"],
        "category_id": data.get("category_id") if data["type"] == "expense" else None,
        "source": data.get("source", "") if data["type"] == "revenue" else "",
        "payee": (data.get("payee") or "").strip().upper() if data["type"] == "expense" else "",
        "active": 1, "last_applied_year": 0, "last_applied_month": 0}}])[0]


def set_recurring_active(repo: Repo, rec_id: int, active: bool) -> dict:
    rows = repo.apply([{"op": "update", "table": "recurring_transactions",
                        "where": {"id": rec_id}, "set": {"active": int(active)}}])[0]
    if not rows:
        raise HTTPException(404, "Récurrente introuvable.")
    return rows[0]


def delete_recurring(repo: Repo, rec_id: int) -> None:
    if not repo.apply([{"op": "delete", "table": "recurring_transactions",
                        "where": {"id": rec_id}}])[0]:
        raise HTTPException(404, "Récurrente introuvable.")


def apply_recurring(repo: Repo, year: int, month: int,
                    items: list[dict]) -> tuple[int, list[BudgetCheck]]:
    """items : [{id, amount}]. Toutes doivent être en attente pour ce mois.
    Saisies ET marquage « appliquée » dans UNE transaction : une panne ne
    laisse jamais des saisies créées avec des récurrentes encore « en
    attente » (ce qui provoquait des doublons au nouvel essai)."""
    by_id = {r["id"]: r for r in recurring(repo, year, month)}
    expenses, revenues, marks = [], [], []
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
        # Garde optimiste : la ligne doit être encore dans l'état lu (sinon
        # appliquée entre-temps par une autre requête -> tout est annulé).
        marks.append({"op": "update", "table": "recurring_transactions", "require": True,
                      "on_missing": "conflict",
                      "where": {"id": r["id"], "last_applied_year": r.get("last_applied_year"),
                                "last_applied_month": r.get("last_applied_month")},
                      "set": {"last_applied_year": year, "last_applied_month": month}})
    mo = existing_month(repo, year, month)
    checks: list[BudgetCheck] = []
    ops = [open_month_op(year, month)]
    if expenses:
        cats = {c["id"]: c["name"] for c in categories(repo)}
        gone = next((e for e in expenses if e["category_id"] not in cats), None)
        if gone:
            raise HTTPException(422, f"« {gone['label']} » : catégorie supprimée, modifiez la récurrente.")
        checks = _budget_checks(repo, year, month, mo, expenses, cats)
        ops.append({"op": "insert", "table": "expenses",
                    "rows": [_expense_row(e, ref(0)) for e in expenses]})
    if revenues:
        ops.append({"op": "insert", "table": "revenues",
                    "rows": [_revenue_row(r, ref(0)) for r in revenues]})
    repo.apply(ops + marks)
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
    # Bornes de montant filtrées PAR LA BASE, avant la limite (filtrées en
    # Python après coup, des résultats manquaient sans le signaler).
    bounds = ([f"amount.gte.{min_amount}"] if min_amount is not None else []) + \
             ([f"amount.lte.{max_amount}"] if max_amount is not None else [])
    if bounds:
        filters["and"] = f"({','.join(bounds)})"
    rows = repo.select(table, filters, order="id.desc", limit=2000)
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
