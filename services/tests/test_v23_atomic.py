"""v2.3 — Écritures atomiques (fintrack_apply), version de synchro avancée
dans la même transaction, recherche par montant filtrée par la base."""
from test_finance_api import api, h, notifier  # noqa: F401


def _sync_version(db, uid):
    return next((r["value"] for r in db.tables.get("app_settings", [])
                 if r["user_id"] == uid and r["key"] == "last_supabase_sync"), None)


def test_each_business_write_is_one_transaction(api, user_id, seeded):  # noqa: F811
    seeded.seed("recurring_transactions", [
        {"id": 1, "user_id": user_id, "label": "Loyer", "amount": 800, "type": "expense",
         "category_id": 3, "source": "", "payee": "", "active": 1,
         "last_applied_year": 0, "last_applied_month": 0},
        {"id": 2, "user_id": user_id, "label": "Salaire", "amount": 2500, "type": "revenue",
         "category_id": None, "source": "Salaire", "payee": "", "active": 1,
         "last_applied_year": 0, "last_applied_month": 0}])
    r = api.post("/v1/recurring/apply", headers=h(user_id), json={
        "year": 2026, "month": 9, "items": [{"id": 1, "amount": 800}, {"id": 2, "amount": 2500}]})
    assert r.status_code == 200, r.text
    assert len(seeded.rpc_calls) == 1            # saisies + marquage : une seule transaction
    assert {r["last_applied_month"] for r in seeded.tables["recurring_transactions"]} == {9}


RECURRING = [
    {"id": 1, "label": "Salaire", "amount": 2500, "type": "revenue", "category_id": None,
     "source": "Salaire", "payee": "", "active": 1, "last_applied_year": 0, "last_applied_month": 0},
    {"id": 2, "label": "Loyer", "amount": 800, "type": "expense", "category_id": 3,
     "source": "", "payee": "", "active": 1, "last_applied_year": 0, "last_applied_month": 0}]


def test_concurrent_recurring_apply_rolls_everything_back(api, user_id, seeded):  # noqa: F811
    seeded.seed("recurring_transactions", [{**r, "user_id": user_id} for r in RECURRING])
    real = seeded.rpc_apply

    def racing(uid, ops):
        # Une autre requête applique « Loyer » entre la lecture et l'écriture
        seeded.tables["recurring_transactions"][1].update(last_applied_year=2026, last_applied_month=9)
        return real(uid, ops)
    seeded.rpc_apply = racing
    r = api.post("/v1/recurring/apply", headers=h(user_id), json={
        "year": 2026, "month": 9, "items": [{"id": 1, "amount": 2500}, {"id": 2, "amount": 800}]})
    assert r.status_code == 409 and "entre-temps" in r.json()["detail"]
    # rien n'a été écrit : ni saisie, ni marquage, ni version de synchro
    assert seeded.tables.get("revenues", []) == [] and seeded.tables.get("expenses", []) == []
    assert seeded.tables["recurring_transactions"][0]["last_applied_month"] == 0
    assert _sync_version(seeded, user_id) is None
    seeded.rpc_apply = real
    # nouvel essai sur la ligne restante : une seule saisie, pas de doublon
    assert api.post("/v1/recurring/apply", headers=h(user_id), json={
        "year": 2026, "month": 9, "items": [{"id": 1, "amount": 2500}]}).status_code == 200
    assert len(seeded.tables["revenues"]) == 1


def test_recurring_with_deleted_category_is_a_clear_error(api, user_id, seeded):  # noqa: F811
    seeded.seed("recurring_transactions", [{**RECURRING[1], "category_id": 999, "user_id": user_id}])
    r = api.post("/v1/recurring/apply", headers=h(user_id), json={
        "year": 2026, "month": 9, "items": [{"id": 2, "amount": 800}]})
    assert r.status_code == 422 and "catégorie supprimée" in r.json()["detail"]


def test_closed_month_write_changes_nothing(api, user_id, seeded):  # noqa: F811
    seeded.seed("months", [{"id": 1, "user_id": user_id, "year": 2026, "month": 2, "closed": 1}])
    r = api.post("/v1/expenses/batch", headers=h(user_id), json={
        "year": 2026, "month": 2, "rows": [{"category_id": 1, "amount": 5}]})
    assert r.status_code == 409 and "clôturé" in r.json()["detail"]
    assert seeded.tables.get("expenses", []) == [] and _sync_version(seeded, user_id) is None


def test_write_bumps_sync_version_in_same_transaction(api, user_id, seeded):  # noqa: F811
    api.put("/v1/budgets/2026/3", headers=h(user_id), json={"category": "LOGEMENT", "amount": 900})
    v1 = _sync_version(seeded, user_id)
    assert v1
    api.put("/v1/budgets/2026/3", headers=h(user_id), json={"category": "LOGEMENT", "amount": 950})
    assert _sync_version(seeded, user_id) != v1
    assert [b["amount"] for b in seeded.tables["budgets"]] == [950]     # upsert, pas de doublon
    api.put("/v1/budgets/2026/3", headers=h(user_id), json={"category": "LOGEMENT", "amount": 0})
    assert seeded.tables["budgets"] == []


def test_copy_budgets_is_one_transaction(api, user_id, seeded):  # noqa: F811
    seeded.seed("budgets", [{"id": i, "user_id": user_id, "year": 2026, "month": 4,
                             "category": c, "amount": 100.0 * i}
                            for i, c in enumerate(["LOGEMENT", "RESTAURANTS", "AUTRES"], start=1)])
    r = api.post("/v1/budgets/2026/5/copy-previous", headers=h(user_id))
    assert r.json() == {"copied": 3} and len(seeded.rpc_calls) == 1
    assert len([b for b in seeded.tables["budgets"] if b["month"] == 5]) == 3


def test_saving_moved_between_accounts_adjusts_both(api, user_id, seeded):  # noqa: F811
    seeded.seed("assets", [
        {"id": 1, "user_id": user_id, "year": 2026, "month": 1, "asset_type": "compte",
         "asset_name": "Livret A", "value": 1000.0, "cost_basis": 1000.0, "notes": ""},
        {"id": 2, "user_id": user_id, "year": 2026, "month": 1, "asset_type": "compte",
         "asset_name": "LDDS", "value": 500.0, "cost_basis": 500.0, "notes": ""}])
    s = api.post("/v1/savings", headers=h(user_id), json={
        "year": 2026, "month": 2, "account": "livret a", "amount": 100}).json()
    assert s["linked_asset_name"] == "Livret A"
    calls = len(seeded.rpc_calls)
    api.put(f"/v1/savings/{s['id']}", headers=h(user_id),
            json={"account": "ldds", "amount": 150, "label": ""})
    assert len(seeded.rpc_calls) == calls + 1
    pat = {a["asset_name"]: a["value"]
           for a in api.get("/v1/patrimoine", headers=h(user_id)).json()["assets"]}
    assert pat == {"Livret A": 1000.0, "LDDS": 650.0}


def test_search_amount_bounds_are_applied_before_the_limit(api, user_id, seeded):  # noqa: F811
    seeded.seed("months", [{"id": 1, "user_id": user_id, "year": 2025, "month": 1, "closed": 0}])
    seeded.seed("expenses", [{"id": 1, "user_id": user_id, "month_id": 1, "category_id": 1,
                              "amount": 5.0, "label": "petit", "payee": ""}])
    seeded.seed("expenses", [{"id": i, "user_id": user_id, "month_id": 1, "category_id": 1,
                              "amount": 100.0, "label": "gros", "payee": ""}
                             for i in range(2, 2105)])
    rows = api.get("/v1/search/expenses", headers=h(user_id),
                   params={"min_amount": 1, "max_amount": 10}).json()
    assert [r["label"] for r in rows] == ["petit"]


def test_missing_migration_is_explicit(api, user_id, seeded, monkeypatch):  # noqa: F811
    import httpx

    def no_rpc(uid, ops):
        return httpx.Response(404, json={"code": "PGRST202", "message": "function not found"})
    monkeypatch.setattr(seeded, "rpc_apply", no_rpc)
    r = api.post("/v1/revenues", headers=h(user_id),
                 json={"year": 2026, "month": 1, "source": "Salaire", "amount": 1})
    assert r.status_code == 503 and "migrée" in r.json()["detail"]


def test_concurrent_savings_on_same_account_add_up(api, user_id, seeded):  # noqa: F811
    """Revue v2.3 : la valeur du compte lié était calculée AVANT la
    transaction (valeur absolue) : deux versements simultanés s'écrasaient.
    Elle est maintenant calculée par la base, sous verrou."""
    seeded.seed("assets", [{"id": 1, "user_id": user_id, "year": 2026, "month": 1,
                            "asset_type": "compte", "asset_name": "Livret A",
                            "value": 1000.0, "cost_basis": 1000.0, "notes": ""}])
    real = seeded.rpc_apply
    state = {"done": False}

    def racing(uid, ops):
        # Un autre versement de 50 € est validé pendant que celui-ci est préparé
        if not state["done"]:
            state["done"] = True
            real(uid, [{"op": "adjust_asset", "asset_name": "Livret A", "year": 2026,
                        "month": 2, "delta": 50.0}])
        return real(uid, ops)
    seeded.rpc_apply = racing
    api.post("/v1/savings", headers=h(user_id), json={
        "year": 2026, "month": 2, "account": "livret a", "amount": 100})
    seeded.rpc_apply = real
    pat = api.get("/v1/patrimoine", headers=h(user_id)).json()
    assert pat["total_assets"] == 1150.0


def test_search_limit_parameter(api, user_id, seeded):  # noqa: F811
    seeded.seed("months", [{"id": 1, "user_id": user_id, "year": 2025, "month": 1, "closed": 0}])
    seeded.seed("expenses", [{"id": i, "user_id": user_id, "month_id": 1, "category_id": 1,
                              "amount": 1.0, "label": "x", "payee": ""} for i in range(1, 301)])
    assert len(api.get("/v1/search/expenses", headers=h(user_id)).json()) == 200
    assert len(api.get("/v1/search/expenses", headers=h(user_id), params={"limit": 300}).json()) == 300
    assert api.get("/v1/search/expenses", headers=h(user_id), params={"limit": 501}).status_code == 422
