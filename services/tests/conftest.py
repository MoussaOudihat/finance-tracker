"""Fixtures communes : jetons Supabase signés (ES256), faux PostgREST en
mémoire avec isolation par utilisateur (équivalent RLS), applications."""
import os
import sys
import time
import urllib.parse
import uuid

import pytest

HERE = os.path.dirname(os.path.abspath(__file__))
SERVICES = os.path.dirname(HERE)
for p in (SERVICES, os.path.join(SERVICES, "common")):
    if p not in sys.path:
        sys.path.insert(0, p)

os.environ["FINTRACK_NO_AUTOAPP"] = "1"
os.environ.setdefault("SUPABASE_URL", "https://proj.supabase.co")
os.environ.setdefault("SUPABASE_ANON_KEY", "anon-test-key")

import httpx  # noqa: E402
import jwt  # noqa: E402
from cryptography.hazmat.primitives.asymmetric import ec  # noqa: E402

from fintrack_common.auth import TokenVerifier  # noqa: E402

ISSUER = "https://proj.supabase.co/auth/v1"
_KEY = ec.generate_private_key(ec.SECP256R1())


class _FakeJwks:
    class _K:
        key = _KEY.public_key()

    def get_signing_key_from_jwt(self, token):
        return self._K()


def make_token(user_id: str, email: str = "u@example.com", *, exp_in: int = 3600,
               role: str = "authenticated", key=None, iss: str = ISSUER) -> str:
    now = int(time.time())
    return jwt.encode({"sub": user_id, "email": email, "role": role, "aud": "authenticated",
                       "iss": iss, "iat": now, "exp": now + exp_in},
                      key or _KEY, algorithm="ES256")


@pytest.fixture
def verifier():
    return TokenVerifier("https://proj.supabase.co", jwks_client=_FakeJwks())


# ── Faux PostgREST ───────────────────────────────────────────
UNIQUE = {"months": ("year", "month"), "categories": ("name",),
          "assets": ("year", "month", "asset_type", "asset_name"),
          "budgets": ("year", "month", "category"), "app_settings": ("key",)}


class FakePostgrest:
    def __init__(self):
        self.tables: dict[str, list[dict]] = {}
        self.requests = 0

    def seed(self, table, rows):
        self.tables.setdefault(table, []).extend(dict(r) for r in rows)

    @staticmethod
    def _match(row, key, cond):
        op, _, val = cond.partition(".")
        cur = row.get(key)
        if op == "eq":
            return str(cur) == val
        if op == "neq":
            return str(cur if cur is not None else "") != val
        if op == "in":
            items = [v.strip().strip('"') for v in val.strip("()").split(",") if v.strip()]
            return str(cur) in items
        if op == "ilike":                                     # * = joker, insensible à la casse
            import fnmatch
            return fnmatch.fnmatch(str(cur or "").lower(), val.lower())
        if op in ("gte", "lte"):
            return cur is not None and (float(cur) >= float(val) if op == "gte" else float(cur) <= float(val))
        raise AssertionError(f"opérateur non géré : {op}")

    @classmethod
    def _match_or(cls, row, expr):
        """or=(col.op.val,col.op.val) — sans parenthèses imbriquées."""
        parts = expr.strip("()").split(",")
        return any(cls._match(row, p.split(".", 1)[0], p.split(".", 1)[1]) for p in parts)

    def _filter(self, rows, params, uid):
        out = [r for r in rows if r.get("user_id") == uid]          # « RLS »
        for k, v in params.items():
            if k in ("select", "order", "limit", "offset", "on_conflict"):
                continue
            if k == "or":
                out = [r for r in out if self._match_or(r, v)]
                continue
            out = [r for r in out if self._match(r, k, v)]
        return out

    def handler(self, request: httpx.Request) -> httpx.Response:
        self.requests += 1
        auth = request.headers.get("authorization", "")
        try:
            uid = jwt.decode(auth[7:], options={"verify_signature": False})["sub"]
        except Exception:
            return httpx.Response(401, json={"message": "JWT"})
        table = request.url.path.rsplit("/", 1)[-1]
        rows = self.tables.setdefault(table, [])
        params = dict(urllib.parse.parse_qsl(request.url.query.decode()))
        if request.method == "GET":
            sel = self._filter(rows, params, uid)
            for part in reversed((params.get("order") or "").split(",")):
                if part:
                    col, _, d = part.partition(".")
                    sel.sort(key=lambda r: r.get(col), reverse=(d == "desc"))
            off, lim = int(params.get("offset", 0)), int(params.get("limit", 10**9))
            sel = sel[off:off + lim]
            cols = params.get("select", "*")
            if cols != "*":
                sel = [{c: r.get(c) for c in cols.split(",")} for r in sel]
            return httpx.Response(200, json=sel)
        if request.method == "POST":
            import json
            new = json.loads(request.content)
            if isinstance(new, list):                # insertion groupée : tout ou rien
                if any(n.get("user_id") != uid for n in new):
                    return httpx.Response(403, json={"message": "RLS"})
                ids = {r["id"] for r in rows if r["user_id"] == uid}
                if any(n["id"] in ids for n in new) or len({n["id"] for n in new}) != len(new):
                    return httpx.Response(409, json={"message": "duplicate"})
                if any(n.get("amount") is not None and n["amount"] <= 0 for n in new):
                    return httpx.Response(400, json={"message": "check violation"})
                rows.extend(new)
                return httpx.Response(201, json=new)
            if new.get("user_id") != uid:
                return httpx.Response(403, json={"message": "RLS"})
            upsert = "merge-duplicates" in request.headers.get("prefer", "")
            uniq = UNIQUE.get(table)
            for r in rows:
                same_pk = r["user_id"] == uid and "id" in new and r.get("id") == new["id"]
                same_uq = uniq and r["user_id"] == uid and all(r.get(c) == new.get(c) for c in uniq)
                if same_pk or same_uq:
                    if upsert:
                        r.update(new)
                        return httpx.Response(201)
                    return httpx.Response(409, json={"message": "duplicate"})
            rows.append(new)
            return httpx.Response(201, json=[new])
        if request.method == "PATCH":
            import json
            vals = json.loads(request.content)
            sel = self._filter(rows, params, uid)
            for r in sel:
                r.update(vals)
            return httpx.Response(200, json=sel)
        if request.method == "DELETE":
            sel = self._filter(rows, params, uid)
            self.tables[table] = [r for r in rows if r not in sel]
            return httpx.Response(200, json=sel)
        return httpx.Response(405)

    def client(self) -> httpx.Client:
        return httpx.Client(base_url="https://proj.supabase.co",
                            transport=httpx.MockTransport(self.handler))


DEFAULT_CATS = ["ALIMENTATION", "AUTRES", "LOGEMENT", "RESTAURANTS"]


@pytest.fixture
def db():
    return FakePostgrest()


@pytest.fixture
def user_id():
    return str(uuid.uuid4())


@pytest.fixture
def seeded(db, user_id):
    db.seed("categories", [{"id": i + 1, "user_id": user_id, "name": n, "is_default": 1}
                           for i, n in enumerate(DEFAULT_CATS)])
    return db
