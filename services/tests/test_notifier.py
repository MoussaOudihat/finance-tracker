import datetime as dt

import httpx
import pytest
from cryptography.fernet import Fernet
from fastapi.testclient import TestClient

from conftest import make_token
from notifier.app.channels import ChannelError, Channels, validate_user_url
from notifier.app.main import create_app
from notifier.app.store import Store

HOSTS = ("ntfy.sh", "discord.com", "hooks.slack.com")
INTERNAL = "i" * 40


class Recorder:
    def __init__(self):
        self.calls = []
        self.fail = False          # simule une panne de tous les canaux

    def handler(self, request: httpx.Request):
        self.calls.append(request)
        if self.fail:
            return httpx.Response(503)
        if request.url.host == "ticktick.com" and request.url.path == "/oauth/token":
            return httpx.Response(200, json={"access_token": "tt-token", "token_type": "bearer"})
        if request.url.path == "/open/v1/project":
            return httpx.Response(200, json=[{"id": "p1", "name": "Finances"}])
        return httpx.Response(200, json={})


@pytest.fixture
def env(tmp_path, verifier, monkeypatch):
    monkeypatch.setenv("NOTIFIER_INTERNAL_TOKEN", INTERNAL)
    rec = Recorder()
    store = Store(str(tmp_path / "n.db"), Fernet.generate_key().decode())
    ch = Channels(httpx.Client(transport=httpx.MockTransport(rec.handler)),
                  ticktick_client_id="cid", ticktick_client_secret="sec",
                  ticktick_redirect_uri="https://fin.example/parametres/ticktick/callback",
                  allowed_hosts=HOSTS)
    app = create_app(verifier=verifier, store=store, channels=ch, start_scheduler=False)
    with TestClient(app) as c:
        yield c, rec, store, app


H = {"Authorization": f"Bearer {make_token('u1', 'u1@example.com')}"}


@pytest.mark.parametrize("url", [
    "http://ntfy.sh/x", "https://evil.com/x", "https://ntfy.sh.evil.com/x",
    "https://user:pw@ntfy.sh/x", "https://ntfy.sh:8443/x", "https://169.254.169.254/latest",
    "https://notifier.fintrack.svc.cluster.local/internal/v1/events",
])
def test_ssrf_urls_rejected(url):
    with pytest.raises(ChannelError):
        validate_user_url(url, HOSTS)


def test_allowed_url():
    assert validate_user_url("https://ntfy.sh/mon-sujet", HOSTS) == "https://ntfy.sh/mon-sujet"


def test_prefs_secrets_never_returned_and_encrypted(env, tmp_path):
    c, _, store, _ = env
    r = c.put("/v1/prefs", headers=H, json={"ntfy_url": "https://ntfy.sh/secret-topic",
                                            "reminder_enabled": True, "reminder_day": 5})
    assert r.status_code == 200
    assert "secret-topic" not in r.text and r.json()["ntfy_configured"] is True
    raw = store._con.execute("SELECT ntfy_url FROM prefs").fetchone()[0]
    assert "secret-topic" not in raw          # chiffré au repos
    assert c.put("/v1/prefs", headers=H, json={"webhook_url": "https://evil.com/x"}).status_code == 422


def test_ticktick_oauth_flow(env):
    c, rec, store, _ = env
    url = c.post("/v1/ticktick/authorize", headers=H).json()["url"]
    assert url.startswith("https://ticktick.com/oauth/authorize?")
    state = httpx.URL(url).params["state"]
    other = {"Authorization": f"Bearer {make_token('u2')}"}
    # l'état est lié à l'utilisateur et à usage unique
    assert c.post("/v1/ticktick/callback", headers=other,
                  json={"code": "c", "state": state}).status_code == 400
    state = httpx.URL(c.post("/v1/ticktick/authorize", headers=H).json()["url"]).params["state"]
    r = c.post("/v1/ticktick/callback", headers=H, json={"code": "c", "state": state})
    assert r.status_code == 200 and r.json()["ticktick_connected"]
    assert c.post("/v1/ticktick/callback", headers=H,
                  json={"code": "c", "state": state}).status_code == 400
    assert c.get("/v1/ticktick/projects", headers=H).json() == [{"id": "p1", "name": "Finances"}]
    assert store.get("u1").ticktick_token == "tt-token"


def test_budget_event_creates_ticktick_task_once(env):
    c, rec, store, _ = env
    p = store.get("u1")
    p.ticktick_token, p.ticktick_project = "tt", "p1"
    store.save(p)
    ev = {"type": "budget.threshold", "user_id": "u1", "year": 2026, "month": 4,
          "category": "RESTAURANTS", "threshold": 100, "spent": 110.0, "budget": 100.0}
    assert c.post("/internal/v1/events", json=ev).status_code == 401
    r = c.post("/internal/v1/events", json=ev, headers={"X-Internal-Token": INTERNAL})
    assert r.json()["status"] == "sent"
    task = [x for x in rec.calls if x.url.path == "/open/v1/task"][0]
    assert b"RESTAURANTS" in task.content and b'"projectId":"p1"' in task.content.replace(b" ", b"")
    r = c.post("/internal/v1/events", json=ev, headers={"X-Internal-Token": INTERNAL})
    assert r.json()["status"] == "duplicate"


def test_internal_token_non_ascii_does_not_crash(env):
    c, *_ = env
    r = c.post("/internal/v1/events", json={},
               headers={"X-Internal-Token": ("é" * 40).encode("latin-1")})
    assert r.status_code in (401, 422)


def test_monthly_reminder(env):
    c, rec, store, app = env
    c.put("/v1/prefs", headers=H, json={"ntfy_url": "https://ntfy.sh/t", "reminder_enabled": True,
                                        "reminder_day": 3})
    run = app.state.run_reminders
    assert run(dt.date(2026, 11, 2)) == 0
    assert run(dt.date(2026, 11, 3)) == 1
    assert run(dt.date(2026, 11, 3)) == 0          # une seule fois par mois
    sent = [x for x in rec.calls if x.url.host == "ntfy.sh"][-1]
    assert b"octobre 2026" in sent.content


def test_failed_delivery_is_retried(env):
    c, rec, store, _ = env
    p = store.get("u1")
    p.ntfy_url = "https://ntfy.sh/t"
    store.save(p)
    ev = {"type": "budget.threshold", "user_id": "u1", "year": 2026, "month": 5,
          "category": "LOGEMENT", "threshold": 80, "spent": 85.0, "budget": 100.0}
    hdr = {"X-Internal-Token": INTERNAL}
    rec.fail = True                                         # ntfy en panne
    assert c.post("/internal/v1/events", json=ev, headers=hdr).json()["status"] == "failed"
    rec.fail = False                                        # rétabli : l'alerte repart
    assert c.post("/internal/v1/events", json=ev, headers=hdr).json()["status"] == "sent"
    assert c.post("/internal/v1/events", json=ev, headers=hdr).json()["status"] == "duplicate"


def test_reminder_without_channel_is_not_marked_sent(env):
    c, _, store, app = env
    c.put("/v1/prefs", headers=H, json={"reminder_enabled": True, "reminder_day": 9})
    assert app.state.run_reminders(dt.date(2026, 11, 9)) == 0
    assert store.mark_once("reminder:u1:2026-11")           # clé non consommée


def test_slack_format_only_for_real_slack_hosts():
    sent = []

    def h(req):
        sent.append(req)
        return httpx.Response(200)
    ch = Channels(httpx.Client(transport=httpx.MockTransport(h)), ticktick_client_id="",
                  ticktick_client_secret="", ticktick_redirect_uri="",
                  allowed_hosts=("hooks.slack.com", "evilslack.com"))
    from notifier.app.channels import Message
    ch.webhook("https://hooks.slack.com/services/x", Message("t", "b"))
    ch.webhook("https://evilslack.com/x", Message("t", "b"))
    assert b'"text"' in sent[0].content and b'"content"' in sent[1].content
