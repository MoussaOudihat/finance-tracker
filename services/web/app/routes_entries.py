"""
routes_entries.py — Saisies : saisie en masse puis routes génériques /{section} (enregistrées EN DERNIER : elles captureraient les autres chemins).
"""
from __future__ import annotations

from typing import Optional
from types import SimpleNamespace

from fastapi import FastAPI, Form, Request
from fastapi.responses import HTMLResponse, Response

from fintrack_common.fmt import shift_month

from . import bulk
from .backends import BackendError
from .common import SECTIONS, parse_amount


def register(app: FastAPI, w: SimpleNamespace) -> None:
    """Enregistre les routes de ce module (dépendances partagées dans `w`)."""
    # Dépendances partagées, créées par main.create_app
    call, call_parallel, check_csrf, flash = w.call, w.call_parallel, w.check_csrf, w.flash
    load, month_params, redirect, render = w.load, w.month_params, w.redirect, w.render

    # ── Saisies ──────────────────────────────────────────────
    def entry_payload(kind, amount, label, category_id, payee, source, account) -> dict:
        p = {"amount": parse_amount(amount), "label": label}
        if kind == "expenses":
            try:
                p.update(category_id=int(category_id), payee=payee)
            except ValueError:
                raise BackendError(422, "Catégorie invalide.") from None
        elif kind == "revenues":
            p["source"] = source
        else:
            p["account"] = account
        return p

    # ── Saisie en masse (dépenses, revenus) ──────────────────
    BULK_SECTIONS = ("depenses", "revenus")

    def suggest_categories(sid, sess, rows: list) -> tuple[list[str], list[str]]:
        """Catégories manquantes proposées par l'IA, en UN appel (une requête
        du quota quotidien). Jamais bloquant : en cas d'échec, la grille
        reste telle quelle avec un avertissement. -> (infos, avertissements)"""
        missing = [r for r in rows if r.keep and not r.blank and r.category_id is None
                   and (r.label.strip() or r.extra.strip())]
        if not missing:
            return [], []
        if not sess.get("ai_consent"):
            return [], ["Activez d'abord l'IA depuis la page « Assistant IA » pour obtenir "
                        "des suggestions de catégorie."]
        todo = missing[:bulk.AI_BATCH_MAX]
        try:
            res = call(sid, sess, "ai", "POST", "/v1/categorize/batch", timeout=90.0, json={
                "provider": sess.get("ai_provider") or "claude",
                "items": [{"label": r.label[:120], "payee": r.extra[:60]} for r in todo]})
        except BackendError as exc:
            return [], [f"Suggestion IA indisponible : {exc.message}"]
        found = 0
        for r, s in zip(todo, res.get("results") or [], strict=False):
            if s and s.get("category_id") is not None:
                r.category_id, r.suggested = int(s["category_id"]), True
                found += 1
        infos = [f"✨ {found} catégorie(s) suggérée(s) par l'IA, signalée(s) par « IA » : "
                 "vérifiez-les avant d'enregistrer."] if found else []
        warns = []
        if len(missing) > len(todo):
            warns.append(f"Suggestion limitée aux {bulk.AI_BATCH_MAX} premières lignes : "
                         "relancez « Suggérer » pour les suivantes.")
        if found < len(todo):
            warns.append(f"{len(todo) - found} ligne(s) sans suggestion : catégorie à choisir.")
        return infos, warns

    def bulk_page(request, sid, sess, section, yy, mm, rows, *, categories, payees=(),
                  closed=False, paste="", warnings=(), error=None, status_code=200,
                  infos=(), blank_rows: Optional[int] = None):
        filled = any(not r.blank for r in rows)
        if blank_rows is None:
            blank_rows = 3 if filled else bulk.GRID_BLANK_ROWS
        blank_rows = max(0, min(blank_rows, bulk.MAX_ROWS - len(rows)))
        grid = rows + [bulk.Row() for _ in range(blank_rows)]
        return render(request, "bulk.html", sid, sess, status_code=status_code, active=section,
                      section=section, title=SECTIONS[section][1], y=yy, m=mm,
                      prev=shift_month(yy, mm, -1), next=shift_month(yy, mm, 1),
                      closed=closed, rows=grid, rows_filled=filled, categories=categories,
                      payees=payees, paste=paste, warnings=list(warnings), error=error,
                      infos=list(infos), ai_enabled=bool(sess.get("ai_consent")), ai_max=bulk.AI_BATCH_MAX,
                      max_rows=bulk.MAX_ROWS, max_paste=bulk.MAX_PASTE_CHARS)

    @app.get("/{section}/saisie", response_class=HTMLResponse)
    def bulk_form(request: Request, section: str, y: Optional[str] = None,
                  m: Optional[str] = None):
        if section not in BULK_SECTIONS:
            return Response(status_code=404)
        sid, sess = load(request)
        yy, mm = month_params(sid, sess, y, m)
        data, cats, payees = call_parallel(
            sid, sess,
            ("finance", "GET", f"/v1/months/{yy}/{mm}/entries"),
            ("finance", "GET", "/v1/categories"),
            ("finance", "GET", "/v1/payees"))
        return bulk_page(request, sid, sess, section, yy, mm, [], categories=cats,
                         payees=payees if section == "depenses" else (), closed=data["closed"])

    @app.post("/{section}/saisie/apercu", response_class=HTMLResponse)
    def bulk_preview(request: Request, section: str, y: int = Form(...), m: int = Form(...),
                     paste: str = Form(""), ai: str = Form(""), csrf: str = Form("")):
        if section not in BULK_SECTIONS:
            return Response(status_code=404)
        sid, sess = load(request)
        check_csrf(sess, csrf)
        yy, mm = month_params(sid, sess, str(y), str(m))
        kind = SECTIONS[section][0]
        cats = call(sid, sess, "finance", "GET", "/v1/categories")
        if len(paste) > bulk.MAX_PASTE_CHARS:
            return bulk_page(request, sid, sess, section, yy, mm, [], categories=cats,
                             status_code=413, error="Collage trop volumineux : découpez-le en "
                             f"plusieurs fois ({bulk.MAX_ROWS} lignes max).")
        rows, warnings = bulk.parse_paste(paste, kind, cats)
        infos: list[str] = []
        if ai == "1" and kind == "expenses":
            infos, more = suggest_categories(sid, sess, rows)
            warnings += more
        bulk.validate(rows, kind, cats)            # signale les lignes à corriger
        return bulk_page(request, sid, sess, section, yy, mm, rows, categories=cats,
                         paste=paste, warnings=warnings, infos=infos)

    @app.post("/depenses/saisie/suggestion", response_class=HTMLResponse)
    def bulk_suggest(request: Request, y: int = Form(...), m: int = Form(...),
                     keep: list[str] = Form([]), amount: list[str] = Form([]),
                     cat: list[str] = Form([]), label: list[str] = Form([]),
                     extra: list[str] = Form([]), csrf: str = Form("")):
        """Bouton « Suggérer » de la grille : complète les catégories
        manquantes sans rien enregistrer."""
        sid, sess = load(request)
        check_csrf(sess, csrf)
        yy, mm = month_params(sid, sess, str(y), str(m))
        try:
            rows = bulk.rows_from_form(keep, amount, cat, label, extra)
        except ValueError as exc:
            raise BackendError(400, str(exc)) from None
        cats = call(sid, sess, "finance", "GET", "/v1/categories")
        rows = [r for r in rows if not r.blank]
        infos, warnings = suggest_categories(sid, sess, rows)
        if not infos and not warnings:
            infos = ["Aucune catégorie manquante à suggérer."]
        bulk.validate(rows, "expenses", cats)
        return bulk_page(request, sid, sess, "depenses", yy, mm, rows, categories=cats,
                         infos=infos, warnings=warnings)

    @app.post("/{section}/saisie/lignes", response_class=HTMLResponse)
    def bulk_more_rows(request: Request, section: str, y: int = Form(...), m: int = Form(...),
                       keep: list[str] = Form([]), amount: list[str] = Form([]),
                       cat: list[str] = Form([]), label: list[str] = Form([]),
                       extra: list[str] = Form([]), csrf: str = Form("")):
        """« + Ajouter des lignes » sans JavaScript : la grille revient
        avec sa saisie et des lignes vides en plus (le script le fait sur place)."""
        if section not in BULK_SECTIONS:
            return Response(status_code=404)
        sid, sess = load(request)
        check_csrf(sess, csrf)
        yy, mm = month_params(sid, sess, str(y), str(m))
        try:
            rows = bulk.rows_from_form(keep, amount, cat, label, extra)
        except ValueError as exc:
            raise BackendError(400, str(exc)) from None
        cats = call(sid, sess, "finance", "GET", "/v1/categories")
        return bulk_page(request, sid, sess, section, yy, mm, [r for r in rows if not r.blank],
                         categories=cats, blank_rows=sum(r.blank for r in rows) + bulk.GRID_ADD_ROWS)

    @app.post("/{section}/saisie", response_class=HTMLResponse)
    def bulk_save(request: Request, section: str, y: int = Form(...), m: int = Form(...),
                  keep: list[str] = Form([]), amount: list[str] = Form([]),
                  cat: list[str] = Form([]), label: list[str] = Form([]),
                  extra: list[str] = Form([]), csrf: str = Form("")):
        if section not in BULK_SECTIONS:
            return Response(status_code=404)
        sid, sess = load(request)
        check_csrf(sess, csrf)
        yy, mm = month_params(sid, sess, str(y), str(m))
        kind = SECTIONS[section][0]
        try:
            rows = bulk.rows_from_form(keep, amount, cat, label, extra)
        except ValueError as exc:
            raise BackendError(400, str(exc)) from None
        cats = call(sid, sess, "finance", "GET", "/v1/categories")

        def again(message: str, status: int = 422):
            return bulk_page(request, sid, sess, section, yy, mm,
                             [r for r in rows if not r.blank], categories=cats,
                             error=message, status_code=status)

        payload = bulk.validate(rows, kind, cats)
        if any(r.errors for r in rows):
            return again("Corrigez les lignes signalées : rien n'a été enregistré.")
        if not payload:
            return again("Aucune ligne à enregistrer.")
        if len(payload) > bulk.MAX_ROWS:
            return again(f"{len(payload)} lignes : {bulk.MAX_ROWS} maximum par enregistrement.")
        try:
            n = call(sid, sess, "finance", "POST", f"/v1/{kind}/batch",
                     json={"year": yy, "month": mm, "rows": payload})["created"]
        except BackendError as exc:           # la grille est conservée
            return again(f"{exc.message} Rien n'a été enregistré.",
                         exc.status if 400 <= exc.status < 600 else 502)
        noun = "dépense(s)" if kind == "expenses" else "revenu(s)"
        flash(sid, sess, f"{n} {noun} enregistré(e)s.")
        return redirect(f"/{section}?y={yy}&m={mm}")

    # ── Saisies (routes génériques en dernier) ───────────────
    @app.get("/{section}", response_class=HTMLResponse)
    def list_entries(request: Request, section: str, y: Optional[str] = None,
                     m: Optional[str] = None):
        if section not in SECTIONS:
            return Response(status_code=404)
        kind, title = SECTIONS[section]
        sid, sess = load(request)
        yy, mm = month_params(sid, sess, y, m)
        if kind == "expenses":
            data, cats, payees = call_parallel(
                sid, sess,
                ("finance", "GET", f"/v1/months/{yy}/{mm}/entries"),
                ("finance", "GET", "/v1/categories"),
                ("finance", "GET", "/v1/payees"))
        else:
            data, cats, payees = call(sid, sess, "finance", "GET", f"/v1/months/{yy}/{mm}/entries"), [], []
        rows = data[kind]
        return render(request, "entries.html", sid, sess, active=section, section=section,
                      title=title, y=yy, m=mm, prev=shift_month(yy, mm, -1), next=shift_month(yy, mm, 1),
                      rows=rows, total=sum(r["amount"] for r in rows), categories=cats,
                      payees=payees, closed=data["closed"], month_actions=True,
                      ai_enabled=bool(sess.get("ai_consent")))

    @app.post("/{section}")
    def add_entry(request: Request, section: str, y: int = Form(...), m: int = Form(...),
                  amount: str = Form(""), label: str = Form(""), category_id: str = Form(""),
                  payee: str = Form(""), source: str = Form(""), account: str = Form(""),
                  csrf: str = Form("")):
        if section not in SECTIONS:
            return Response(status_code=404)
        sid, sess = load(request)
        check_csrf(sess, csrf)
        kind = SECTIONS[section][0]
        yy, mm = month_params(sid, sess, str(y), str(m))
        body = entry_payload(kind, amount, label, category_id, payee, source, account)
        row = call(sid, sess, "finance", "POST", f"/v1/{kind}", json={**body, "year": yy, "month": mm})
        msg = {"expenses": "Dépense ajoutée.", "revenues": "Revenu ajouté.",
               "savings": "Épargne ajoutée."}[kind]
        if kind == "savings" and row.get("linked_asset_name"):
            msg += f" Compte « {row['linked_asset_name']} » mis à jour dans le patrimoine."
        flash(sid, sess, msg)
        return redirect(f"/{section}?y={yy}&m={mm}")

    @app.get("/{section}/{entry_id}/modifier", response_class=HTMLResponse)
    def edit_form(request: Request, section: str, entry_id: int):
        if section not in SECTIONS:
            return Response(status_code=404)
        kind, title = SECTIONS[section]
        sid, sess = load(request)
        if kind == "expenses":
            entry, cats = call_parallel(sid, sess,
                                        ("finance", "GET", f"/v1/entries/{kind}/{entry_id}"),
                                        ("finance", "GET", "/v1/categories"))
        else:
            entry, cats = call(sid, sess, "finance", "GET", f"/v1/entries/{kind}/{entry_id}"), []
        return render(request, "edit.html", sid, sess, active=section, section=section,
                      title=title, entry=entry, categories=cats, closed=entry["closed"])

    @app.post("/{section}/{entry_id}/modifier")
    def edit_entry(request: Request, section: str, entry_id: int, amount: str = Form(""),
                   label: str = Form(""), category_id: str = Form(""), payee: str = Form(""),
                   source: str = Form(""), account: str = Form(""), csrf: str = Form("")):
        if section not in SECTIONS:
            return Response(status_code=404)
        sid, sess = load(request)
        check_csrf(sess, csrf)
        kind = SECTIONS[section][0]
        body = entry_payload(kind, amount, label, category_id, payee, source, account)
        entry = call(sid, sess, "finance", "GET", f"/v1/entries/{kind}/{entry_id}")
        call(sid, sess, "finance", "PUT", f"/v1/{kind}/{entry_id}", json=body)
        flash(sid, sess, "Modification enregistrée.")
        return redirect(f"/{section}?y={entry['year']}&m={entry['month']}")

    @app.post("/{section}/{entry_id}/supprimer")
    def delete_entry(request: Request, section: str, entry_id: int, csrf: str = Form("")):
        if section not in SECTIONS:
            return Response(status_code=404)
        sid, sess = load(request)
        check_csrf(sess, csrf)
        res = call(sid, sess, "finance", "DELETE", f"/v1/{SECTIONS[section][0]}/{entry_id}")
        flash(sid, sess, "Élément supprimé.")
        return redirect(f"/{section}?y={res['year']}&m={res['month']}")
