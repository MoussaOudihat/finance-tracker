"""
routes_misc.py — Transactions récurrentes, recherche, duplication du mois précédent.
"""
from __future__ import annotations

from typing import Optional
from types import SimpleNamespace

from fastapi import FastAPI, Form, Request
from fastapi.responses import HTMLResponse

from fintrack_common.fmt import shift_month

from .backends import BackendError
from .common import SECTIONS, parse_amount


def register(app: FastAPI, w: SimpleNamespace) -> None:
    """Enregistre les routes de ce module (dépendances partagées dans `w`)."""
    # Dépendances partagées, créées par main.create_app
    call, call_parallel, check_csrf, flash = w.call, w.call_parallel, w.check_csrf, w.flash
    load, month_params, redirect, render = w.load, w.month_params, w.redirect, w.render

    # ── Transactions récurrentes ─────────────────────────────
    @app.get("/recurrentes", response_class=HTMLResponse)
    def recurring_page(request: Request, y: Optional[str] = None, m: Optional[str] = None):
        sid, sess = load(request)
        yy, mm = month_params(sid, sess, y, m)
        rec, cats = call_parallel(
            sid, sess,
            ("finance", "GET", "/v1/recurring", {"params": {"year": yy, "month": mm}}),
            ("finance", "GET", "/v1/categories"))
        return render(request, "recurring.html", sid, sess, active="recurrentes", y=yy, m=mm,
                      prev=shift_month(yy, mm, -1), next=shift_month(yy, mm, 1),
                      closed=rec["closed"], items=rec["items"], categories=cats,
                      pending=[r for r in rec["items"] if r["pending"]])

    @app.post("/recurrentes")
    def add_recurring(request: Request, y: int = Form(...), m: int = Form(...),
                      type: str = Form("expense"), label: str = Form(""),
                      amount: str = Form(""), category_id: str = Form(""),
                      payee: str = Form(""), source: str = Form(""), csrf: str = Form("")):
        sid, sess = load(request)
        check_csrf(sess, csrf)
        body: dict = {"type": type, "label": label, "amount": parse_amount(amount)}
        if type == "expense":
            try:
                body.update(category_id=int(category_id), payee=payee)
            except ValueError:
                raise BackendError(422, "Catégorie invalide.") from None
        else:
            body["source"] = source or label
        call(sid, sess, "finance", "POST", "/v1/recurring", json=body)
        flash(sid, sess, "Transaction récurrente ajoutée.")
        return redirect(f"/recurrentes?y={y}&m={m}")

    @app.post("/recurrentes/appliquer")
    def apply_recurring(request: Request, y: int = Form(...), m: int = Form(...),
                        sel: list[str] = Form([]), ids: list[str] = Form([]),
                        amounts: list[str] = Form([]), csrf: str = Form("")):
        sid, sess = load(request)
        check_csrf(sess, csrf)
        if len(ids) != len(amounts):
            raise BackendError(400, "Formulaire incomplet — rechargez la page.")
        chosen = set(sel)
        items = [{"id": i, "amount": parse_amount(a)}
                 for i, a in zip(ids, amounts, strict=True) if i in chosen]
        if not items:
            raise BackendError(422, "Aucune transaction sélectionnée.")
        try:
            items = [{**it, "id": int(it["id"])} for it in items]
        except ValueError:
            raise BackendError(422, "Sélection invalide.") from None
        n = call(sid, sess, "finance", "POST", "/v1/recurring/apply",
                 json={"year": y, "month": m, "items": items})["applied"]
        flash(sid, sess, f"{n} transaction(s) récurrente(s) appliquée(s).")
        return redirect(f"/recurrentes?y={y}&m={m}")

    @app.post("/recurrentes/{rec_id}/activer")
    def toggle_recurring(request: Request, rec_id: int, active: str = Form("1"),
                         y: int = Form(...), m: int = Form(...), csrf: str = Form("")):
        sid, sess = load(request)
        check_csrf(sess, csrf)
        call(sid, sess, "finance", "PUT", f"/v1/recurring/{rec_id}/active",
             json={"active": active == "1"})
        flash(sid, sess, "Récurrente activée." if active == "1" else "Récurrente désactivée.")
        return redirect(f"/recurrentes?y={y}&m={m}")

    @app.post("/recurrentes/{rec_id}/supprimer")
    def delete_recurring(request: Request, rec_id: int, y: int = Form(...), m: int = Form(...),
                         csrf: str = Form("")):
        sid, sess = load(request)
        check_csrf(sess, csrf)
        call(sid, sess, "finance", "DELETE", f"/v1/recurring/{rec_id}")
        flash(sid, sess, "Récurrente supprimée.")
        return redirect(f"/recurrentes?y={y}&m={m}")

    # ── Recherche ────────────────────────────────────────────
    def _amount_param(raw: str) -> Optional[float]:
        raw = parse_amount(raw)
        if not raw:
            return None
        try:
            v = float(raw)
        except ValueError:
            v = -1.0
        if not (0 <= v <= 1e9):              # NaN inclus
            raise BackendError(400, "Montant de filtre invalide.")
        return v

    @app.get("/recherche", response_class=HTMLResponse)
    def search_page(request: Request, type: str = "depenses", q: str = "", cat: str = "",
                    min: str = "", max: str = ""):  # noqa: A002 — noms des champs du formulaire
        sid, sess = load(request)
        section = type if type in SECTIONS else "depenses"
        q = q.strip()[:80]
        try:
            cat_id = int(cat) if cat and section == "depenses" else None
        except ValueError:
            cat_id = None
        lo, hi = _amount_param(min), _amount_param(max)
        searched = bool(q or cat_id is not None or lo is not None or hi is not None)
        params = {k: v for k, v in {"q": q, "category_id": cat_id,
                                    "min_amount": lo, "max_amount": hi}.items()
                  if v not in (None, "")}
        specs = [("finance", "GET", "/v1/categories")]
        if searched:
            specs.append(("finance", "GET", f"/v1/search/{SECTIONS[section][0]}",
                          {"params": params}))
        cats, *rest = call_parallel(sid, sess, *specs)
        results = rest[0] if rest else []
        return render(request, "search.html", sid, sess, active="recherche", section=section,
                      q=q, cat=cat_id, min=min, max=max, categories=cats, searched=searched,
                      results=results, total=sum(r["amount"] for r in results))

    # ── Dupliquer le mois précédent (dépenses) ───────────────
    @app.get("/depenses/dupliquer", response_class=HTMLResponse)
    def duplicate_form(request: Request, y: Optional[str] = None, m: Optional[str] = None):
        sid, sess = load(request)
        yy, mm = month_params(sid, sess, y, m)
        py, pm = shift_month(yy, mm, -1)
        src, cur = call_parallel(sid, sess,
                                 ("finance", "GET", f"/v1/months/{py}/{pm}/entries"),
                                 ("finance", "GET", f"/v1/months/{yy}/{mm}/entries"))
        return render(request, "duplicate.html", sid, sess, active="depenses", y=yy, m=mm,
                      src=(py, pm), rows=src["expenses"], closed=cur["closed"],
                      existing=len(cur["expenses"]))

    @app.post("/depenses/dupliquer")
    def duplicate_month(request: Request, y: int = Form(...), m: int = Form(...),
                        sel: list[str] = Form([]), cat: list[str] = Form([]),
                        label: list[str] = Form([]), payee: list[str] = Form([]),
                        amounts: list[str] = Form([]), csrf: str = Form("")):
        sid, sess = load(request)
        check_csrf(sess, csrf)
        if not (len(cat) == len(label) == len(payee) == len(amounts)):
            raise BackendError(400, "Formulaire incomplet — rechargez la page.")
        try:
            chosen = sorted({int(i) for i in sel})
            rows = [{"category_id": int(cat[i]), "amount": parse_amount(amounts[i]),
                     "label": label[i], "payee": payee[i]}
                    for i in chosen if 0 <= i < len(cat)]
        except ValueError:
            raise BackendError(422, "Sélection invalide.") from None
        if not rows:
            raise BackendError(422, "Aucune dépense sélectionnée.")
        n = call(sid, sess, "finance", "POST", "/v1/expenses/batch",
                 json={"year": y, "month": m, "rows": rows})["created"]
        flash(sid, sess, f"{n} dépense(s) copiée(s) depuis le mois précédent.")
        return redirect(f"/depenses?y={y}&m={m}")
