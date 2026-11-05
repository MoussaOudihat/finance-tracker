"""Page Analyses, bilan IA envoyé sur les notifications, préférence d'alerte."""
import json
import re

import httpx

from fintrack_common.http import service_client
from test_web import csrf, login, setup  # noqa: F401 — fixture réutilisée
from web.app.main import line_points


def _seed(c, tok):
    for m in range(4, 10):
        for amount, cat in (("100", "1"), ("800", "3")):
            c.post("/depenses", data={"y": 2026, "m": m, "amount": amount, "label": "",
                                      "payee": "", "category_id": cat, "csrf": tok})
    for amount, cat in (("320", "1"), ("800", "3")):
        c.post("/depenses", data={"y": 2026, "m": 10, "amount": amount, "label": "",
                                  "payee": "", "category_id": cat, "csrf": tok})


def _fake(c, service, handler):
    c.app.state.backends.clients[service] = service_client(
        f"http://{service}", transport=httpx.MockTransport(handler))


def test_line_points():
    assert line_points([], 10) == ""
    assert line_points([0, 10], 10) == "0.00,38.00 100.00,2.00"
    assert line_points([5], 0) == "0.00,2.00"             # pas de division par zéro, borné
    assert line_points([-3, 99], 10) == "0.00,38.00 100.00,2.00"   # hors bornes : écrêté


def test_analyses_page(setup):  # noqa: F811
    c, *_ = setup
    login(c)
    _seed(c, csrf(c.get("/depenses?y=2026&m=10").text))
    page = c.get("/analyses?y=2026&m=10")
    assert page.status_code == 200 and 'aria-current="page"' in page.text
    html = page.text
    assert html.count('<polyline class="line') >= 3 + 2        # tendance + sparklines
    assert "inhabituel" in html and "ALIMENTATION</strong> : 320,00" in html
    assert "+220 %" in html                                     # 320 vs 100 le mois précédent
    assert "style=" not in html                                 # CSP : aucun style inline
    assert "Activez l" in html                                  # IA non activée
    # mois sans historique : message explicite, pas d'erreur
    assert "au moins 3 mois" in c.get("/analyses?y=2026&m=5").text


def test_report_generated_and_sent(setup):  # noqa: F811
    c, _, sessions = setup
    login(c)
    sid = c.cookies["fintrack_sid"]
    sessions.update(sid, ai_consent=True, ai_provider="claude")
    sent = []
    _fake(c, "ai", lambda r: httpx.Response(200, json={
        "provider": "claude", "text": "- **Bien** : <b>épargne</b> en hausse"}))

    def notifier(request):
        sent.append(json.loads(request.content))
        return httpx.Response(200, json={"failures": []})
    _fake(c, "notifier", notifier)
    tok = csrf(c.get("/analyses?y=2026&m=10").text)
    r = c.post("/analyses/bilan", data={"y": 2026, "m": 10, "send": "1", "csrf": tok},
               follow_redirects=False)
    assert r.status_code == 303 and r.headers["location"] == "/analyses?y=2026&m=10"
    assert sent == [{"year": 2026, "month": 10, "text": "- **Bien** : <b>épargne</b> en hausse"}]
    page = c.get("/analyses?y=2026&m=10").text
    assert "envoyé sur vos notifications" in page and "<strong>Bien</strong>" in page
    assert "<b>épargne</b>" not in page                         # texte IA échappé
    assert "Bilan généré" not in c.get("/analyses?y=2026&m=9").text   # bilan propre au mois

    # notifier en échec : le bilan est quand même affiché, message d'erreur
    _fake(c, "notifier", lambda r: httpx.Response(409, json={"detail": "Aucun canal de notification configuré."}))
    page = c.post("/analyses/bilan", data={"y": 2026, "m": 10, "send": "1", "csrf": tok}).text
    assert "non envoyé : Aucun canal" in page and "<strong>Bien</strong>" in page


def test_report_requires_ai_consent_and_csrf(setup):  # noqa: F811
    c, *_ = setup
    login(c)
    tok = csrf(c.get("/analyses?y=2026&m=10").text)
    page = c.post("/analyses/bilan", data={"y": 2026, "m": 10, "csrf": tok},
                  headers={"referer": "http://testserver/analyses?y=2026&m=10"}).text
    assert "Activez d&#39;abord" in page
    r = c.post("/analyses/bilan", data={"y": 2026, "m": 10, "csrf": "forged"},
               follow_redirects=False)
    assert r.status_code == 303


def test_unusual_alerts_preference_is_sent(setup):  # noqa: F811
    c, *_ = setup
    login(c)
    puts = []

    def notifier(request):
        if request.method == "PUT":
            puts.append(json.loads(request.content))
            return httpx.Response(200, json={})
        return httpx.Response(200, json={"budget_alerts": True, "unusual_alerts": True,
                                         "reminder_enabled": False, "reminder_day": 1,
                                         "ticktick_connected": False, "ticktick_available": False,
                                         "ticktick_project": "", "ntfy_configured": False,
                                         "webhook_configured": False, "allowed_hosts": []})
    _fake(c, "notifier", notifier)
    page = c.get("/parametres").text
    assert re.search(r'name="unusual_alerts" value="1" checked', page)
    c.post("/parametres/notifications", data={"budget_alerts": "1", "reminder_day": "1",
                                              "csrf": csrf(page)})
    assert puts[-1]["unusual_alerts"] is False and puts[-1]["budget_alerts"] is True
