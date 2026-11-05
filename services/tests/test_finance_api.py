import json
import uuid

import httpx
import pytest
from fastapi.testclient import TestClient

from conftest import make_token
from finance_api.app.main import create_app


class _Notifier:
    def __init__(self):
        self.events = []

    def post(self, path, json=None, headers=None):
        assert headers["X-Internal-Token"] == "n" * 40
        self.events.append(json)
        return httpx.Response(202)


@pytest.fixture
def notifier():
    return _Notifier()


@pytest.fixture
def api(seeded, verifier, notifier, monkeypatch):
    monkeypatch.setenv("NOTIFIER_INTERNAL_TOKEN", "n" * 40)
    app = create_app(verifier=verifier, supabase_http=seeded.client(), notifier_http=notifier)
    return TestClient(app)


def h(uid):
    return {"Authorization": f"Bearer {make_token(uid)}"}


def test_requires_valid_token(api):
    assert api.get("/v1/categories").status_code == 401
    assert api.get("/v1/categories", headers={"Authorization": "Bearer x.y.z"}).status_code == 401
    assert api.get("/healthz").status_code == 200


def test_expense_crud_and_summary(api, user_id, seeded):
    r = api.post("/v1/expenses", headers=h(user_id), json={
        "year": 2026, "month": 11, "category_id": 1, "amount": 42.5,
        "label": " Courses ", "payee": "lidl"})
    assert r.status_code == 201, r.text
    e = r.json()
    assert e["payee"] == "LIDL" and e["label"] == "Courses" and e["user_id"] == user_id
    s = api.get("/v1/months/2026/11/summary", headers=h(user_id)).json()
    assert s["expenses"] == 42.5 and s["by_category"][0]["name"] == "ALIMENTATION"
    # sync timestamp touché : le desktop saura qu'il doit récupérer avant d'envoyer
    assert any(r["key"] == "last_supabase_sync" for r in seeded.tables["app_settings"])

    r = api.put(f"/v1/expenses/{e['id']}", headers=h(user_id),
                json={"category_id": 3, "amount": 10, "label": "x", "payee": ""})
    assert r.status_code == 200 and r.json()["amount"] == 10
    r = api.delete(f"/v1/expenses/{e['id']}", headers=h(user_id))
    assert r.json() == {"year": 2026, "month": 11}
    assert api.get("/v1/months/2026/11/entries", headers=h(user_id)).json()["expenses"] == []


@pytest.mark.parametrize("amount", ["nan", "inf", -5, 0, 2e9])
def test_invalid_amounts_rejected(api, user_id, amount):
    body = json.dumps({"year": 2026, "month": 11, "category_id": 1, "amount": 1})
    body = body.replace('"amount": 1', f'"amount": {json.dumps(amount) if isinstance(amount, str) else amount}')
    r = api.post("/v1/expenses", headers={**h(user_id), "Content-Type": "application/json"},
                 content=body)
    assert r.status_code == 422


@pytest.mark.parametrize("path", ["/v1/months/2026/13/summary", "/v1/months/1999/1/summary"])
def test_invalid_month_rejected(api, user_id, path):
    assert api.get(path, headers=h(user_id)).status_code == 422


def test_unknown_category_rejected(api, user_id):
    r = api.post("/v1/expenses", headers=h(user_id),
                 json={"year": 2026, "month": 1, "category_id": 999, "amount": 1})
    assert r.status_code == 422


def test_users_are_isolated(api, user_id):
    other = str(uuid.uuid4())
    e = api.post("/v1/expenses", headers=h(user_id), json={
        "year": 2026, "month": 1, "category_id": 1, "amount": 5}).json()
    # l'autre utilisateur ne voit ni ne supprime la ligne
    assert api.get(f"/v1/entries/expenses/{e['id']}", headers=h(other)).status_code == 404
    assert api.delete(f"/v1/expenses/{e['id']}", headers=h(other)).status_code == 404
    assert api.get(f"/v1/entries/expenses/{e['id']}", headers=h(user_id)).status_code == 200


def test_closed_month_is_locked(api, user_id, seeded):
    seeded.seed("months", [{"id": 1, "user_id": user_id, "year": 2026, "month": 2, "closed": 1}])
    r = api.post("/v1/revenues", headers=h(user_id),
                 json={"year": 2026, "month": 2, "source": "Salaire", "amount": 1000})
    assert r.status_code == 409


def test_ids_allocated_per_user(api, user_id, seeded):
    seeded.seed("expenses", [{"id": 41, "user_id": user_id, "month_id": 99, "category_id": 1,
                              "amount": 1, "label": "", "payee": ""}])
    e = api.post("/v1/expenses", headers=h(user_id), json={
        "year": 2026, "month": 3, "category_id": 1, "amount": 2}).json()
    assert e["id"] == 42


def test_budget_alerts_emitted_once_per_threshold(api, user_id, notifier):
    api.put("/v1/budgets/2026/4", headers=h(user_id), json={"category": "RESTAURANTS", "amount": 100})
    def add(a):
        api.post("/v1/expenses", headers=h(user_id),
                 json={"year": 2026, "month": 4, "category_id": 4, "amount": a})
    add(50)
    assert notifier.events == []
    add(35)                                  # 85 % -> alerte 80
    add(5)                                   # 90 % -> rien
    add(20)                                  # 110 % -> alerte 100
    assert [e["threshold"] for e in notifier.events] == [80, 100]
    assert notifier.events[1]["category"] == "RESTAURANTS" and notifier.events[1]["user_id"] == user_id


def test_saving_updates_linked_account(api, user_id, seeded):
    seeded.seed("assets", [{"id": 1, "user_id": user_id, "year": 2026, "month": 1,
                            "asset_type": "compte", "asset_name": "Livret A Bourso",
                            "value": 1000.0, "cost_basis": 1000.0, "notes": ""}])
    s = api.post("/v1/savings", headers=h(user_id), json={
        "year": 2026, "month": 2, "account": "livret a", "amount": 200}).json()
    assert s["linked_asset_name"] == "Livret A Bourso"
    pat = api.get("/v1/patrimoine", headers=h(user_id)).json()
    assert pat["total_assets"] == 1200.0
    api.delete(f"/v1/savings/{s['id']}", headers=h(user_id))
    assert api.get("/v1/patrimoine", headers=h(user_id)).json()["total_assets"] == 1000.0


def test_ai_context_is_aggregated(api, user_id):
    for m, (loyer, resto) in enumerate([(900, 50), (900, 70), (900, 30)], start=1):
        api.post("/v1/expenses", headers=h(user_id), json={
            "year": 2026, "month": m, "category_id": 3, "amount": loyer, "label": "Loyer"})
        api.post("/v1/expenses", headers=h(user_id), json={
            "year": 2026, "month": m, "category_id": 4, "amount": resto, "payee": "chez paul"})
    ctx = api.get("/v1/ai-context", headers=h(user_id),
                  params={"year": 2026, "month": 3, "months": 3}).json()
    assert ctx["top_expenses"][0] == {"name": "Loyer", "per_month": 900.0}
    assert ctx["top_payees"][0] == {"name": "CHEZ PAUL", "per_month": 50.0}
    assert len(ctx["per_month"]) == 3
    assert "label" not in json.dumps(ctx["per_month"])     # pas de lignes brutes


# ── Saisie groupée, récurrentes, recherche ───────────────────

def test_expense_batch_is_atomic(api, user_id, seeded):
    rows = [{"category_id": 1, "amount": 10, "label": "a", "payee": "lidl"},
            {"category_id": 3, "amount": 700, "label": "loyer"}]
    r = api.post("/v1/expenses/batch", headers=h(user_id),
                 json={"year": 2026, "month": 5, "rows": rows})
    assert r.status_code == 201 and r.json() == {"created": 2}
    ids = sorted(e["id"] for e in seeded.tables["expenses"])
    assert ids == [1, 2] and seeded.tables["expenses"][0]["payee"] == "LIDL"
    # une ligne invalide -> rien n'est écrit
    bad = rows + [{"category_id": 1, "amount": -1}]
    assert api.post("/v1/expenses/batch", headers=h(user_id),
                    json={"year": 2026, "month": 5, "rows": bad}).status_code == 422
    unknown = rows + [{"category_id": 999, "amount": 1}]
    assert api.post("/v1/expenses/batch", headers=h(user_id),
                    json={"year": 2026, "month": 5, "rows": unknown}).status_code == 422
    assert len(seeded.tables["expenses"]) == 2


def test_batch_limits_and_closed_month(api, user_id, seeded):
    too_many = [{"category_id": 1, "amount": 1}] * 201
    assert api.post("/v1/expenses/batch", headers=h(user_id),
                    json={"year": 2026, "month": 5, "rows": too_many}).status_code == 422
    assert api.post("/v1/expenses/batch", headers=h(user_id),
                    json={"year": 2026, "month": 5, "rows": []}).status_code == 422
    seeded.seed("months", [{"id": 7, "user_id": user_id, "year": 2026, "month": 1, "closed": 1}])
    assert api.post("/v1/revenues/batch", headers=h(user_id), json={
        "year": 2026, "month": 1, "rows": [{"source": "Salaire", "amount": 1}]}).status_code == 409


def test_expense_batch_emits_budget_alert(api, user_id, notifier):
    api.put("/v1/budgets/2026/6", headers=h(user_id), json={"category": "RESTAURANTS", "amount": 100})
    api.post("/v1/expenses/batch", headers=h(user_id), json={"year": 2026, "month": 6, "rows": [
        {"category_id": 4, "amount": 60}, {"category_id": 4, "amount": 50}]})
    assert [e["threshold"] for e in notifier.events] == [100]


def test_recurring_lifecycle(api, user_id, seeded):
    loyer = api.post("/v1/recurring", headers=h(user_id), json={
        "type": "expense", "label": "Loyer", "amount": 800, "category_id": 3}).json()
    api.post("/v1/recurring", headers=h(user_id), json={
        "type": "revenue", "label": "Salaire", "amount": 2500})
    assert api.post("/v1/recurring", headers=h(user_id), json={
        "type": "expense", "label": "x", "amount": 1}).status_code == 422   # catégorie requise

    rec = api.get("/v1/recurring?year=2026&month=7", headers=h(user_id)).json()
    assert rec["closed"] is False and [r["pending"] for r in rec["items"]] == [True, True]

    items = [{"id": r["id"], "amount": r["amount"] + (15 if r["type"] == "expense" else 0)}
             for r in rec["items"]]
    r = api.post("/v1/recurring/apply", headers=h(user_id),
                 json={"year": 2026, "month": 7, "items": items})
    assert r.json() == {"applied": 2}
    s = api.get("/v1/months/2026/7/summary", headers=h(user_id)).json()
    assert s["expenses"] == 815 and s["revenues"] == 2500
    rec = api.get("/v1/recurring?year=2026&month=7", headers=h(user_id)).json()
    assert not any(r["pending"] for r in rec["items"])
    # double application refusée, rien n'est écrit
    assert api.post("/v1/recurring/apply", headers=h(user_id),
                    json={"year": 2026, "month": 7, "items": items}).status_code == 409
    assert len(seeded.tables["expenses"]) == 1
    # le mois suivant : de nouveau en attente ; désactivée -> plus en attente
    api.put(f"/v1/recurring/{loyer['id']}/active", headers=h(user_id), json={"active": False})
    rec = api.get("/v1/recurring?year=2026&month=8", headers=h(user_id)).json()
    assert {r["label"]: r["pending"] for r in rec["items"]} == {"Loyer": False, "Salaire": True}
    assert api.delete(f"/v1/recurring/{loyer['id']}", headers=h(user_id)).status_code == 204
    assert api.delete(f"/v1/recurring/{loyer['id']}", headers=h(user_id)).status_code == 404


def test_search_filters(api, user_id):
    for (m, cat, amount, label, payee) in [(1, 1, 12, "Courses", "lidl"), (2, 1, 80, "Courses", "carrefour"),
                                           (3, 4, 35, "Pizza", "Lidl"), (3, 3, 700, "Loyer", "")]:
        api.post("/v1/expenses", headers=h(user_id), json={
            "year": 2026, "month": m, "category_id": cat, "amount": amount,
            "label": label, "payee": payee})

    def search(**params):
        return api.get("/v1/search/expenses", headers=h(user_id), params=params).json()
    assert [r["amount"] for r in search(q="lidl")] == [35, 12]       # enseigne, casse ignorée, récent d'abord
    assert [r["label"] for r in search(q="cour", min_amount=50)] == ["Courses"]
    assert [r["amount"] for r in search(category_id=1, max_amount=50)] == [12]
    assert search(q="pizza")[0]["category"] == "RESTAURANTS" and search(q="pizza")[0]["month"] == 3
    assert len(search(q="*")) == 4                                   # joker retiré : = sans filtre texte
    assert api.get("/v1/search/expenses", headers=h(user_id),
                   params={"q": "a,b)(or=x"}).status_code == 200
    assert api.get("/v1/search/budgets", headers=h(user_id)).status_code == 422


def test_search_is_isolated_per_user(api, user_id):
    api.post("/v1/expenses", headers=h(user_id), json={
        "year": 2026, "month": 1, "category_id": 1, "amount": 5, "label": "secret"})
    other = str(uuid.uuid4())
    assert api.get("/v1/search/expenses?q=secret", headers=h(other)).json() == []
