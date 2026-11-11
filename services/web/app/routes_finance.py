"""
routes_finance.py — Tableau de bord, patrimoine, budgets, clôture du mois, vue épargne.
"""
from __future__ import annotations

from datetime import date
from typing import Optional
from types import SimpleNamespace

from fastapi import FastAPI, Form, Request
from fastapi.responses import HTMLResponse

from fintrack_common.fmt import shift_month

from .backends import BackendError
from .common import MONTHS_FR, parse_amount


def register(app: FastAPI, w: SimpleNamespace) -> None:
    """Enregistre les routes de ce module (dépendances partagées dans `w`)."""
    # Dépendances partagées, créées par main.create_app
    back_url, call, call_parallel, check_csrf = w.back_url, w.call, w.call_parallel, w.check_csrf
    flash, load, month_params, redirect = w.flash, w.load, w.month_params, w.redirect
    render = w.render

    # ── Tableau de bord ──────────────────────────────────────
    @app.get("/", response_class=HTMLResponse)
    def dashboard(request: Request, y: Optional[str] = None, m: Optional[str] = None):
        sid, sess = load(request)
        yy, mm = month_params(sid, sess, y, m)
        s, hist, pat = call_parallel(
            sid, sess,
            ("finance", "GET", f"/v1/months/{yy}/{mm}/summary"),
            ("finance", "GET", "/v1/history", {"params": {"limit": 12}}),
            ("finance", "GET", "/v1/patrimoine"))
        return render(request, "dashboard.html", sid, sess, active="dashboard", y=yy, m=mm,
                      month_actions=True,
                      prev=shift_month(yy, mm, -1), next=shift_month(yy, mm, 1), s=s, history=hist,
                      closed=s["closed"], net_worth=pat["net_worth"],
                      max_cat=max((c["total"] for c in s["by_category"]), default=0) or 1,
                      max_hist=max((max(h["rev"], h["exp"]) for h in hist), default=0) or 1)

    @app.get("/patrimoine", response_class=HTMLResponse)
    def patrimoine(request: Request):
        sid, sess = load(request)
        pat = call(sid, sess, "finance", "GET", "/v1/patrimoine")
        today = date.today()
        return render(request, "patrimoine.html", sid, sess, active="patrimoine", pat=pat,
                      this_month=f"{today.year}-{today.month:02d}",
                      max_type=max((t["total"] for t in pat["by_type"]), default=0) or 1)

    @app.get("/budgets", response_class=HTMLResponse)
    def budgets(request: Request, y: Optional[str] = None, m: Optional[str] = None):
        sid, sess = load(request)
        yy, mm = month_params(sid, sess, y, m)
        s, cats = call_parallel(sid, sess,
                                ("finance", "GET", f"/v1/months/{yy}/{mm}/summary"),
                                ("finance", "GET", "/v1/categories"))
        budgeted = {b["category"] for b in s["budgets"]}
        spent = {c["name"]: c["total"] for c in s["by_category"]}
        return render(request, "budgets.html", sid, sess, active="budgets", y=yy, m=mm,
                      prev=shift_month(yy, mm, -1), next=shift_month(yy, mm, 1), s=s, closed=False,
                      unbudgeted=[{"name": c["name"], "spent": spent.get(c["name"], 0.0)}
                                  for c in cats if c["name"] not in budgeted])

    @app.post("/budgets")
    def set_budget(request: Request, y: int = Form(...), m: int = Form(...),
                   category: str = Form(""), amount: str = Form("0"), csrf: str = Form("")):
        sid, sess = load(request)
        check_csrf(sess, csrf)
        call(sid, sess, "finance", "PUT", f"/v1/budgets/{y}/{m}",
             json={"category": category, "amount": parse_amount(amount) or "0"})
        flash(sid, sess, "Budget enregistré.")
        return redirect(f"/budgets?y={y}&m={m}")

    @app.post("/budgets/copier")
    def copy_budgets(request: Request, y: int = Form(...), m: int = Form(...),
                     csrf: str = Form("")):
        sid, sess = load(request)
        check_csrf(sess, csrf)
        n = call(sid, sess, "finance", "POST", f"/v1/budgets/{y}/{m}/copy-previous")["copied"]
        flash(sid, sess, f"{n} budget(s) copié(s) depuis le mois précédent.")
        return redirect(f"/budgets?y={y}&m={m}")

    # ── Clôture du mois ──────────────────────────────────────
    @app.post("/mois/cloture")
    def month_close(request: Request, y: int = Form(...), m: int = Form(...),
                    action: str = Form("close"), csrf: str = Form("")):
        sid, sess = load(request)
        check_csrf(sess, csrf)
        yy, mm = month_params(sid, sess, str(y), str(m))
        closed = action != "reopen"
        call(sid, sess, "finance", "PUT", f"/v1/months/{yy}/{mm}/closed", json={"closed": closed})
        flash(sid, sess, f"{MONTHS_FR[mm - 1]} {yy} "
              + ("clôturé : saisie verrouillée." if closed else "rouvert : saisie possible."))
        return redirect(back_url(request, f"/?y={yy}&m={mm}"))

    # ── Épargne : vue d'ensemble ─────────────────────────────
    @app.get("/epargne/vue", response_class=HTMLResponse)
    def savings_view(request: Request, y: Optional[str] = None, m: Optional[str] = None):
        sid, sess = load(request)
        yy, mm = month_params(sid, sess, y, m)
        ov = call(sid, sess, "finance", "GET", "/v1/savings-overview",
                  params={"year": yy, "month": mm, "months": 12})
        return render(request, "savings_overview.html", sid, sess, active="epargne", y=yy, m=mm,
                      prev=shift_month(yy, mm, -1), next=shift_month(yy, mm, 1), closed=False,
                      ov=ov, max_sav=max((p["sav"] for p in ov["per_month"]), default=0) or 1,
                      max_acc=max((a["total"] for a in ov["by_account"]), default=0) or 1)

    # ── Patrimoine : saisie ──────────────────────────────────
    def parse_period(raw: str) -> tuple[int, int]:
        """<input type="month"> : 'AAAA-MM' ; vide -> mois en cours."""
        if not raw:
            t = date.today()
            return t.year, t.month
        try:
            yi, mi = (int(x) for x in raw.split("-", 1))
        except ValueError:
            raise BackendError(422, "Mois de valeur invalide (AAAA-MM).") from None
        if not (2000 <= yi <= 2100 and 1 <= mi <= 12):
            raise BackendError(422, "Mois de valeur invalide (AAAA-MM).")
        return yi, mi

    def opt_amount(raw: str) -> Optional[str]:
        v = parse_amount(raw)
        return v or None

    @app.post("/patrimoine/actif")
    def asset_save(request: Request, asset_type: str = Form(...), name: str = Form(...),
                   value: str = Form(...), cost_basis: str = Form(""), period: str = Form(""),
                   csrf: str = Form("")):
        sid, sess = load(request)
        check_csrf(sess, csrf)
        yy, mm = parse_period(period)
        call(sid, sess, "finance", "PUT", "/v1/assets",
             json={"year": yy, "month": mm, "asset_type": asset_type, "name": name,
                   "value": parse_amount(value), "cost_basis": opt_amount(cost_basis)})
        flash(sid, sess, f"« {name.strip()} » : valeur enregistrée pour {MONTHS_FR[mm - 1]} {yy}.")
        return redirect("/patrimoine")

    @app.post("/patrimoine/actif/supprimer")
    def asset_delete(request: Request, asset_type: str = Form(...), name: str = Form(...),
                     csrf: str = Form("")):
        sid, sess = load(request)
        check_csrf(sess, csrf)
        call(sid, sess, "finance", "POST", "/v1/assets/delete",
             json={"asset_type": asset_type, "name": name})
        flash(sid, sess, f"« {name} » n'est plus suivi (historique supprimé).")
        return redirect("/patrimoine")

    @app.post("/patrimoine/passif")
    def liability_save(request: Request, name: str = Form(...), liability_type: str = Form("autre"),
                       remaining_capital: str = Form(...), monthly_payment: str = Form(""),
                       end_date: str = Form(""), period: str = Form(""), csrf: str = Form("")):
        sid, sess = load(request)
        check_csrf(sess, csrf)
        yy, mm = parse_period(period)
        call(sid, sess, "finance", "PUT", "/v1/liabilities",
             json={"year": yy, "month": mm, "name": name, "liability_type": liability_type,
                   "remaining_capital": parse_amount(remaining_capital) or "0",
                   "monthly_payment": opt_amount(monthly_payment),
                   "end_date": end_date.strip() or None})
        flash(sid, sess, f"Passif « {name.strip()} » enregistré.")
        return redirect("/patrimoine")

    @app.post("/patrimoine/passif/supprimer")
    def liability_delete(request: Request, name: str = Form(...), csrf: str = Form("")):
        sid, sess = load(request)
        check_csrf(sess, csrf)
        call(sid, sess, "finance", "POST", "/v1/liabilities/delete", json={"name": name})
        flash(sid, sess, f"Passif « {name} » supprimé.")
        return redirect("/patrimoine")
