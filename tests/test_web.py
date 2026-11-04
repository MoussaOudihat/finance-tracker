"""Tests de l'interface web (mode d'authentification local, sans Supabase)."""
import re

import bcrypt
import pytest
from fastapi.testclient import TestClient

from web.main import create_app
from web.settings import ConfigError, WebSettings
from web.workspace import WorkspaceManager

PASSWORD = "correct horse battery staple"


def _settings(tmp_path, **over) -> WebSettings:
    base = dict(
        data_dir=str(tmp_path), secret_key="x" * 40, auth_mode="local",
        supabase_url="", supabase_anon_key="", local_user="moi",
        local_password_hash=bcrypt.hashpw(PASSWORD.encode(), bcrypt.gensalt(4)).decode(),
        cookie_secure=False, session_max_age=3600, sync_delay=1, idle_timeout=3600,
    )
    base.update(over)
    return WebSettings(**base)


@pytest.fixture
def client(tmp_path):
    s = _settings(tmp_path)
    app = create_app(s, WorkspaceManager(s.users_dir, s.sync_delay, s.idle_timeout))
    with TestClient(app) as c:
        yield c


def _csrf(html: str) -> str:
    return re.search(r'name="csrf" value="([^"]+)"', html).group(1)


def _login(client, password=PASSWORD):
    tok = _csrf(client.get("/connexion").text)
    return client.post("/connexion", data={"identifier": "moi", "password": password,
                                           "csrf": tok}, follow_redirects=False)


def test_health(client):
    assert client.get("/healthz").json()["status"] == "ok"
    assert client.get("/readyz").status_code == 200


def test_requires_login(client):
    r = client.get("/", follow_redirects=False)
    assert r.status_code == 303 and r.headers["location"] == "/connexion"
    assert client.get("/depenses", follow_redirects=False).status_code == 303


def test_security_headers(client):
    r = client.get("/connexion")
    assert "frame-ancestors 'none'" in r.headers["content-security-policy"]
    assert r.headers["x-frame-options"] == "DENY"
    assert r.headers["cache-control"] == "no-store"


def test_bad_password_and_rate_limit(client):
    for _ in range(5):
        assert _login(client, "nope").status_code == 401
    assert _login(client).status_code == 429   # bloqué même avec le bon mot de passe


def test_login_without_csrf_rejected(client):
    r = client.post("/connexion", data={"identifier": "moi", "password": PASSWORD})
    assert r.status_code == 400


def test_expense_crud_flow(client):
    assert _login(client).status_code == 303
    page = client.get("/depenses?y=2026&m=3")
    assert page.status_code == 200
    tok = _csrf(page.text)
    cat_id = re.search(r'<option value="(\d+)"', page.text).group(1)

    r = client.post("/depenses", data={"y": 2026, "m": 3, "amount": "1 234,50",
                                       "label": "Vélo", "payee": "decathlon",
                                       "category_id": cat_id, "csrf": tok},
                    follow_redirects=False)
    assert r.status_code == 303 and r.headers["location"] == "/depenses?y=2026&m=3"
    page = client.get("/depenses?y=2026&m=3").text
    assert "Vélo" in page and "DECATHLON" in page and "1 234,50" in page

    exp_id = re.search(r"/depenses/(\d+)/modifier", page).group(1)
    r = client.post(f"/depenses/{exp_id}/modifier",
                    data={"amount": "99", "label": "Vélo d'occasion", "payee": "",
                          "category_id": cat_id, "csrf": tok}, follow_redirects=False)
    assert r.status_code == 303
    page = client.get("/depenses?y=2026&m=3").text
    assert "99,00" in page and "Vélo d&#39;occasion" in page

    dash = client.get("/?y=2026&m=3").text
    assert "99,00" in dash

    r = client.post(f"/depenses/{exp_id}/supprimer", data={"csrf": tok},
                    follow_redirects=False)
    assert r.status_code == 303
    assert "Rien de saisi" in client.get("/depenses?y=2026&m=3").text


def test_invalid_amount_and_csrf_are_rejected(client):
    _login(client)
    page = client.get("/revenus?y=2026&m=3").text
    tok = _csrf(page)
    client.post("/revenus", data={"y": 2026, "m": 3, "amount": "-3", "source": "X",
                                  "csrf": tok})
    client.post("/revenus", data={"y": 2026, "m": 3, "amount": "10", "source": "X",
                                  "csrf": "forged"})
    assert "Rien de saisi" in client.get("/revenus?y=2026&m=3").text


def test_closed_month_is_read_only(client):
    _login(client)
    ws = client.app.state.manager.get("local")
    ws.db.add_revenue(2026, 1, "Salaire", 2000)
    ws.db.close_month(2026, 1)
    page = client.get("/revenus?y=2026&m=1").text
    assert "Clôturé" in page and "Supprimer" not in page
    rev_id = ws.db.get_revenues(2026, 1)[0]["id"]
    client.post(f"/revenus/{rev_id}/supprimer", data={"csrf": _csrf(page)})
    assert len(ws.db.get_revenues(2026, 1)) == 1


def test_savings_and_patrimoine_pages(client):
    _login(client)
    tok = _csrf(client.get("/epargne?y=2026&m=2").text)
    client.post("/epargne", data={"y": 2026, "m": 2, "amount": "150", "account": "Livret A",
                                  "label": "", "csrf": tok})
    assert "Livret A" in client.get("/epargne?y=2026&m=2").text
    assert client.get("/patrimoine").status_code == 200


def test_logout(client):
    _login(client)
    tok = _csrf(client.get("/").text)
    r = client.post("/deconnexion", data={"csrf": tok}, follow_redirects=False)
    assert r.status_code == 303
    assert client.get("/", follow_redirects=False).status_code == 303
    assert client.app.state.manager.count() == 0


def test_settings_validation(tmp_path):
    with pytest.raises(ConfigError):
        _settings(tmp_path, secret_key="short").validate()
    with pytest.raises(ConfigError):
        _settings(tmp_path, auth_mode="supabase").validate()
    with pytest.raises(ConfigError):
        _settings(tmp_path, local_password_hash="plaintext").validate()


def test_sign_out_only_revokes_this_device():
    import cloud_auth

    class _Auth:
        def sign_out(self, options=None):
            self.options = options

    class _Client:
        auth = _Auth()

    c = _Client()
    cloud_auth.sign_out(c)
    assert c.auth.options == {"scope": "local"}


def test_healthcheck_module(monkeypatch):
    from web import healthcheck

    class _Resp:
        status = 200
        def __enter__(self): return self
        def __exit__(self, *a): return False

    monkeypatch.setattr("sys.argv", ["healthcheck", "/readyz"])
    seen = {}
    monkeypatch.setattr(healthcheck.urllib.request, "urlopen",
                        lambda url, timeout: seen.setdefault("url", url) and _Resp())
    assert healthcheck.main() == 0 and seen["url"].endswith("/readyz")

    def _down(url, timeout):
        raise OSError("connection refused")
    monkeypatch.setattr(healthcheck.urllib.request, "urlopen", _down)
    assert healthcheck.main() == 1
