"""Page de consentement OAuth (clients MCP) servie par web : connexion
préalable avec retour sur la page, CSRF, liste d'hôtes de retour, revérification
côté serveur et retour vers le client sans redirection de formulaire."""
import json
import re

import httpx
import pytest
from fastapi.testclient import TestClient

from conftest import make_token
from fintrack_common.ratelimit import Counter
from web.app.backends import Backends, SupabaseAuth
from web.app.main import create_app as create_web
from web.app.main import oauth_redirect_allowed, safe_next
from web.app.session import SessionStore

PASSWORD = "bon-mot-de-passe"
AID = "a1b2c3d4-0000-4000-8000-000000000000"
CLAUDE_CODE_CB = "http://localhost:53682/callback"


@pytest.fixture
def oauth(user_id, monkeypatch):
    monkeypatch.setenv("SESSION_ENCRYPTION_KEY", "unused")
    monkeypatch.setenv("FINTRACK_COOKIE_SECURE", "0")
    st = {"redirect_uri": CLAUDE_CODE_CB, "already": False, "consents": [], "status": 200,
          "auth_headers": []}

    def gotrue(request: httpx.Request):
        body = json.loads(request.content or b"{}")
        if "grant_type=password" in str(request.url):
            if body.get("password") != PASSWORD:
                return httpx.Response(400, json={"error": "invalid_grant"})
            return httpx.Response(200, json={
                "access_token": make_token(user_id), "refresh_token": "r", "expires_in": 3600,
                "user": {"id": user_id, "email": "u@example.com"}})
        path = request.url.path
        if path.startswith("/auth/v1/oauth/authorizations/"):
            st["auth_headers"].append(request.headers.get("authorization", ""))
            if st["status"] != 200:
                return httpx.Response(st["status"], json={"msg": "nope"})
            if path.endswith("/consent"):
                st["consents"].append(body["action"])
                if body["action"] == "approve":
                    return httpx.Response(200, json={
                        "redirect_url": f"{st['redirect_uri']}?code=XYZ&state=s1"})
                return httpx.Response(200, json={
                    "redirect_url": f"{st['redirect_uri']}?error=access_denied&state=s1"})
            if st["already"]:
                return httpx.Response(200, json={"redirect_url": f"{st['redirect_uri']}?code=OLD"})
            return httpx.Response(200, json={
                "authorization_id": AID, "redirect_uri": st["redirect_uri"],
                "client": {"id": "c1", "name": "Claude Code", "uri": "", "logo_uri": ""},
                "user": {"id": user_id, "email": "u@example.com"}, "scope": "openid email"})
        return httpx.Response(404)

    backends = Backends(SupabaseAuth(httpx.Client(base_url="https://proj.supabase.co",
                                                  transport=httpx.MockTransport(gotrue)), "anon"),
                        httpx.Client(base_url="http://finance"), None, None)
    from cryptography.fernet import Fernet
    web = create_web(backends=backends, sessions=SessionStore(Fernet.generate_key().decode()),
                     counter=Counter())
    return TestClient(web), st


def csrf(html):
    return re.search(r'name="csrf" value="([^"]+)"', html).group(1)


def consent_url(aid=AID):
    return f"/oauth/consent?authorization_id={aid}"


def login_then_consent(c):
    r = c.get(consent_url(), follow_redirects=False)
    assert r.status_code == 303
    assert r.headers["location"] == "/connexion?next=%2Foauth%2Fconsent%3Fauthorization_id%3D" + AID
    page = c.get(r.headers["location"]).text
    assert 'name="next" value="/oauth/consent?authorization_id=' + AID in page
    r = c.post("/connexion", data={"identifier": "u@example.com", "password": PASSWORD,
                                   "csrf": csrf(page), "next": "/oauth/consent?authorization_id=" + AID},
               follow_redirects=False)
    assert r.status_code == 303 and r.headers["location"] == consent_url()
    return c.get(consent_url())


def test_login_then_approve_returns_code_to_client(oauth):
    c, st = oauth
    page = login_then_consent(c)
    assert page.status_code == 200
    assert "Claude Code" in page.text and "lecture seule" in page.text
    assert 'value="approve"' in page.text
    r = c.post("/oauth/consent", data={"authorization_id": AID, "action": "approve",
                                       "csrf": csrf(page.text)}, follow_redirects=False)
    assert r.status_code == 200                       # page de retour, pas un 303 externe
    assert 'http-equiv="refresh"' in r.text and "code=XYZ" in r.text
    assert st["consents"] == ["approve"]
    assert all(h.startswith("Bearer ey") for h in st["auth_headers"])   # jeton de l'utilisateur


def test_deny(oauth):
    c, st = oauth
    page = login_then_consent(c)
    r = c.post("/oauth/consent", data={"authorization_id": AID, "action": "deny",
                                       "csrf": csrf(page.text)})
    assert st["consents"] == ["deny"] and "error=access_denied" in r.text


def test_csrf_required(oauth):
    c, st = oauth
    login_then_consent(c)
    r = c.post("/oauth/consent", data={"authorization_id": AID, "action": "approve", "csrf": "x"},
               follow_redirects=False)
    assert r.status_code == 303 and st["consents"] == []


def test_untrusted_redirect_cannot_be_approved(oauth):
    c, st = oauth
    st["redirect_uri"] = "https://evil.example/cb"
    page = login_then_consent(c)
    assert 'value="approve"' not in page.text and "non autorisée" in page.text
    # Même en forgeant le formulaire : revérifié côté serveur
    c.post("/oauth/consent", data={"authorization_id": AID, "action": "approve",
                                   "csrf": csrf(page.text)})
    assert st["consents"] == []


def test_already_consented_goes_straight_back(oauth):
    c, st = oauth
    st["already"] = True
    page = login_then_consent(c)
    assert "code=OLD" in page.text and 'http-equiv="refresh"' in page.text


def test_expired_request_shows_error(oauth):
    c, st = oauth
    login_then_consent(c)
    st["status"] = 404
    r = c.get(consent_url())
    assert r.status_code == 400 and "invalide ou expirée" in r.text


@pytest.mark.parametrize("aid", ["../../admin", "x" * 200, "a b"])
def test_authorization_id_is_validated(oauth, aid):
    c, st = oauth
    c.get(consent_url(aid), follow_redirects=False)
    assert st["auth_headers"] == []


@pytest.mark.parametrize("url,ok", [
    ("http://localhost:1234/callback", True),
    ("http://127.0.0.1/cb", True),
    ("https://claude.ai/api/mcp/auth_callback", True),
    ("https://evil.example/cb", False),
    ("https://claude.ai.evil.example/cb", False),
    ("http://claude.ai/cb", False),                    # http hors boucle locale
    ("javascript:alert(1)", False),
    ("https://user:pw@claude.ai/cb", False),
    ("", False),
])
def test_redirect_allowlist(url, ok):
    assert oauth_redirect_allowed(url, ("claude.ai", "claude.com")) is ok


@pytest.mark.parametrize("raw,expected", [
    ("/oauth/consent?authorization_id=1", "/oauth/consent?authorization_id=1"),
    ("//evil.example", "/"), ("/\\evil.example", "/"), ("https://evil.example", "/"), (None, "/"),
    ("/x\r\nSet-Cookie: a=b", "/"), ("/x\x7f", "/"), ("/" + "a" * 3000, "/"),
    ("/depenses?y=2026&m=11", "/depenses?y=2026&m=11"),
])
def test_safe_next(raw, expected):
    assert safe_next(raw) == expected


def test_expired_session_keeps_consent_page_as_next(oauth):
    """Revue v2.3 : session Supabase révoquée pendant le consentement → la
    reconnexion doit ramener sur la page de consentement (le client MCP
    attend son retour), pas sur l'accueil."""
    c, st = oauth
    login_then_consent(c)
    st["status"] = 401                       # jeton refusé par Supabase Auth
    r = c.get(consent_url(), follow_redirects=False)
    assert r.status_code == 303
    assert r.headers["location"] == ("/connexion?next=%2Foauth%2Fconsent%3Fauthorization_id%3D" + AID)
