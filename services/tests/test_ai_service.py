import httpx
import pytest
from fastapi.testclient import TestClient

from ai_service.app.main import create_app
from ai_service.app.providers import ProviderConfig, ProviderError, Providers
from conftest import make_token
from fintrack_common.ratelimit import Counter

CATS = [{"id": 1, "name": "ALIMENTATION"}, {"id": 4, "name": "RESTAURANTS"}]


class FakeProviders(Providers):
    def __init__(self, choice="RESTAURANTS", fail=False):
        super().__init__(ProviderConfig("k", "", "claude-opus-5-5", "gemini-x"))
        self.calls = []
        self.choice = choice
        self.fail = fail

    def complete(self, provider, system, messages, *, effort="medium", max_tokens=4000):
        if self.fail:
            raise ProviderError("Claude est indisponible pour le moment.")
        self.calls.append((provider, messages))
        return "- **Bien** : épargne régulière"

    def choose(self, provider, system, prompt, choices):
        self.calls.append((provider, prompt))
        if self.choice not in choices:
            raise ProviderError("Catégorie non reconnue.")
        return self.choice


def finance_handler(request: httpx.Request):
    assert request.headers["authorization"].startswith("Bearer ")
    if request.url.path == "/v1/ai-context":
        return httpx.Response(200, json={"per_month": [], "top_expenses": [{"name": "Loyer"}]})
    if request.url.path == "/v1/categories":
        return httpx.Response(200, json=CATS)
    return httpx.Response(404)


@pytest.fixture
def make(verifier, monkeypatch):
    monkeypatch.setenv("AI_DAILY_LIMIT", "3")

    def _make(**kw):
        prov = kw.pop("providers", FakeProviders())
        app = create_app(verifier=verifier, providers=prov, counter=Counter(),
                         finance_http=httpx.Client(base_url="http://finance",
                                                   transport=httpx.MockTransport(finance_handler)))
        return TestClient(app), prov
    return _make


H = {"Authorization": f"Bearer {make_token('u1')}"}


def test_insights_uses_aggregated_context(make):
    c, prov = make()
    r = c.post("/v1/insights", headers=H, json={"year": 2026, "month": 3, "provider": "claude"})
    assert r.status_code == 200 and "épargne" in r.json()["text"]
    assert "Loyer" in prov.calls[0][1][0]["content"]


def test_chat_requires_last_user_message(make):
    c, _ = make()
    r = c.post("/v1/chat", headers=H, json={"year": 2026, "month": 3, "messages": [
        {"role": "assistant", "content": "x"}]})
    assert r.status_code == 422


def test_chat_ok(make):
    c, prov = make()
    r = c.post("/v1/chat", headers=H, json={"year": 2026, "month": 3, "provider": "gemini",
                                            "messages": [{"role": "user", "content": "Restos ?"}]})
    assert r.status_code == 200
    roles = [m["role"] for m in prov.calls[0][1]]
    assert roles == ["user", "assistant", "user"]       # alternance respectée


def test_categorize_returns_known_category(make):
    c, _ = make()
    r = c.post("/v1/categorize", headers=H, json={"label": "Pizza", "payee": "DOMINOS"})
    assert r.json() == {"category_id": 4, "category": "RESTAURANTS", "provider": "claude"}


def test_categorize_rejects_hallucinated_category(make):
    c, _ = make(providers=FakeProviders(choice="VOYAGES"))
    r = c.post("/v1/categorize", headers=H, json={"label": "Avion"})
    assert r.status_code == 502


def test_daily_quota(make):
    c, _ = make()
    for _ in range(3):
        assert c.post("/v1/categorize", headers=H, json={"label": "x"}).status_code == 200
    assert c.post("/v1/categorize", headers=H, json={"label": "x"}).status_code == 429
    assert c.get("/v1/providers", headers=H).json()["remaining"] == 0


def test_provider_error_is_clean(make):
    c, _ = make(providers=FakeProviders(fail=True))
    r = c.post("/v1/insights", headers=H, json={"year": 2026, "month": 3})
    assert r.status_code == 502 and r.json()["detail"] == "Claude est indisponible pour le moment."


def test_unknown_provider_and_auth(make):
    c, _ = make()
    assert c.post("/v1/insights", json={"year": 2026, "month": 3}).status_code == 401
    assert c.post("/v1/insights", headers=H, json={"year": 2026, "month": 3,
                                                   "provider": "openai"}).status_code == 422


def test_claude_request_shape():
    """Vérifie la requête réellement construite pour l'API Claude (SDK
    Anthropic branché sur un transport factice : aucun appel réseau)."""
    import anthropic
    import httpx2
    seen = {}
    prov = Providers(ProviderConfig("sk-test", "", "claude-opus-5-5", "g"))
    prov._anthropic = anthropic.Anthropic(
        api_key="sk-test", max_retries=0, http_client=anthropic.DefaultHttpxClient(
            transport=httpx2.MockTransport(
                lambda req: httpx2.Response(200, json=_respond(req, seen)))))
    assert prov.choose("claude", "sys", "prompt", ["ALIMENTATION", "RESTAURANTS"]) == "RESTAURANTS"
    body = seen["body"]
    assert body["model"] == "claude-opus-5-5"
    assert body["fallbacks"] == "default" and "server-side-fallback-2026-07-01" in seen["beta"]
    assert body["output_config"]["format"]["schema"]["properties"]["category"]["enum"] == [
        "ALIMENTATION", "RESTAURANTS"]
    assert "temperature" not in body and "thinking" not in body
    assert body["system"][0]["cache_control"] == {"type": "ephemeral"}


def _respond(req, seen):
    import json
    seen["body"] = json.loads(req.content)
    seen["beta"] = req.headers.get("anthropic-beta", "")
    return {"id": "msg_1", "type": "message", "role": "assistant", "model": "claude-opus-5-5",
            "content": [{"type": "text", "text": '{"category": "RESTAURANTS"}'}],
            "stop_reason": "end_turn", "stop_sequence": None,
            "usage": {"input_tokens": 10, "output_tokens": 5}}


def test_long_assistant_history_accepted(make):
    c, _ = make()
    r = c.post("/v1/chat", headers=H, json={"year": 2026, "month": 3, "messages": [
        {"role": "user", "content": "Bilan ?"}, {"role": "assistant", "content": "x" * 6000},
        {"role": "user", "content": "Et ensuite ?"}]})
    assert r.status_code == 200


def test_failed_calls_do_not_consume_quota(make):
    c, _ = make(providers=FakeProviders(fail=True))
    for _ in range(5):
        assert c.post("/v1/insights", headers=H, json={"year": 2026, "month": 3}).status_code == 502
    assert c.get("/v1/providers", headers=H).json()["remaining"] == 3
