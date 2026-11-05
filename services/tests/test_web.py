"""Tests de bout en bout : navigateur -> web (BFF) -> finance-api -> faux
PostgREST. Seul Supabase Auth (GoTrue) est simulé."""
import json
import re

import httpx
import pytest
from fastapi.testclient import TestClient

from conftest import make_token
from finance_api.app.main import create_app as create_finance
from fintrack_common.http import service_client
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


@pytest.mark.parametrize("referer", ["https://evil.example/x", "http://testserver//evil.example/x"])
def test_no_open_redirect_via_referer(setup, referer):
    c, *_ = setup
    login(c)
    r = c.post("/revenus", data={"y": 2026, "m": 3, "amount": "10", "source": "X", "csrf": "forged"},
               headers={"referer": referer}, follow_redirects=False)
    assert r.status_code == 303 and r.headers["location"].startswith("/")
    assert not r.headers["location"].startswith("//")


# ── TickTick : pas de redirection externe après un POST (CSP form-action) ──
AUTH_URL = ("https://ticktick.com/oauth/authorize?client_id=cid&scope=tasks%3Awrite+tasks%3Aread"
            "&state=st&redirect_uri=http%3A%2F%2Ffintrack.localtest.me%3A9080%2Fcb&response_type=code")


@pytest.fixture
def tt(setup):
    """web + faux notifier qui renvoie l'URL d'autorisation choisie par le test."""
    c, state, sessions = setup
    calls = {"authorize": 0, "url": AUTH_URL}

    def notifier(request: httpx.Request):
        if request.url.path == "/v1/ticktick/authorize":
            calls["authorize"] += 1
            return httpx.Response(200, json={"url": calls["url"]})
        return httpx.Response(404)

    c.app.state.backends.clients["notifier"] = httpx.Client(
        base_url="http://notifier", transport=httpx.MockTransport(notifier))
    login(c)
    return c, calls


def test_ticktick_connect_is_not_an_external_redirect(tt):
    c, calls = tt
    tok = csrf(c.get("/").text)
    r = c.post("/parametres/ticktick/connecter", data={"csrf": tok}, follow_redirects=False)
    assert r.status_code == 200 and "location" not in r.headers      # pas de 3xx
    assert calls["authorize"] == 1
    # meta refresh + lien de secours, URL échappée (& -> &amp;) dans l'attribut
    escaped = AUTH_URL.replace("&", "&amp;")
    assert f'http-equiv="refresh" content="0;url={escaped}"' in r.text
    assert f'href="{escaped}"' in r.text
    # la CSP globale est inchangée, sans script inline
    csp = r.headers["content-security-policy"]
    assert "form-action 'self' https://ticktick.com" in csp and "script-src 'self'" in csp
    assert "<script" not in r.text.split("</head>")[0]


@pytest.mark.parametrize("bad", [
    "https://evil.example/oauth/authorize?x=1",            # autre hôte
    "https://ticktick.com.evil.example/oauth/authorize",    # hôte suffixé
    "http://ticktick.com/oauth/authorize",                  # pas https
    "https://ticktick.com/autre-chemin",                    # autre chemin
    "https://user@ticktick.com/oauth/authorize",            # identifiants dans l'URL
    "javascript:alert(1)",
])
def test_ticktick_connect_rejects_unexpected_url(tt, bad):
    c, calls = tt
    calls["url"] = bad
    tok = csrf(c.get("/").text)
    r = c.post("/parametres/ticktick/connecter", data={"csrf": tok},
               headers={"referer": "http://testserver/parametres"}, follow_redirects=False)
    assert r.status_code == 303 and r.headers["location"] == "/parametres"   # retour local
    page = c.get("/parametres").text                                        # affiche le message
    assert "URL d&#39;autorisation inattendue" in page and bad not in page


def test_ticktick_connect_requires_csrf(tt):
    c, calls = tt
    r = c.post("/parametres/ticktick/connecter", data={"csrf": "forged"},
               headers={"referer": "http://testserver/parametres"}, follow_redirects=False)
    assert r.status_code == 303 and r.headers["location"] == "/parametres"
    assert calls["authorize"] == 0                       # aucun state créé sans CSRF valide


# ── Performance : cache des fichiers statiques, appels parallèles ──

def test_static_assets_are_fingerprinted_and_cached(setup):
    c, *_ = setup
    page = c.get("/connexion").text
    css = re.search(r'href="(/static/app\.css\?v=[0-9a-f]{12})"', page).group(1)
    r = c.get(css)
    assert r.status_code == 200
    assert r.headers["cache-control"] == "public, max-age=31536000, immutable"
    assert "etag" in r.headers
    # sans empreinte : revalidation (ETag) plutôt que cache long
    assert c.get("/static/app.css").headers["cache-control"] == "no-cache"
    # les pages, elles, ne sont jamais mises en cache
    assert c.get("/connexion").headers["cache-control"] == "no-store"


def test_fingerprint_changes_with_content(tmp_path):
    from web.app.main import _static_hashes
    (tmp_path / "a.css").write_text("body{}")
    h1 = _static_hashes(str(tmp_path))["a.css"]
    (tmp_path / "a.css").write_text("body{color:red}")
    assert _static_hashes(str(tmp_path))["a.css"] != h1


def test_dashboard_backend_calls_run_in_parallel(seeded, user_id, verifier, monkeypatch):
    """3 appels de 0,4 s chacun : en série ≥ 1,2 s ; en parallèle ≈ 0,4 s."""
    import threading
    import time as _t

    from cryptography.fernet import Fernet
    monkeypatch.setenv("FINTRACK_COOKIE_SECURE", "0")
    seen_rids, lock = set(), threading.Lock()

    def finance(request: httpx.Request):
        _t.sleep(0.4)
        with lock:
            seen_rids.add(request.headers.get("x-request-id"))
        path = request.url.path
        if path.endswith("/summary"):
            return httpx.Response(200, json={"closed": False, "revenues": 0, "expenses": 0,
                                             "savings": 0, "balance": 0, "by_category": [], "budgets": []})
        if path == "/v1/history":
            return httpx.Response(200, json=[])
        if path == "/v1/patrimoine":
            return httpx.Response(200, json={"net_worth": 0})
        return httpx.Response(404)

    def gotrue(request):
        return httpx.Response(200, json=_session(user_id, "u@example.com"))

    backends = Backends(SupabaseAuth(httpx.Client(base_url="https://proj.supabase.co",
                                                  transport=httpx.MockTransport(gotrue)), "anon"),
                        service_client("http://finance", transport=httpx.MockTransport(finance)),
                        None, None)
    c = TestClient(create_web(backends=backends,
                              sessions=SessionStore(Fernet.generate_key().decode()), counter=Counter()))
    login(c)
    start = _t.perf_counter()
    r = c.get("/?y=2026&m=3", headers={"x-request-id": "rid-test-123456"})
    elapsed = _t.perf_counter() - start
    assert r.status_code == 200
    assert elapsed < 1.0, f"appels en série ? {elapsed:.2f} s"
    assert seen_rids == {"rid-test-123456"}          # request_id propagé dans chaque thread


# ── Thème, récurrentes, recherche, duplication ───────────────

def test_theme_cookie_sets_data_theme(setup):
    c, *_ = setup
    login(c)
    page = c.get("/depenses?y=2026&m=11").text
    assert "data-theme" not in page.split(">", 2)[1]               # auto par défaut
    r = c.post("/theme", data={"theme": "dark", "csrf": csrf(page)}, follow_redirects=False,
               headers={"referer": "http://testserver/depenses?y=2026&m=11"})
    assert r.status_code == 303 and r.headers["location"] == "/depenses?y=2026&m=11"
    assert "fintrack_theme=dark" in r.headers["set-cookie"]
    assert '<html lang="fr" data-theme="dark">' in c.get("/depenses?y=2026&m=11").text
    c.cookies.delete("fintrack_theme")
    c.cookies.set("fintrack_theme", '"><script>')                 # valeur inconnue -> auto
    assert "data-theme" not in c.get("/depenses?y=2026&m=11").text.split(">", 2)[1]
    assert c.post("/theme", data={"theme": "light", "csrf": "forged"}).status_code in (200, 303)
    assert c.cookies.get("fintrack_theme") != "light"


def test_recurring_pages(setup):
    c, *_ = setup
    login(c)
    page = c.get("/recurrentes?y=2026&m=9")
    assert page.status_code == 200 and "Aucune transaction récurrente" in page.text
    tok = csrf(page.text)
    c.post("/recurrentes", data={"y": 2026, "m": 9, "type": "expense", "label": "Netflix",
                                 "amount": "13,49", "category_id": "2", "csrf": tok})
    c.post("/recurrentes", data={"y": 2026, "m": 9, "type": "revenue", "label": "Salaire",
                                 "amount": "2 500", "source": "", "csrf": tok})
    page = c.get("/recurrentes?y=2026&m=9").text
    ids = re.findall(r'name="ids" value="(\d+)"', page)
    assert len(ids) == 2 and "13,49" in page
    # n'applique que la première, avec un montant ajusté
    r = c.post("/recurrentes/appliquer", data={"y": 2026, "m": 9, "sel": [ids[0]], "ids": ids,
                                               "amounts": ["15,99", "2500"], "csrf": tok},
               follow_redirects=False)
    assert r.status_code == 303
    assert "1 transaction(s) récurrente(s) appliquée(s)" in c.get("/recurrentes?y=2026&m=9").text
    entries = c.get("/depenses?y=2026&m=9").text + c.get("/revenus?y=2026&m=9").text
    assert ("15,99" in entries) != ("2 500,00" in entries)          # une seule des deux appliquée
    page = c.get("/recurrentes?y=2026&m=9").text
    assert len(re.findall(r'name="ids"', page)) == 1
    rid = re.search(r"/recurrentes/(\d+)/supprimer", page).group(1)
    c.post(f"/recurrentes/{rid}/activer", data={"y": 2026, "m": 9, "active": "0", "csrf": tok})
    assert "Inactive" in c.get("/recurrentes?y=2026&m=9").text


def test_search_page(setup):
    c, *_ = setup
    login(c)
    tok = csrf(c.get("/depenses?y=2026&m=10").text)
    for m, amount, label in [(10, "12", "Boulangerie"), (11, "64", "Boulangerie fête")]:
        c.post("/depenses", data={"y": 2026, "m": m, "amount": amount, "label": label,
                                  "payee": "", "category_id": "1", "csrf": tok})
    assert "résultat" not in c.get("/recherche").text               # formulaire seul
    page = c.get("/recherche?type=depenses&q=boulang&min=20").text
    assert "1 résultat(s)" in page and "Novembre 2026" in page and "Octobre 2026" not in page
    assert c.get("/recherche?q=x&min=abc").status_code == 400
    assert "<script>" not in c.get("/recherche?q=<script>").text


def test_duplicate_previous_month(setup):
    c, *_ = setup
    login(c)
    tok = csrf(c.get("/depenses?y=2026&m=3").text)
    for amount, label, cat in [("700", "Loyer", "3"), ("45", "Internet", "2"), ("30", "Ciné", "4")]:
        c.post("/depenses", data={"y": 2026, "m": 3, "amount": amount, "label": label,
                                  "payee": "", "category_id": cat, "csrf": tok})
    page = c.get("/depenses/dupliquer?y=2026&m=4").text
    assert "Mars 2026" in page and "Avril 2026" in page
    labels = re.findall(r'name="label" value="([^"]*)"', page)
    cats = re.findall(r'name="cat" value="(\d+)"', page)
    keep = [str(i) for i, lb in enumerate(labels) if lb != "Ciné"]
    amounts = ["710" if lb == "Loyer" else "45" for lb in labels]
    r = c.post("/depenses/dupliquer", data={"y": 2026, "m": 4, "sel": keep, "cat": cats,
                                           "label": labels, "payee": [""] * 3,
                                           "amounts": amounts, "csrf": tok}, follow_redirects=False)
    assert r.status_code == 303 and r.headers["location"] == "/depenses?y=2026&m=4"
    april = c.get("/depenses?y=2026&m=4").text
    assert "2 dépense(s) copiée(s)" in april and "710,00" in april and "Ciné" not in april
    assert "contient déjà 2 dépense(s)" in c.get("/depenses/dupliquer?y=2026&m=4").text
    # un montant invalide : rien n'est écrit (insertion atomique)
    c.post("/depenses/dupliquer", data={"y": 2026, "m": 4, "sel": ["0", "1"], "cat": cats[:2],
                                        "label": labels[:2], "payee": ["", ""],
                                        "amounts": ["10", "-5"], "csrf": tok})
    assert len(re.findall(r"/depenses/\d+/modifier", c.get("/depenses?y=2026&m=4").text)) == 2
