"""
finance-api — Service de données de Fintrack (API REST JSON).

Seul service à parler à la base (Supabase Postgres via PostgREST), toujours
avec le jeton de l'utilisateur (RLS). Sans état : réplicable (HPA).

Émet des événements vers notifier (franchissement de budget à 80 % / 100 %).
"""
from __future__ import annotations

from typing import Annotated, Literal, Optional

import httpx
from fastapi import BackgroundTasks, Depends, FastAPI, HTTPException, Query
from pydantic import BaseModel, Field, field_validator

from fintrack_common.auth import TokenVerifier, User, user_dependency
from fintrack_common.config import VERSION, env
from fintrack_common.http import RequestContextMiddleware, add_health_routes, service_client
from fintrack_common.logs import setup_logging

from . import ledger
from .repo import Repo

log = setup_logging("finance-api")

Year = Annotated[int, Field(ge=2000, le=2100)]
Month = Annotated[int, Field(ge=1, le=12)]
Amount = Annotated[float, Field(gt=0, le=1_000_000_000, allow_inf_nan=False)]
Text = Annotated[str, Field(max_length=120)]
BUDGET_THRESHOLDS = (80, 100)


class _Trimmed(BaseModel):
    @field_validator("*", mode="before")
    @classmethod
    def _strip(cls, v):
        return v.strip() if isinstance(v, str) else v


class ExpenseIn(_Trimmed):
    year: Year
    month: Month
    category_id: int
    amount: Amount
    label: Text = ""
    payee: Annotated[str, Field(max_length=60)] = ""


class ExpenseUpdate(_Trimmed):
    category_id: int
    amount: Amount
    label: Text = ""
    payee: Annotated[str, Field(max_length=60)] = ""


class RevenueIn(_Trimmed):
    year: Year
    month: Month
    source: Annotated[str, Field(min_length=1, max_length=120)]
    amount: Amount
    label: Text = ""


class RevenueUpdate(_Trimmed):
    source: Annotated[str, Field(min_length=1, max_length=120)]
    amount: Amount
    label: Text = ""


class SavingIn(_Trimmed):
    year: Year
    month: Month
    account: Annotated[str, Field(max_length=80)] = ""
    amount: Amount
    label: Text = ""


class SavingUpdate(_Trimmed):
    account: Annotated[str, Field(max_length=80)] = ""
    amount: Amount
    label: Text = ""


class ExpenseRow(_Trimmed):
    category_id: int
    amount: Amount
    label: Text = ""
    payee: Annotated[str, Field(max_length=60)] = ""


class RevenueRow(_Trimmed):
    source: Annotated[str, Field(min_length=1, max_length=120)]
    amount: Amount
    label: Text = ""


class ExpenseBatch(BaseModel):
    year: Year
    month: Month
    rows: Annotated[list[ExpenseRow], Field(min_length=1, max_length=200)]


class RevenueBatch(BaseModel):
    year: Year
    month: Month
    rows: Annotated[list[RevenueRow], Field(min_length=1, max_length=200)]


class RecurringIn(_Trimmed):
    type: Literal["expense", "revenue"]
    label: Annotated[str, Field(min_length=1, max_length=120)]
    amount: Amount
    category_id: Optional[int] = None
    source: Text = ""
    payee: Annotated[str, Field(max_length=60)] = ""


class ApplyItem(BaseModel):
    id: int
    amount: Amount


class ApplyIn(BaseModel):
    year: Year
    month: Month
    items: Annotated[list[ApplyItem], Field(min_length=1, max_length=100)]


class ActiveIn(BaseModel):
    active: bool


class BudgetIn(_Trimmed):
    category: Annotated[str, Field(min_length=1, max_length=60)]
    amount: Annotated[float, Field(ge=0, le=1_000_000_000, allow_inf_nan=False)]


class ClosedIn(BaseModel):
    closed: bool


AssetType = Literal["bourse", "immobilier", "crypto", "or_metaux", "compte", "autre"]
LiabilityType = Literal["voiture", "conso", "autre"]
Money = Annotated[float, Field(ge=0, le=1_000_000_000, allow_inf_nan=False)]
Name = Annotated[str, Field(min_length=1, max_length=80)]


class AssetKey(_Trimmed):
    asset_type: AssetType
    name: Name


class AssetIn(AssetKey):
    year: Year
    month: Month
    value: Money
    cost_basis: Optional[Money] = None          # None : repris du dernier instantané
    notes: Optional[Annotated[str, Field(max_length=200)]] = None


class LiabilityKey(_Trimmed):
    name: Name


class LiabilityIn(LiabilityKey):
    year: Year
    month: Month
    liability_type: LiabilityType = "autre"
    remaining_capital: Money
    monthly_payment: Optional[Money] = None
    end_date: Optional[Annotated[str, Field(max_length=10, pattern=r"^(\d{4}-\d{2}(-\d{2})?)?$")]] = None


def create_app(*, verifier: Optional[TokenVerifier] = None,
               supabase_http: Optional[httpx.Client] = None,
               notifier_http: Optional[httpx.Client] = None) -> FastAPI:
    supabase_url = env("SUPABASE_URL", required=True)
    anon_key = env("SUPABASE_ANON_KEY", required=True)
    notifier_url = env("NOTIFIER_URL", "")
    notifier_token = env("NOTIFIER_INTERNAL_TOKEN", "", min_len=32)

    app = FastAPI(title="fintrack-finance-api", version=VERSION,
                  docs_url=None, redoc_url=None, openapi_url=None)
    app.add_middleware(RequestContextMiddleware)
    app.state.verifier = verifier or TokenVerifier(supabase_url)
    http = supabase_http or httpx.Client(
        base_url=supabase_url.rstrip("/"), timeout=httpx.Timeout(10.0, connect=3.0),
        follow_redirects=False)
    notifier = notifier_http or (service_client(notifier_url, timeout=3.0) if notifier_url else None)
    add_health_routes(app)

    current_user = user_dependency()

    def repo(user: User = Depends(current_user)) -> Repo:
        return Repo(http, anon_key, user)

    # ── Événements → notifier (best effort, jamais bloquant pour la saisie) ──
    def _emit(event: dict) -> None:
        if notifier is None:
            return
        try:
            notifier.post("/internal/v1/events", json=event,
                          headers={"X-Internal-Token": notifier_token})
        except httpx.HTTPError as exc:
            log.warning("notifier injoignable : %s", exc.__class__.__name__)

    def _check_budget(r: Repo, chk: ledger.BudgetCheck) -> None:
        if chk.budget <= 0:
            return
        # Un seul message par écriture : le seuil le plus haut franchi (une
        # saisie groupée qui passe de 50 % à 110 % n'annonce pas aussi « 80 % »).
        crossed = [t for t in BUDGET_THRESHOLDS
                   if chk.before < chk.budget * t / 100 <= chk.after]
        if crossed:
            _emit({"type": "budget.threshold", "user_id": r.user.id,
                   "email": r.user.email, "year": chk.year, "month": chk.month,
                   "category": chk.category, "threshold": max(crossed),
                   "spent": round(chk.after, 2), "budget": round(chk.budget, 2)})

    def _check_unusual(r: Repo, year: int, month: int, categories: set[str]) -> None:
        """Après la réponse (BackgroundTasks) : la saisie ne paie pas le coût
        de l'analyse. Une alerte par catégorie et par mois (anti-doublon
        côté notifier)."""
        if notifier is None or not categories:
            return
        try:
            an = ledger.analytics(r, year, month, months=1)
        except Exception:                    # best effort, jamais d'erreur visible
            log.warning("analyse des dépenses inhabituelles impossible", exc_info=True)
            return
        for u in an["unusual"]:
            if u["category"] in categories:
                _emit({"type": "spending.unusual", "user_id": r.user.id, "email": r.user.email,
                       "year": year, "month": month, "category": u["category"],
                       "spent": u["spent"], "average": u["average"]})

    # ── Lecture ──────────────────────────────────────────────
    @app.get("/v1/categories")
    def get_categories(r: Repo = Depends(repo)):
        return ledger.categories(r)

    @app.get("/v1/months/{year}/{month}/summary")
    def get_summary(year: Year, month: Month, r: Repo = Depends(repo)):
        return ledger.month_summary(r, year, month)

    @app.get("/v1/months/{year}/{month}/entries")
    def get_entries(year: Year, month: Month, r: Repo = Depends(repo)):
        return ledger.month_entries(r, year, month)

    @app.get("/v1/last-month")
    def get_last_month(r: Repo = Depends(repo)):
        return ledger.last_month(r)

    @app.put("/v1/months/{year}/{month}/closed")
    def put_month_closed(year: Year, month: Month, body: ClosedIn, r: Repo = Depends(repo)):
        return ledger.set_month_closed(r, year, month, body.closed)

    @app.get("/v1/savings-overview")
    def get_savings_overview(year: Year, month: Month,
                             months: Annotated[int, Query(ge=1, le=24)] = 12,
                             r: Repo = Depends(repo)):
        return ledger.savings_overview(r, year, month, months)

    @app.put("/v1/assets")
    def put_asset(body: AssetIn, r: Repo = Depends(repo)):
        return ledger.set_asset_value(r, body.year, body.month, body.asset_type, body.name,
                                      body.value, body.cost_basis, body.notes)

    @app.post("/v1/assets/delete")
    def post_asset_delete(body: AssetKey, r: Repo = Depends(repo)):
        return {"deleted": ledger.delete_asset(r, body.asset_type, body.name)}

    @app.put("/v1/liabilities")
    def put_liability(body: LiabilityIn, r: Repo = Depends(repo)):
        return ledger.set_liability(r, body.year, body.month, body.liability_type, body.name,
                                    body.remaining_capital, body.monthly_payment, body.end_date)

    @app.post("/v1/liabilities/delete")
    def post_liability_delete(body: LiabilityKey, r: Repo = Depends(repo)):
        return {"deleted": ledger.delete_liability(r, body.name)}

    @app.get("/v1/history")
    def get_history(limit: int = Query(12, ge=1, le=60), r: Repo = Depends(repo)):
        return ledger.history(r, limit)

    @app.get("/v1/payees")
    def get_payees(r: Repo = Depends(repo)):
        return ledger.payees(r)

    @app.get("/v1/patrimoine")
    def get_patrimoine(r: Repo = Depends(repo)):
        return ledger.patrimoine(r)

    @app.get("/v1/ai-context")
    def get_ai_context(year: Year, month: Month,
                       months: int = Query(3, ge=1, le=12), r: Repo = Depends(repo)):
        return ledger.ai_context(r, year, month, months)

    @app.get("/v1/entries/{kind}/{entry_id}")
    def get_entry(kind: str, entry_id: int, r: Repo = Depends(repo)):
        table = ledger.ENTRY_TABLES.get(kind)
        if table is None:
            raise HTTPException(404, "Type inconnu.")
        entry, mo = ledger.entry_with_month(r, table, entry_id)
        return {**entry, "year": mo["year"], "month": mo["month"],
                "closed": bool(mo.get("closed"))}

    # ── Écriture ─────────────────────────────────────────────
    @app.post("/v1/expenses", status_code=201)
    def post_expense(body: ExpenseIn, bg: BackgroundTasks, r: Repo = Depends(repo)):
        row, chk = ledger.add_expense(r, body.year, body.month, body.category_id,
                                      body.amount, body.label, body.payee)
        _check_budget(r, chk)
        bg.add_task(_check_unusual, r, body.year, body.month, {chk.category})
        return row

    @app.put("/v1/expenses/{entry_id}")
    def put_expense(entry_id: int, body: ExpenseUpdate, r: Repo = Depends(repo)):
        row, chk = ledger.update_expense(r, entry_id, body.category_id, body.amount,
                                         body.label, body.payee)
        _check_budget(r, chk)
        return row

    @app.post("/v1/expenses/batch", status_code=201)
    def post_expenses_batch(body: ExpenseBatch, bg: BackgroundTasks, r: Repo = Depends(repo)):
        created, checks = ledger.add_expenses_batch(
            r, body.year, body.month, [row.model_dump() for row in body.rows])
        for chk in checks:
            _check_budget(r, chk)
        bg.add_task(_check_unusual, r, body.year, body.month, {c.category for c in checks})
        return {"created": len(created)}

    @app.post("/v1/revenues/batch", status_code=201)
    def post_revenues_batch(body: RevenueBatch, r: Repo = Depends(repo)):
        created = ledger.add_revenues_batch(r, body.year, body.month,
                                            [row.model_dump() for row in body.rows])
        return {"created": len(created)}

    @app.get("/v1/analytics")
    def get_analytics(year: Year, month: Month,
                      months: Annotated[int, Query(ge=1, le=24)] = 12,
                      r: Repo = Depends(repo)):
        return ledger.analytics(r, year, month, months)

    @app.get("/v1/recurring")
    def get_recurring(year: Year, month: Month, r: Repo = Depends(repo)):
        mo = r.month(year, month, create=False)
        return {"closed": bool(mo and mo.get("closed")),
                "items": ledger.recurring(r, year, month)}

    @app.post("/v1/recurring", status_code=201)
    def post_recurring(body: RecurringIn, r: Repo = Depends(repo)):
        if body.type == "expense" and body.category_id is None:
            raise HTTPException(422, "Catégorie requise pour une dépense récurrente.")
        if body.type == "revenue" and not (body.source or body.label):
            raise HTTPException(422, "Source requise pour un revenu récurrent.")
        return ledger.add_recurring(r, body.model_dump())

    @app.put("/v1/recurring/{rec_id}/active")
    def put_recurring_active(rec_id: int, body: ActiveIn, r: Repo = Depends(repo)):
        return ledger.set_recurring_active(r, rec_id, body.active)

    @app.delete("/v1/recurring/{rec_id}", status_code=204)
    def delete_recurring(rec_id: int, r: Repo = Depends(repo)):
        ledger.delete_recurring(r, rec_id)

    @app.post("/v1/recurring/apply")
    def post_recurring_apply(body: ApplyIn, bg: BackgroundTasks, r: Repo = Depends(repo)):
        n, checks = ledger.apply_recurring(r, body.year, body.month,
                                           [i.model_dump() for i in body.items])
        for chk in checks:
            _check_budget(r, chk)
        bg.add_task(_check_unusual, r, body.year, body.month, {c.category for c in checks})
        return {"applied": n}

    @app.get("/v1/search/{kind}")
    def get_search(kind: Literal["expenses", "revenues", "savings"],
                   q: Annotated[str, Query(max_length=80)] = "",
                   category_id: Optional[int] = None,
                   min_amount: Annotated[Optional[float], Query(ge=0, le=1e9)] = None,
                   max_amount: Annotated[Optional[float], Query(ge=0, le=1e9)] = None,
                   r: Repo = Depends(repo)):
        return ledger.search(r, kind, q, category_id, min_amount, max_amount)

    @app.post("/v1/revenues", status_code=201)
    def post_revenue(body: RevenueIn, r: Repo = Depends(repo)):
        return ledger.add_revenue(r, body.year, body.month, body.source, body.amount, body.label)

    @app.put("/v1/revenues/{entry_id}")
    def put_revenue(entry_id: int, body: RevenueUpdate, r: Repo = Depends(repo)):
        return ledger.update_revenue(r, entry_id, body.source, body.amount, body.label)

    @app.post("/v1/savings", status_code=201)
    def post_saving(body: SavingIn, r: Repo = Depends(repo)):
        return ledger.add_saving(r, body.year, body.month, body.account, body.amount, body.label)

    @app.put("/v1/savings/{entry_id}")
    def put_saving(entry_id: int, body: SavingUpdate, r: Repo = Depends(repo)):
        return ledger.update_saving(r, entry_id, body.account, body.amount, body.label)

    @app.delete("/v1/{kind}/{entry_id}")
    def delete_entry(kind: str, entry_id: int, r: Repo = Depends(repo)):
        table = ledger.ENTRY_TABLES.get(kind)
        if table is None:
            raise HTTPException(404, "Type inconnu.")
        return ledger.delete_entry(r, table, entry_id)

    @app.put("/v1/budgets/{year}/{month}")
    def put_budget(year: Year, month: Month, body: BudgetIn, r: Repo = Depends(repo)):
        ledger.set_budget(r, year, month, body.category, body.amount)
        return ledger.month_summary(r, year, month)["budgets"]

    @app.post("/v1/budgets/{year}/{month}/copy-previous")
    def copy_budgets(year: Year, month: Month, r: Repo = Depends(repo)):
        return {"copied": ledger.copy_budgets(r, year, month)}

    return app


app = create_app() if __name__ != "__test__" and not env("FINTRACK_NO_AUTOAPP") else None
