"""Tests de bout en bout : navigateur -> web (BFF) -> finance-api -> faux
PostgREST. Seul Supabase Auth (GoTrue) est simulé."""
import json
import re

import httpx
import pytest
from fastapi.testclient import TestClient

from conftest import make_token
from finance_api.app.main import create_app as create_finance
from fintrack_common.ratelimit import Counter
from web.app.backends import Backends, SupabaseAuth
from web.app.main import create_app as create_web
from web.app.session import SessionStore

PASSWORD = "bon-mot-de-passe"


@pytest.fixture
def setup(seeded, user_id, verifier, monkeypatch):
    monkeypatch.setenv("SESSION_ENCRYPTION_KEY", "unused")
    monkeypatch.setenv("FINTRACK_COOKIE_SECURE", "0")
    state = {"refresh_calls": 0, "logout": 0}

    def gotrue(request: httpx.Request):
        body = json.loads(request.content or b"{}")
        if "grant_type=password" in str(request.url):
            if body.get("password") != PASSWORD:
                return httpx.Response(400, json={"error": "invalid_grant"})
            return httpx.Response(200, json=_session(user_id, body["email"]))
        if "grant_type=refresh_token" in str(request.url):
            state["refresh_calls"] += 1
            return httpx.Response(200, json=_session(user_id, "u@example.com"))
        if request.url.path.endswith("/logout"):
            assert request.url.params["scope"] == "local"
            state["logout"] += 1
            return httpx.Response(204)
        return httpx.Response(404)

    finance = TestClient(create_finance(verifier=verifier, supabase_http=seeded.client()),
                         base_url="http://finance")
    backends = Backends(
        SupabaseAuth(httpx.Client(base_url="https://proj.supabase.co",
                                  transport=httpx.MockTransport(gotrue)), "anon"),
        finance, None, None)
    from cryptography.fernet import Fernet
    sessions = SessionStore(Fernet.generate_key().decode())
    web = create_web(backends=backends, sessions=sessions, counter=Counter())
    return TestClient(web), state, sessions


def _session(uid, email, expires_in=3600):
    return {"access_token": make_token(uid, email), "refresh_token": "r-" + uid,
            "expires_in": expires_in, "user": {"id": uid, "email": email}}


def csrf(html):
    return re.search(r'name="csrf" value="([^"]+)"', html).group(1)


def login(c, password=PASSWORD, email="u@example.com"):
    tok = csrf(c.get("/connexion").text)
    return c.post("/connexion", data={"identifier": email, "password": password, "csrf": tok},
                  follow_redirects=False)


def test_redirects_to_login(setup):
    c, *_ = setup
    r = c.get("/", follow_redirects=False)
    assert r.status_code == 303 and r.headers["location"] == "/connexion"


def test_security_headers_and_cookie_flags(setup):
    c, *_ = setup
    r = c.get("/connexion")
    assert "frame-ancestors 'none'" in r.headers["content-security-policy"]
    assert "script-src 'self'" in r.headers["content-security-policy"]
    assert r.headers["cache-control"] == "no-store"
    r = login(c)
    cookie = r.headers["set-cookie"].lower()
    assert "httponly" in cookie and "samesite=lax" in cookie
    assert "eyj" not in cookie                    # aucun jeton dans le cookie


def test_full_expense_flow(setup):
    c, *_ = setup
    assert login(c).status_code == 303
    page = c.get("/depenses?y=2026&m=11")
    assert page.status_code == 200
    tok = csrf(page.text)
    r = c.post("/depenses", data={"y": 2026, "m": 11, "amount": "1 234,50", "label": "Vélo",
                                  "payee": "decathlon", "category_id": "1", "csrf": tok},
               follow_redirects=False)
    assert r.status_code == 303 and r.headers["location"] == "/depenses?y=2026&m=11"
    page = c.get("/depenses?y=2026&m=11").text
    assert "Vélo" in page and "DECATHLON" in page and "1 234,50" in page
    eid = re.search(r"/depenses/(\d+)/modifier", page).group(1)
    edit = c.get(f"/depenses/{eid}/modifier")
    assert edit.status_code == 200 and "1234,50" in edit.text
    c.post(f"/depenses/{eid}/modifier", data={"amount": "99", "label": "Vélo d'occasion",
                                              "payee": "", "category_id": "1", "csrf": tok})
    assert "99,00" in c.get("/?y=2026&m=11").text
    c.post(f"/depenses/{eid}/supprimer", data={"csrf": tok})
    assert "Rien de saisi" in c.get("/depenses?y=2026&m=11").text


@pytest.mark.parametrize("amount", ["nan", "-3", "abc", "0"])
def test_invalid_amount_flashes_error(setup, amount):
    c, *_ = setup
    login(c)
    tok = csrf(c.get("/revenus?y=2026&m=3").text)
    r = c.post("/revenus", data={"y": 2026, "m": 3, "amount": amount, "source": "X", "csrf": tok},
               headers={"referer": "http://testserver/revenus?y=2026&m=3"})
    assert "Données invalides" in r.text
    assert "Rien de saisi" in r.text


def test_invalid_month_is_rejected_not_substituted(setup):
    c, *_ = setup
    login(c)
    tok = csrf(c.get("/depenses?y=2026&m=3").text)
    r = c.post("/depenses", data={"y": 2026, "m": 13, "amount": "5", "category_id": "1",
                                  "csrf": tok})
    assert "Mois invalide" in r.text


def test_forged_csrf_rejected(setup):
    c, *_ = setup
    login(c)
    r = c.post("/revenus", data={"y": 2026, "m": 3, "amount": "10", "source": "X",
                                 "csrf": "forged"})
    assert "Formulaire expiré" in r.text


def test_logout_revokes_server_side_session(setup):
    c, state, sessions = setup
    login(c)
    sid = c.cookies.get("fintrack_sid")
    tok = csrf(c.get("/").text)
    c.post("/deconnexion", data={"csrf": tok}, follow_redirects=False)
    assert sessions.get(sid) is None and state["logout"] == 1
    # un cookie copié avant la déconnexion ne donne plus accès
    c.cookies.set("fintrack_sid", sid)
    assert c.get("/", follow_redirects=False).headers["location"] == "/connexion"


def test_login_rate_limit_is_per_ip_and_account(setup):
    c, *_ = setup
    for _ in range(5):
        assert login(c, "faux").status_code == 401
    assert login(c).status_code == 429                         # ce compte depuis cette IP
    assert login(c, email="autre@example.com").status_code == 303   # pas de blocage global


def test_non_ascii_csrf_does_not_crash(setup):
    c, *_ = setup
    c.get("/connexion")
    r = c.post("/connexion", data={"identifier": "élodie@x.fr", "password": "x", "csrf": "é"})
    assert r.status_code == 400


def test_token_refreshed_before_expiry(setup, user_id):
    c, state, sessions = setup
    login(c)
    sid = c.cookies.get("fintrack_sid")
    sessions.update(sid, expires_at=0)         # jeton sur le point d'expirer
    assert c.get("/?y=2026&m=1").status_code == 200
    assert state["refresh_calls"] == 1


def test_budgets_page_and_set(setup):
    c, *_ = setup
    login(c)
    page = c.get("/budgets?y=2026&m=5")
    tok = csrf(page.text)
    c.post("/budgets", data={"y": 2026, "m": 5, "category": "RESTAURANTS", "amount": "150",
                             "csrf": tok})
    page = c.get("/budgets?y=2026&m=5").text
    assert "RESTAURANTS" in page and "150,00" in page


def test_ai_and_settings_degrade_gracefully_when_services_absent(setup):
    c, *_ = setup
    login(c)
    assert "Aucun fournisseur IA" in c.get("/ia").text
    assert "pas déployé" in c.get("/parametres").text


def test_ai_text_rendering_escapes_html():
    from web.app.main import render_ai_text
    out = str(render_ai_text('<script>alert(1)</script>\n- **gras** <img src=x onerror=alert(1)>'))
    assert "<script>" not in out and "<img" not in out
    assert "&lt;script&gt;" in out and "<li><strong>gras</strong>" in out


def test_session_update_merges_concurrent_changes():
    """Une requête longue ne doit pas écraser un jeton rafraîchi entre-temps."""
    from cryptography.fernet import Fernet
    st = SessionStore(Fernet.generate_key().decode())
    sid = st.create({"access_token": "a1", "refresh_token": "r1", "expires_at": 0})
    stale = st.get(sid)                                   # copie lue par la requête A
    st.update(sid, refresh_token="r2", access_token="a2")  # requête B : rotation du jeton
    st.update(sid, chat=["…"])                            # requête A termine
    cur = st.get(sid)
    assert cur["refresh_token"] == "r2" and cur["chat"] == ["…"] and stale["refresh_token"] == "r1"


def test_backend_403_is_not_a_logout(setup):
    c, _, sessions = setup
    login(c)
    sid = c.cookies.get("fintrack_sid")
    from web.app.backends import BackendError
    def deny(*a, **k):
        raise BackendError(403, "Opération refusée par la base de données.")
    c.app.state.backends.call = deny
    r = c.get("/depenses?y=2026&m=1", headers={"referer": "http://testserver/"})
    assert sessions.get(sid) is not None                   # toujours connecté
    assert r.status_code == 403 and "Opération refusée" in r.text
