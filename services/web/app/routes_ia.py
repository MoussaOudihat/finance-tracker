"""
routes_ia.py — Assistant IA et analyses.
"""
from __future__ import annotations

from typing import Optional
from types import SimpleNamespace

from fastapi import FastAPI, Form, Header, Request
from fastapi.responses import HTMLResponse, JSONResponse

from fintrack_common.fmt import shift_month

from .backends import BackendError
from .common import CHAT_MAX_MESSAGES, COOKIE, CategorizeReq, MONTHS_FR, line_points, render_ai_text


def register(app: FastAPI, w: SimpleNamespace) -> None:
    """Enregistre les routes de ce module (dépendances partagées dans `w`)."""
    # Dépendances partagées, créées par main.create_app
    call, check_csrf, flash, load = w.call, w.check_csrf, w.flash, w.load
    month_params, redirect, render, sessions = w.month_params, w.redirect, w.render, w.sessions

    # ── IA ───────────────────────────────────────────────────
    def ai_state(sid, sess) -> dict:
        try:
            return call(sid, sess, "ai", "GET", "/v1/providers")
        except BackendError:
            return {"providers": [], "daily_limit": 0, "remaining": 0}

    @app.get("/ia", response_class=HTMLResponse)
    def ia_page(request: Request, y: Optional[str] = None, m: Optional[str] = None):
        sid, sess = load(request)
        yy, mm = month_params(sid, sess, y, m)
        st = ai_state(sid, sess)
        chat = sess.get("chat", [])
        return render(request, "ia.html", sid, sess, active="ia", y=yy, m=mm, ai=st,
                      prev=shift_month(yy, mm, -1), next=shift_month(yy, mm, 1),
                      provider=sess.get("ai_provider") or (st["providers"] or ["claude"])[0],
                      consent=sess.get("ai_consent", False),
                      insight=render_ai_text(sess.get("insight", {}).get("text", "")),
                      insight_meta=sess.get("insight", {}),
                      chat=[{"role": c["role"], "html": render_ai_text(c["content"])
                             if c["role"] == "assistant" else c["content"]} for c in chat])

    def ai_common(sess, provider: str, consent: str) -> str:
        if provider not in ("claude", "gemini"):
            raise BackendError(422, "Fournisseur IA inconnu.")
        if consent != "1" and not sess.get("ai_consent"):
            raise BackendError(400, "Cochez la case de consentement avant d'utiliser l'IA.")
        sess["ai_consent"] = True
        sess["ai_provider"] = provider
        return provider

    @app.post("/ia/analyse")
    def ia_insights(request: Request, y: int = Form(...), m: int = Form(...),
                    months: int = Form(3), provider: str = Form("claude"),
                    consent: str = Form(""), csrf: str = Form("")):
        sid, sess = load(request)
        check_csrf(sess, csrf)
        provider = ai_common(sess, provider, consent)
        res = call(sid, sess, "ai", "POST", "/v1/insights", timeout=120.0,
                   json={"provider": provider, "year": y, "month": m,
                         "months": max(1, min(months, 12))})
        sessions.update(sid, ai_consent=True, ai_provider=provider,
                        insight={"text": res["text"], "provider": provider,
                                 "period": f"{MONTHS_FR[m - 1]} {y}", "months": months})
        return redirect(f"/ia?y={y}&m={m}")

    @app.post("/ia/chat")
    def ia_chat(request: Request, y: int = Form(...), m: int = Form(...),
                question: str = Form(""), provider: str = Form("claude"),
                consent: str = Form(""), csrf: str = Form("")):
        sid, sess = load(request)
        check_csrf(sess, csrf)
        provider = ai_common(sess, provider, consent)
        q = question.strip()[:2000]
        if not q:
            raise BackendError(422, "Posez une question.")
        history = (sess.get("chat", []) + [{"role": "user", "content": q}])[-CHAT_MAX_MESSAGES:]
        if history[0]["role"] != "user":
            history = history[1:]
        res = call(sid, sess, "ai", "POST", "/v1/chat", timeout=120.0,
                   json={"provider": provider, "year": y, "month": m, "messages": history})
        sessions.update(sid, ai_consent=True, ai_provider=provider,
                        chat=(history + [{"role": "assistant", "content": res["text"]}])[-CHAT_MAX_MESSAGES:])
        return redirect(f"/ia?y={y}&m={m}#chat")

    @app.post("/ia/chat/effacer")
    def ia_chat_clear(request: Request, y: int = Form(...), m: int = Form(...),
                      csrf: str = Form("")):
        sid, sess = load(request)
        check_csrf(sess, csrf)
        sessions.update(sid, chat=[])
        return redirect(f"/ia?y={y}&m={m}#chat")

    @app.post("/api/categorize")
    def api_categorize(request: Request, body: CategorizeReq,
                       x_csrf_token: str = Header("")):
        sid = request.cookies.get(COOKIE)
        sess = sessions.get(sid)
        if sess is None:
            return JSONResponse({"detail": "Session expirée."}, status_code=401)
        check_csrf(sess, x_csrf_token)
        if not sess.get("ai_consent"):
            raise BackendError(400, "Activez d'abord l'IA depuis la page « Assistant IA ».")
        return call(sid, sess, "ai", "POST", "/v1/categorize", timeout=60.0,
                    json={"provider": sess.get("ai_provider") or "claude",
                          "label": body.label, "payee": body.payee})

    # ── Analyses ─────────────────────────────────────────────
    @app.get("/analyses", response_class=HTMLResponse)
    def analyses(request: Request, y: Optional[str] = None, m: Optional[str] = None):
        sid, sess = load(request)
        yy, mm = month_params(sid, sess, y, m)
        an = call(sid, sess, "finance", "GET", "/v1/analytics",
                  params={"year": yy, "month": mm, "months": 12})
        pm = an["per_month"]
        top = max((max(p["rev"], p["exp"], p["sav"]) for p in pm), default=0.0)
        lines = {k: line_points([p[k] for p in pm], top) for k in ("rev", "exp", "sav")}
        lines["max"] = top
        sparks = {c["category"]: line_points(c["series"], max(c["series"]) or 1.0)
                  for c in an["categories"]}
        report = sess.get("report") or {}
        return render(request, "analyses.html", sid, sess, active="analyses", y=yy, m=mm,
                      prev=shift_month(yy, mm, -1), next=shift_month(yy, mm, 1), closed=False,
                      an=an, lines=lines, sparks=sparks, ai_enabled=bool(sess.get("ai_consent")),
                      period=f"{yy}-{mm:02d}", report=report,
                      report_html=render_ai_text(report.get("text", "")))

    @app.post("/analyses/bilan")
    def analyses_report(request: Request, y: int = Form(...), m: int = Form(...),
                        send: str = Form(""), csrf: str = Form("")):
        sid, sess = load(request)
        check_csrf(sess, csrf)
        yy, mm = month_params(sid, sess, str(y), str(m))
        if not sess.get("ai_consent"):
            raise BackendError(400, "Activez d'abord l'IA depuis la page « Assistant IA ».")
        provider = sess.get("ai_provider") or "claude"
        res = call(sid, sess, "ai", "POST", "/v1/insights", timeout=120.0,
                   json={"provider": provider, "year": yy, "month": mm, "months": 3})
        report = {"text": res["text"], "provider": provider, "period": f"{yy}-{mm:02d}",
                  "sent": False}
        message, kind = "Bilan généré.", "ok"
        if send == "1":
            try:
                out = call(sid, sess, "notifier", "POST", "/v1/report",
                           json={"year": yy, "month": mm, "text": res["text"]})
                report["sent"] = True
                message = "Bilan généré et envoyé sur vos notifications."
                if out.get("failures"):
                    message += f" Échec sur : {', '.join(out['failures'])}."
            except BackendError as exc:              # le bilan reste affiché
                message, kind = f"Bilan généré, mais non envoyé : {exc.message}", "error"
        sessions.update(sid, report=report)
        flash(sid, sess, message, kind)
        return redirect(f"/analyses?y={yy}&m={mm}")
