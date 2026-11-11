"""
routes_settings.py — Paramètres (notifications, TickTick) et thème.
"""
from __future__ import annotations

from typing import Optional
from types import SimpleNamespace

from fastapi import FastAPI, Form, Request
from fastapi.responses import HTMLResponse

from .backends import BackendError
from .common import THEME_COOKIE, THEME_LABEL


def register(app: FastAPI, w: SimpleNamespace) -> None:
    """Enregistre les routes de ce module (dépendances partagées dans `w`)."""
    # Dépendances partagées, créées par main.create_app
    back_url, call, check_csrf, cookie_secure = w.back_url, w.call, w.check_csrf, w.cookie_secure
    flash, load, redirect, render = w.flash, w.load, w.redirect, w.render
    ticktick_handoff = w.ticktick_handoff

    # ── Paramètres / notifications ───────────────────────────
    @app.get("/parametres", response_class=HTMLResponse)
    def settings_page(request: Request):
        sid, sess = load(request)
        try:
            prefs = call(sid, sess, "notifier", "GET", "/v1/prefs")
        except BackendError as exc:
            prefs, err = None, exc.message
        else:
            err = None
        projects = []
        if prefs and prefs.get("ticktick_connected"):
            try:
                projects = call(sid, sess, "notifier", "GET", "/v1/ticktick/projects")
            except BackendError as exc:
                err = exc.message
        return render(request, "settings.html", sid, sess, active="parametres", prefs=prefs,
                      projects=projects, notifier_error=err)

    @app.post("/parametres/notifications")
    def save_prefs(request: Request, budget_alerts: str = Form(""),
                   unusual_alerts: str = Form(""),
                   reminder_enabled: str = Form(""), reminder_day: int = Form(1),
                   ntfy_url: str = Form(""), webhook_url: str = Form(""),
                   clear_ntfy: str = Form(""), clear_webhook: str = Form(""),
                   ticktick_project: Optional[str] = Form(None), csrf: str = Form("")):
        sid, sess = load(request)
        check_csrf(sess, csrf)
        body = {"budget_alerts": budget_alerts == "1",
                "unusual_alerts": unusual_alerts == "1",
                "reminder_enabled": reminder_enabled == "1",
                "reminder_day": max(1, min(reminder_day, 28)),
                # champ vide = inchangé (les URLs enregistrées ne sont jamais réaffichées)
                "ntfy_url": "" if clear_ntfy else (ntfy_url.strip() or None),
                "webhook_url": "" if clear_webhook else (webhook_url.strip() or None)}
        if ticktick_project is not None:
            body["ticktick_project"] = ticktick_project
        call(sid, sess, "notifier", "PUT", "/v1/prefs", json=body)
        flash(sid, sess, "Préférences de notification enregistrées.")
        return redirect("/parametres")

    @app.post("/parametres/test")
    def test_notif(request: Request, csrf: str = Form("")):
        sid, sess = load(request)
        check_csrf(sess, csrf)
        res = call(sid, sess, "notifier", "POST", "/v1/test")
        if res["failures"]:
            flash(sid, sess, "Échec sur : " + ", ".join(res["failures"]), "error")
        else:
            flash(sid, sess, "Notification de test envoyée.")
        return redirect("/parametres")

    @app.post("/parametres/ticktick/connecter")
    def ticktick_connect(request: Request, csrf: str = Form("")):
        sid, sess = load(request)
        check_csrf(sess, csrf)
        url = call(sid, sess, "notifier", "POST", "/v1/ticktick/authorize")["url"]
        return ticktick_handoff(request, sid, sess, url)

    @app.get("/parametres/ticktick/callback")
    def ticktick_callback(request: Request, code: str = "", state: str = "",
                          error: str = ""):
        sid, sess = load(request)
        if error or not code or not state:
            flash(sid, sess, "Connexion TickTick annulée.", "error")
            return redirect("/parametres")
        call(sid, sess, "notifier", "POST", "/v1/ticktick/callback",
             json={"code": code[:512], "state": state[:128]})
        flash(sid, sess, "TickTick connecté. Choisissez la liste où créer les tâches.")
        return redirect("/parametres")

    @app.post("/parametres/ticktick/deconnecter")
    def ticktick_disconnect(request: Request, csrf: str = Form("")):
        sid, sess = load(request)
        check_csrf(sess, csrf)
        call(sid, sess, "notifier", "DELETE", "/v1/ticktick")
        flash(sid, sess, "TickTick déconnecté.")
        return redirect("/parametres")

    # ── Thème ────────────────────────────────────────────────
    @app.post("/theme")
    def set_theme(request: Request, theme: str = Form("auto"), csrf: str = Form("")):
        sid, sess = load(request)
        check_csrf(sess, csrf)
        resp = redirect(back_url(request))
        resp.set_cookie(THEME_COOKIE, theme if theme in THEME_LABEL else "auto",
                        max_age=365 * 24 * 3600, path="/", httponly=True,
                        secure=cookie_secure, samesite="lax")
        return resp
