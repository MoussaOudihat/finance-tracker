"""
finance-api — Service de données de Fintrack (API REST JSON).

Seul service à parler à la base (Supabase Postgres via PostgREST), toujours
avec le jeton de l'utilisateur (RLS). Sans état : réplicable (HPA).

Émet des événements vers notifier (franchissement de budget à 80 % / 100 %).
"""
from __future__ import annotations

from typing import Annotated, Optional

import httpx
from fastapi import Depends, FastAPI, HTTPException, Query
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


class BudgetIn(_Trimmed):
    category: Annotated[str, Field(min_length=1, max_length=60)]
    amount: Annotated[float, Field(ge=0, le=1_000_000_000, allow_inf_nan=False)]


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
        for t in BUDGET_THRESHOLDS:
            limit = chk.budget * t / 100
            if chk.before < limit <= chk.after:
                _emit({"type": "budget.threshold", "user_id": r.user.id,
                       "email": r.user.email, "year": chk.year, "month": chk.month,
                       "category": chk.category, "threshold": t,
                       "spent": round(chk.after, 2), "budget": round(chk.budget, 2)})

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
        h = ledger.history(r, limit=1)
        return {"year": h[-1]["year"], "month": h[-1]["month"]} if h else None

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
    def post_expense(body: ExpenseIn, r: Repo = Depends(repo)):
        row, chk = ledger.add_expense(r, body.year, body.month, body.category_id,
                                      body.amount, body.label, body.payee)
        _check_budget(r, chk)
        return row

    @app.put("/v1/expenses/{entry_id}")
    def put_expense(entry_id: int, body: ExpenseUpdate, r: Repo = Depends(repo)):
        row, chk = ledger.update_expense(r, entry_id, body.category_id, body.amount,
                                         body.label, body.payee)
        _check_budget(r, chk)
        return row

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
