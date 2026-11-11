"""Serveur MCP : découverte OAuth (RFC 9728), contrôle des jetons, outils en
lecture seule branchés sur finance-api avec le jeton de l'utilisateur."""
import json

import httpx
import pytest
from fastapi.testclient import TestClient

from conftest import make_token

PUBLIC = "https://fin.example.com/mcp"
ACCEPT = {"Accept": "application/json, text/event-stream",
          "Content-Type": "application/json", "Host": "fin.example.com"}


class FakeFinance:
    """finance-api simulée : enregistre chaque appel (chemin, paramètres, jeton)."""

    def __init__(self):
        self.calls: list[tuple[str, dict, str]] = []

    def handler(self, request: httpx.Request) -> httpx.Response:
        assert request.method == "GET", "le serveur MCP ne doit jamais écrire"
        self.calls.append((request.url.path, dict(request.url.params),
                           request.headers.get("authorization", "")))
        p = request.url.path
        if p == "/v1/last-month":
            return httpx.Response(200, json={"year": 2026, "month": 10})
        if p == "/v1/months/2026/10/summary":
            return httpx.Response(200, json={"year": 2026, "month": 10, "revenues": 3000.0,
                                             "expenses": 1800.0, "savings": 500.0, "balance": 700.0,
                                             "by_category": [], "budgets": [], "closed": False})
        if p == "/v1/months/2026/10/entries":
            return httpx.Response(200, json={"closed": False, "revenues": [], "savings": [],
                                             "expenses": [{"id": 1, "user_id": "secret-uid",
                                                           "amount": 42.5, "category": "AUTRES"}]})
        if p == "/v1/search/expenses":
            return httpx.Response(200, json=[{"id": i, "amount": 10.0} for i in range(5)])
        if p == "/v1/patrimoine":
            return httpx.Response(401, json={"detail": "Jeton invalide ou expiré."})
        if p == "/v1/analytics":
            return httpx.Response(422, json={"detail": [{"msg": "bad"}]})
        return httpx.Response(404, json={"detail": "Introuvable."})


@pytest.fixture
def finance():
    return FakeFinance()


@pytest.fixture
def make(verifier, finance, monkeypatch):
    monkeypatch.setenv("MCP_PUBLIC_URL", PUBLIC)

    def _make(**env):
        for k, v in env.items():
            monkeypatch.setenv(k, v)
        from mcp_server.app.main import create_app
        app = create_app(verifier=verifier, finance_http=httpx.AsyncClient(
            base_url="http://finance", transport=httpx.MockTransport(finance.handler)))
        return TestClient(app, base_url="https://fin.example.com")
    return _make


def oauth_token(uid="u1", client_id="claude-code"):
    return make_token(uid, client_id=client_id)


def rpc(client, method, params=None, *, token=None, rid=1, headers=None):
    h = dict(ACCEPT, **(headers or {}))
    if token:
        h["Authorization"] = f"Bearer {token}"
    return client.post("/mcp", headers=h, json={"jsonrpc": "2.0", "id": rid, "method": method,
                                               "params": params or {}})


def init(client, token):
    r = rpc(client, "initialize", {"protocolVersion": "2025-06-18", "capabilities": {},
                                   "clientInfo": {"name": "test", "version": "1"}}, token=token)
    assert r.status_code == 200, r.text
    return r.json()["result"]


def call(client, token, name, args=None):
    r = rpc(client, "tools/call", {"name": name, "arguments": args or {}}, token=token, rid=2)
    assert r.status_code == 200, r.text
    return r.json()["result"]


def payload(result):
    assert not result.get("isError"), result
    if result.get("structuredContent") is not None:
        sc = result["structuredContent"]
        return sc.get("result", sc) if isinstance(sc, dict) and set(sc) == {"result"} else sc
    return json.loads(result["content"][0]["text"])


# ── Découverte OAuth / authentification ──────────────────────

def test_protected_resource_metadata_points_to_supabase(make):
    with make() as c:
        r = c.get("/.well-known/oauth-protected-resource/mcp")
    assert r.status_code == 200
    meta = r.json()
    assert meta["resource"] == PUBLIC
    assert meta["authorization_servers"] == ["https://proj.supabase.co/auth/v1"]


def test_missing_token_gets_401_with_resource_metadata(make):
    with make() as c:
        r = rpc(c, "tools/list")
    assert r.status_code == 401
    assert "resource_metadata=" in r.headers["www-authenticate"]
    assert "/.well-known/oauth-protected-resource/mcp" in r.headers["www-authenticate"]


@pytest.mark.parametrize("token", [
    make_token("u1"),                                        # session web/desktop : pas de client OAuth
    make_token("u1", client_id="c", exp_in=-120),            # expiré
    make_token("u1", client_id="c", role="anon"),            # rôle anonyme
    make_token("u1", client_id="c", iss="https://evil.example/auth/v1"),
    "pas-un-jwt",
])
def test_invalid_tokens_are_refused(make, token):
    with make() as c:
        assert rpc(c, "tools/list", token=token).status_code == 401


def test_session_token_allowed_when_explicitly_enabled(make):
    with make(MCP_REQUIRE_OAUTH_CLIENT="false") as c:
        init(c, make_token("u1"))


def test_foreign_host_is_rejected(make):
    with make() as c:
        r = rpc(c, "tools/list", token=oauth_token(), headers={"Host": "attacker.example"})
    assert r.status_code == 421


def test_browser_origin_from_other_site_is_rejected(make):
    with make() as c:
        r = rpc(c, "tools/list", token=oauth_token(), headers={"Origin": "https://evil.example"})
    assert r.status_code == 403


# ── Outils ───────────────────────────────────────────────────

def test_all_tools_are_read_only(make):
    with make() as c:
        tok = oauth_token()
        info = init(c, tok)
        assert info["serverInfo"]["name"] == "fintrack"
        tools = rpc(c, "tools/list", token=tok).json()["result"]["tools"]
    names = {t["name"] for t in tools}
    assert {"get_financial_context", "get_month_summary", "search_entries",
            "get_month_entries", "get_net_worth"} <= names
    for t in tools:
        assert t["annotations"]["readOnlyHint"] is True, t["name"]


def test_details_can_be_hidden(make):
    with make(MCP_EXPOSE_DETAILS="false") as c:
        tok = oauth_token()
        names = {t["name"] for t in rpc(c, "tools/list", token=tok).json()["result"]["tools"]}
    assert "get_month_entries" not in names and "search_entries" not in names
    assert "get_month_summary" in names


def test_summary_defaults_to_last_month_and_forwards_user_token(make, finance):
    tok = oauth_token("u42")
    with make() as c:
        data = payload(call(c, tok, "get_month_summary"))
    assert data["balance"] == 700.0
    assert [x[0] for x in finance.calls] == ["/v1/last-month", "/v1/months/2026/10/summary"]
    assert all(x[2] == f"Bearer {tok}" for x in finance.calls)


def test_year_without_month_is_an_error(make):
    with make() as c:
        res = call(c, oauth_token(), "get_month_summary", {"year": 2026})
    assert res["isError"] is True
    assert "ET le mois" in res["content"][0]["text"]


def test_out_of_range_month_is_rejected(make, finance):
    with make() as c:
        res = call(c, oauth_token(), "get_month_summary", {"year": 2026, "month": 13})
    assert res["isError"] is True
    assert finance.calls == []


def test_entries_strip_user_id_and_filter_kind(make):
    with make() as c:
        data = payload(call(c, oauth_token(), "get_month_entries",
                            {"year": 2026, "month": 10, "kind": "expenses"}))
    assert "revenues" not in data
    assert data["expenses"][0]["amount"] == 42.5
    assert "user_id" not in json.dumps(data)


def test_search_is_limited_and_passes_filters(make, finance):
    with make() as c:
        data = payload(call(c, oauth_token(), "search_entries",
                            {"query": "carrefour", "min_amount": 5, "limit": 2}))
    assert data["returned"] == 2 and data["truncated"] is True and len(data["results"]) == 2
    assert "incomplète" in data["note"]
    path, params, _ = finance.calls[-1]
    assert path == "/v1/search/expenses"
    assert params["q"] == "carrefour" and params["min_amount"] == "5.0"
    assert params["limit"] == "3"                      # limit + 1 : détection de la troncature
    assert "max_amount" not in params


def test_backend_errors_become_tool_errors(make):
    with make() as c:
        tok = oauth_token()
        expired = call(c, tok, "get_net_worth")
        invalid = call(c, tok, "get_analytics", {"year": 2026, "month": 10})
    assert expired["isError"] and "reconnectez" in expired["content"][0]["text"]
    # Détail de validation pydantic (liste) jamais relayé tel quel au modèle
    assert invalid["isError"] and invalid["content"][0]["text"].endswith(": Données indisponibles.")


def test_health_routes_need_no_token(make):
    with make() as c:
        assert c.get("/healthz").json()["status"] == "ok"
        assert c.get("/readyz").status_code == 200


def test_public_url_must_be_https(make, monkeypatch):
    from fintrack_common.config import ConfigError
    with pytest.raises(ConfigError):
        make(MCP_PUBLIC_URL="http://fin.example.com/mcp")
    with pytest.raises(ConfigError):
        make(MCP_PUBLIC_URL="https://fin.example.com/")


def test_jwks_outage_is_503_not_401(make, verifier, monkeypatch):
    """Revue v2.3 : une panne JWKS ne doit pas ressembler à un jeton invalide
    (un 401 ferait relancer tout le parcours OAuth par chaque client)."""
    from fastapi import HTTPException

    def down(token):
        raise HTTPException(503, "Vérification d'identité momentanément indisponible.")
    monkeypatch.setattr(verifier, "verify", down)
    with make() as c:
        r = rpc(c, "tools/list", token=oauth_token())
    assert r.status_code == 503 and r.headers["retry-after"] == "5"
    assert "www-authenticate" not in r.headers



def test_insecure_http_only_with_explicit_opt_in(make, monkeypatch):
    """Cluster local sans TLS (ex. http://fintrack.localtest.me:9080/mcp) :
    refusé par défaut, accepté avec MCP_ALLOW_INSECURE_HTTP=true."""
    from fintrack_common.config import ConfigError
    url = "http://fintrack.localtest.me:9080/mcp"
    with pytest.raises(ConfigError):
        make(MCP_PUBLIC_URL=url)
    with make(MCP_PUBLIC_URL=url, MCP_ALLOW_INSECURE_HTTP="true",
              MCP_EXTRA_ALLOWED_HOSTS="fin.example.com") as c:
        meta = c.get("/.well-known/oauth-protected-resource/mcp").json()
    assert meta["resource"] == url
