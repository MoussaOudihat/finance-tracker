"""v2.2 : mois par défaut, clôture, contexte IA (mois vides / partiels),
patrimoine, vue épargne, ajout de lignes en saisie en masse."""
import datetime as dt

import pytest

from finance_api.app import ledger
from test_ai_service import H as AI_H, make  # noqa: F401 — fixture réutilisée
from test_finance_api import _add, api, h, notifier  # noqa: F401 — fixtures réutilisées
from test_web import csrf, login, setup  # noqa: F401
from web.app import bulk


class _Today(dt.date):
    @classmethod
    def today(cls):
        return cls(2026, 11, 6)


@pytest.fixture
def frozen(monkeypatch):
    monkeypatch.setattr(ledger, "date", _Today)


# ── finance-api ──────────────────────────────────────────────

def test_last_month_skips_empty_and_future_months(api, user_id, frozen):  # noqa: F811
    assert api.get("/v1/last-month", headers=h(user_id)).json() is None
    _add(api, user_id, 2026, 9, 1, 10)
    _add(api, user_id, 2030, 2, 1, 10)                       # saisie de test future
    r = api.post("/v1/expenses", headers=h(user_id), json={
        "year": 2026, "month": 10, "category_id": 1, "amount": 5})
    api.delete(f"/v1/expenses/{r.json()['id']}", headers=h(user_id))   # mois vidé
    assert api.get("/v1/last-month", headers=h(user_id)).json() == {"year": 2026, "month": 9}


def test_close_and_reopen_month(api, user_id):  # noqa: F811
    _add(api, user_id, 2026, 9, 1, 10)
    body = {"year": 2026, "month": 9, "category_id": 1, "amount": 3}
    r = api.put("/v1/months/2026/9/closed", headers=h(user_id), json={"closed": True})
    assert r.json() == {"year": 2026, "month": 9, "closed": True}
    assert api.post("/v1/expenses", headers=h(user_id), json=body).status_code == 409
    api.put("/v1/months/2026/9/closed", headers=h(user_id), json={"closed": False})
    assert api.post("/v1/expenses", headers=h(user_id), json=body).status_code == 201


def test_ai_context_ignores_empty_and_partial_months(api, user_id, frozen):  # noqa: F811
    # août et octobre saisis, septembre vide, novembre en cours (partiel)
    _add(api, user_id, 2026, 8, 1, 100)
    _add(api, user_id, 2026, 10, 1, 200)
    _add(api, user_id, 2026, 11, 1, 30)
    ctx = api.get("/v1/ai-context", headers=h(user_id),
                  params={"year": 2026, "month": 11, "months": 3}).json()
    assert [p["period"] for p in ctx["per_month"]] == ["2026-08", "2026-10", "2026-11"]
    assert [p["partial"] for p in ctx["per_month"]] == [False, False, True]
    assert ctx["averages_per_month"]["exp"] == 150.0      # (100 + 200) / 2, ni 0 ni novembre
    assert ctx["averages_months"] == 2 and ctx["top_categories"][0]["per_month"] == 150.0
    assert any("2026-09" in n for n in ctx["notes"]) and any("partielles" in n for n in ctx["notes"])
    assert ctx["per_month"][1]["categories"] == {"ALIMENTATION": 200.0}
    # mois futur demandé : ramené au mois en cours ; un seul mois : pas de moyenne vide
    ctx = api.get("/v1/ai-context", headers=h(user_id),
                  params={"year": 2030, "month": 2, "months": 1}).json()
    assert [p["period"] for p in ctx["per_month"]] == ["2026-11"]
    assert ctx["averages_per_month"]["exp"] == 30.0


def test_assets_and_liabilities(api, user_id, seeded):  # noqa: F811
    H = h(user_id)
    r = api.put("/v1/assets", headers=H, json={"year": 2026, "month": 10, "asset_type": "bourse",
                                               "name": "PEA", "value": 1000, "cost_basis": 800})
    assert r.status_code == 200, r.text
    api.put("/v1/assets", headers=H, json={"year": 2026, "month": 11, "asset_type": "bourse",
                                           "name": "PEA", "value": 1100})
    api.put("/v1/assets", headers=H, json={"year": 2026, "month": 11, "asset_type": "bourse",
                                           "name": "PEA", "value": 1200})       # même mois : mis à jour
    assert len(seeded.tables["assets"]) == 2                                     # historique conservé
    a = api.get("/v1/patrimoine", headers=H).json()["assets"][0]
    assert (a["month"], a["value"], a["cost_basis"]) == (11, 1200, 800)          # investi repris

    api.put("/v1/liabilities", headers=H, json={"year": 2026, "month": 10, "name": "Prêt auto",
                                                "liability_type": "voiture",
                                                "remaining_capital": 5000, "monthly_payment": 200})
    api.put("/v1/liabilities", headers=H, json={"year": 2026, "month": 11, "name": "Prêt auto",
                                                "liability_type": "voiture", "remaining_capital": 4800})
    pat = api.get("/v1/patrimoine", headers=H).json()
    assert pat["liabilities"][0]["monthly_payment"] == 200 and pat["net_worth"] == 1200 - 4800

    assert api.put("/v1/assets", headers=H, json={"year": 2026, "month": 11, "asset_type": "action",
                                                  "name": "X", "value": 1}).status_code == 422
    assert api.put("/v1/assets", headers=H, json={"year": 2026, "month": 11, "asset_type": "autre",
                                                  "name": "X", "value": -1}).status_code == 422
    assert api.post("/v1/assets/delete", headers=H,
                    json={"asset_type": "bourse", "name": "PEA"}).json() == {"deleted": 2}
    assert api.post("/v1/assets/delete", headers=H,
                    json={"asset_type": "bourse", "name": "PEA"}).status_code == 404
    assert api.post("/v1/liabilities/delete", headers=H, json={"name": "Prêt auto"}).json() == {"deleted": 2}


def test_savings_overview(api, user_id, seeded):  # noqa: F811
    H = h(user_id)
    for m in (9, 10):
        api.post("/v1/revenues", headers=H, json={"year": 2026, "month": m, "source": "Salaire",
                                                  "amount": 2000})
    api.post("/v1/savings", headers=H, json={"year": 2026, "month": 9, "account": "Livret A", "amount": 300})
    api.post("/v1/savings", headers=H, json={"year": 2026, "month": 10, "account": "PEA", "amount": 200})
    seeded.seed("savings_goals", [{"id": 1, "user_id": user_id, "name": "Voyage", "target_amount": 1000,
                                   "target_date": "2027-06", "current_amount": 250}])
    ov = api.get("/v1/savings-overview?year=2026&month=10", headers=H).json()
    assert ov["total"] == 500 and ov["months_with_data"] == 2 and ov["average"] == 250
    assert ov["rate"] == 12.5
    assert ov["by_account"][0] == {"account": "Livret A", "total": 300}
    assert ov["goals"][0]["pct"] == 25.0
    assert len(ov["per_month"]) == 12 and ov["per_month"][-1]["has_data"]
    assert not ov["per_month"][0]["has_data"]


# ── ai-service ───────────────────────────────────────────────

def test_chat_prompt_asks_for_a_direct_answer(make):  # noqa: F811
    c, prov = make()
    r = c.post("/v1/chat", headers=AI_H, json={"year": 2026, "month": 10,
                                               "messages": [{"role": "user", "content": "Restos ?"}]})
    assert r.status_code == 200
    intro = prov.calls[0][1][0]["content"]
    assert "Loyer" in intro and "directement à la question" in intro


# ── web ──────────────────────────────────────────────────────

def test_web_close_month(setup):  # noqa: F811
    c, *_ = setup
    login(c)
    page = c.get("/depenses?y=2026&m=9").text
    assert "Clôturer le mois" in page
    tok = csrf(page)
    back = {"referer": "http://testserver/depenses?y=2026&m=9"}
    r = c.post("/mois/cloture", data={"y": 2026, "m": 9, "action": "close", "csrf": tok},
               headers=back, follow_redirects=False)
    assert r.status_code == 303 and r.headers["location"] == "/depenses?y=2026&m=9"
    page = c.get("/depenses?y=2026&m=9").text
    assert "Rouvrir le mois" in page and 'id="entry-form"' not in page
    c.post("/mois/cloture", data={"y": 2026, "m": 9, "action": "reopen", "csrf": tok}, headers=back)
    assert 'id="entry-form"' in c.get("/depenses?y=2026&m=9").text


def test_web_patrimoine_and_savings_view(setup):  # noqa: F811
    c, *_ = setup
    login(c)
    tok = csrf(c.get("/patrimoine").text)
    r = c.post("/patrimoine/actif", data={"asset_type": "compte", "name": "Livret A",
                                          "value": "1 500,00", "period": "2026-10", "csrf": tok},
               follow_redirects=False)
    assert r.status_code == 303
    r = c.post("/patrimoine/passif", data={"name": "Prêt auto", "liability_type": "voiture",
                                           "remaining_capital": "4 000", "monthly_payment": "200",
                                           "period": "2026-10", "end_date": "2028-06", "csrf": tok},
               follow_redirects=False)
    assert r.status_code == 303
    page = c.get("/patrimoine").text
    assert "<td>Livret A</td>" in page and "<td>Prêt auto</td>" in page and "Valeur au mois de" in page
    r = c.post("/patrimoine/actif", data={"asset_type": "compte", "name": "X", "value": "1",
                                          "period": "2026-13", "csrf": tok})
    assert "Mois de valeur invalide" in r.text
    c.post("/patrimoine/passif/supprimer", data={"name": "Prêt auto", "csrf": tok})
    assert "<td>Prêt auto</td>" not in c.get("/patrimoine").text

    c.post("/epargne", data={"y": 2026, "m": 10, "amount": "100", "account": "Livret A",
                             "label": "", "csrf": tok})
    assert "/epargne/vue?y=2026&m=10" in c.get("/epargne?y=2026&m=10").text
    view = c.get("/epargne/vue?y=2026&m=10")
    assert view.status_code == 200 and "Taux d'épargne" in view.text and "Livret A" in view.text


def test_web_bulk_add_rows_and_blank_checked_rows(setup):  # noqa: F811
    c, *_ = setup
    login(c)
    tok = csrf(c.get("/depenses/saisie?y=2026&m=9").text)
    form = {"y": 2026, "m": 9, "keep": [str(i) for i in range(12)],
            "amount": ["5"] * 10 + ["", ""], "cat": ["1"] * 10 + ["", ""],
            "label": ["x"] * 10 + ["", ""], "extra": [""] * 12, "csrf": tok}
    r = c.post("/depenses/saisie/lignes", data=form)
    assert r.status_code == 200
    assert r.text.count('name="amount"') == 10 + 2 + bulk.GRID_ADD_ROWS
    # 10 lignes remplies + 2 vides restées cochées : tout est enregistré
    r = c.post("/depenses/saisie", data=form, follow_redirects=False)
    assert r.status_code == 303
    assert "10 dépense(s) enregistré(e)s" in c.get("/depenses?y=2026&m=9").text


def test_web_ai_page_has_month_navigation(setup):  # noqa: F811
    c, *_ = setup
    login(c)
    page = c.get("/ia?y=2026&m=10").text
    assert "Analyse jusqu'à" in page and "?y=2026&m=9" in page
