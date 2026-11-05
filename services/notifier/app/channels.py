"""
channels.py — Canaux d'envoi : TickTick (API officielle Open API, OAuth2),
ntfy, webhooks Discord / Slack.

Anti-SSRF : les URLs saisies par l'utilisateur ne peuvent viser que des
hôtes HTTPS d'une liste blanche (NOTIFIER_ALLOWED_HOSTS), sans
identifiants ni port exotique ; les redirections ne sont jamais suivies.
"""
from __future__ import annotations

import logging
import urllib.parse
from dataclasses import dataclass

import httpx

log = logging.getLogger(__name__)

TICKTICK_AUTH = "https://ticktick.com/oauth/authorize"
TICKTICK_TOKEN_URL = "https://ticktick.com/oauth/token"  # noqa: S105  # nosec B105
TICKTICK_API = "https://api.ticktick.com/open/v1"
TICKTICK_SCOPE = "tasks:write tasks:read"

DEFAULT_ALLOWED_HOSTS = ("ntfy.sh", "discord.com", "discordapp.com", "hooks.slack.com")


@dataclass
class Message:
    title: str
    body: str
    priority: int = 0        # 0 normal, 3 moyen, 5 haut (échelle TickTick)


class ChannelError(RuntimeError):
    pass


def validate_user_url(url: str, allowed_hosts: tuple[str, ...]) -> str:
    url = (url or "").strip()
    if not url:
        return ""
    p = urllib.parse.urlsplit(url)
    host = (p.hostname or "").lower()
    if p.scheme != "https" or p.username or p.password or p.port not in (None, 443):
        raise ChannelError("L'URL doit être en https://, sans identifiant ni port.")
    if not any(host == h or host.endswith("." + h) for h in allowed_hosts):
        raise ChannelError(f"Hôte non autorisé : {host}. Autorisés : {', '.join(allowed_hosts)}.")
    if len(url) > 500:
        raise ChannelError("URL trop longue.")
    return url


class Channels:
    def __init__(self, http: httpx.Client, *, ticktick_client_id: str,
                 ticktick_client_secret: str, ticktick_redirect_uri: str,
                 allowed_hosts: tuple[str, ...]):
        self.http = http
        self.tt_id = ticktick_client_id
        self.tt_secret = ticktick_client_secret
        self.tt_redirect = ticktick_redirect_uri
        self.allowed_hosts = allowed_hosts

    # ── TickTick ─────────────────────────────────────────────
    @property
    def ticktick_enabled(self) -> bool:
        return bool(self.tt_id and self.tt_secret and self.tt_redirect)

    def ticktick_authorize_url(self, state: str) -> str:
        q = urllib.parse.urlencode({"client_id": self.tt_id, "scope": TICKTICK_SCOPE,
                                    "state": state, "redirect_uri": self.tt_redirect,
                                    "response_type": "code"})
        return f"{TICKTICK_AUTH}?{q}"

    def ticktick_exchange(self, code: str) -> str:
        r = self.http.post(TICKTICK_TOKEN_URL, auth=(self.tt_id, self.tt_secret), data={
            "code": code, "grant_type": "authorization_code",
            "scope": TICKTICK_SCOPE, "redirect_uri": self.tt_redirect})
        if r.status_code != 200 or "access_token" not in r.json():
            log.warning("Échange OAuth TickTick refusé (HTTP %s)", r.status_code)
            raise ChannelError("Connexion TickTick refusée.")
        return r.json()["access_token"]

    def ticktick_projects(self, token: str) -> list[dict]:
        r = self.http.get(f"{TICKTICK_API}/project",
                          headers={"Authorization": f"Bearer {token}"})
        if r.status_code == 401:
            raise ChannelError("Accès TickTick expiré — reconnectez TickTick.")
        r.raise_for_status()
        return [{"id": p["id"], "name": p.get("name", "")} for p in r.json()]

    def ticktick_task(self, token: str, project_id: str, msg: Message,
                      due_iso: str | None = None) -> None:
        task = {"title": msg.title[:200], "content": msg.body[:2000], "priority": msg.priority}
        if project_id:
            task["projectId"] = project_id
        if due_iso:
            task["dueDate"] = due_iso
            task["isAllDay"] = True
        r = self.http.post(f"{TICKTICK_API}/task", json=task,
                           headers={"Authorization": f"Bearer {token}"})
        if r.status_code == 401:
            raise ChannelError("Accès TickTick expiré — reconnectez TickTick.")
        r.raise_for_status()

    # ── ntfy / webhooks ──────────────────────────────────────
    def ntfy(self, url: str, msg: Message) -> None:
        validate_user_url(url, self.allowed_hosts)
        # Publication JSON (UTF-8 natif) : POST https://<hôte>/ {"topic": …}
        p = urllib.parse.urlsplit(url)
        topic = p.path.strip("/")
        if not topic or "/" in topic:
            raise ChannelError("URL ntfy attendue : https://ntfy.sh/<sujet>")
        prio = {0: 3, 3: 4, 5: 5}.get(msg.priority, 3)
        r = self.http.post(f"https://{p.hostname}/", json={
            "topic": topic, "title": msg.title, "message": msg.body,
            "priority": prio, "tags": ["moneybag"]})
        r.raise_for_status()

    def webhook(self, url: str, msg: Message) -> None:
        validate_user_url(url, self.allowed_hosts)
        host = urllib.parse.urlsplit(url).hostname or ""
        text = f"**{msg.title}**\n{msg.body}"
        is_slack = host == "slack.com" or host.endswith(".slack.com")   # pas « evilslack.com »
        payload = {"text": text} if is_slack else {"content": text[:1900]}
        r = self.http.post(url, json=payload)
        r.raise_for_status()
