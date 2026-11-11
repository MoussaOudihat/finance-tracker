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
               role: str = "authenticated", key=None, iss: str = ISSUER,
               **extra) -> str:
    now = int(time.time())
    return jwt.encode({"sub": user_id, "email": email, "role": role, "aud": "authenticated",
                       "iss": iss, "iat": now, "exp": now + exp_in, **extra},
                      key or _KEY, algorithm="ES256")


@pytest.fixture
def verifier():
    return TokenVerifier("https://proj.supabase.co", jwks_client=_FakeJwks())


# ── Faux PostgREST ───────────────────────────────────────────
UNIQUE = {"months": ("year", "month"), "categories": ("name",),
          "assets": ("year", "month", "asset_type", "asset_name"),
          "liabilities": ("year", "month", "liability_name"),
          "budgets": ("year", "month", "category"), "app_settings": ("key",)}
APPLY_TABLES = {"months", "expenses", "revenues", "savings", "assets", "liabilities",
                "budgets", "recurring_transactions"}
FK = {"expenses": (("month_id", "months"), ("category_id", "categories")),
      "revenues": (("month_id", "months"),), "savings": (("month_id", "months"),),
      "recurring_transactions": (("category_id", "categories"),)}


class RpcError(Exception):
    def __init__(self, code: str, message: str = ""):
        super().__init__(message or code)
        self.code, self.message = code, message or code


class FakePostgrest:
    def __init__(self):
        self.tables: dict[str, list[dict]] = {}
        self.requests = 0
        self.rpc_calls: list[list[dict]] = []

    # ── Émulation de public.fintrack_apply (migration_v2_3_atomic.sql) ──
    def _next_id(self, uid, table):
        return max((r["id"] for r in self.tables.get(table, []) if r["user_id"] == uid), default=0) + 1

    @staticmethod
    def _resolve(row, results):
        out = {}
        for k, v in (row or {}).items():
            if k == "user_id":
                continue
            if isinstance(v, dict) and "$ref" in v:
                i, f = v["$ref"]
                v = results[i][f]
            out[k] = v
        return out

    @staticmethod
    def _public(row):
        return {k: v for k, v in row.items() if k != "user_id"}

    def _check_fk(self, uid, table, row):
        for col, ref_table in FK.get(table, ()):
            val = row.get(col)
            if val is None:
                continue
            if not any(r["user_id"] == uid and r["id"] == val for r in self.tables.get(ref_table, [])):
                raise RpcError("23503", "foreign key violation")

    def rpc_apply(self, uid, ops):
        import copy
        snapshot = copy.deepcopy(self.tables)
        self.rpc_calls.append(ops)
        try:
            results, wrote = [], False
            for op in ops:
                kind, table = op["op"], op.get("table")
                if kind in ("insert", "upsert", "update", "delete") and table not in APPLY_TABLES:
                    raise RpcError("22023", "fintrack:bad_table")
                rows = self.tables.setdefault(table or "months", [])
                res = None
                if kind == "month":
                    mo = next((r for r in rows if r["user_id"] == uid and r["year"] == op["year"]
                               and r["month"] == op["month"]), None)
                    if mo is None:
                        mo = {"id": self._next_id(uid, "months"), "user_id": uid,
                              "year": op["year"], "month": op["month"], "closed": 0}
                        rows.append(mo)
                        wrote = True
                    if op.get("require_open") and mo.get("closed"):
                        raise RpcError("P0001", "fintrack:month_closed")
                    res = self._public(mo)
                elif kind == "adjust_asset":
                    assets = self.tables.setdefault("assets", [])
                    snaps = [a for a in assets if a["user_id"] == uid and a["asset_type"] == "compte"
                             and a["asset_name"] == op["asset_name"]]
                    cur = max(snaps, key=lambda a: (a["year"], a["month"]), default=None)
                    y, m, d = op["year"], op["month"], op["delta"]
                    if cur and d and (y, m) >= (cur["year"], cur["month"]):
                        vals = {"value": max(0.0, (cur["value"] or 0) + d),
                                "cost_basis": max(0.0, (cur["cost_basis"] or 0) + d)}
                        if (cur["year"], cur["month"]) == (y, m):
                            cur.update(vals)
                            res = self._public(cur)
                        else:
                            new = {"id": self._next_id(uid, "assets"), "user_id": uid, "year": y,
                                   "month": m, "asset_type": "compte", "asset_name": cur["asset_name"],
                                   "notes": cur.get("notes") or "", **vals}
                            assets.append(new)
                            res = self._public(new)
                        wrote = True
                elif kind == "assert_open":
                    mo = next((r for r in rows if r["user_id"] == uid and r["id"] == op["month_id"]), None)
                    if mo is None:
                        raise RpcError("P0001", "fintrack:not_found")
                    if mo.get("closed"):
                        raise RpcError("P0001", "fintrack:month_closed")
                elif kind in ("insert", "upsert"):
                    out = []
                    for item in (op["rows"] if "rows" in op else [op["row"]]):
                        item = self._resolve(item, results)
                        self._check_fk(uid, table, item)
                        if item.get("amount") is not None and table != "budgets" and item["amount"] <= 0:
                            raise RpcError("23514", "check violation")
                        item.setdefault("id", self._next_id(uid, table))
                        mine = [r for r in rows if r["user_id"] == uid]
                        if kind == "upsert":
                            key = op["conflict"]
                            hit = next((r for r in mine if all(r.get(c) == item.get(c) for c in key)), None)
                            if hit:
                                hit.update({k: v for k, v in item.items() if k != "id" and k not in key})
                                out.append(self._public(hit))
                                continue
                        uniq = UNIQUE.get(table)
                        if any(r["id"] == item["id"] for r in mine) or (
                                uniq and any(all(r.get(c) == item.get(c) for c in uniq) for r in mine)):
                            raise RpcError("23505", "duplicate key")
                        new = {**item, "user_id": uid}
                        rows.append(new)
                        out.append(self._public(new))
                    res = out[0] if "row" in op else out
                    wrote = True
                elif kind in ("update", "delete"):
                    where = self._resolve(op["where"], results)
                    hits = [r for r in rows if r["user_id"] == uid
                            and all(r.get(k) == v for k, v in where.items())]
                    if kind == "update":
                        values = {k: v for k, v in self._resolve(op["set"], results).items() if k != "id"}
                        for r in hits:
                            r.update(values)
                    else:
                        self.tables[table] = [r for r in rows if not any(r is h for h in hits)]
                    res = [self._public(r) for r in hits]
                    if op.get("require") and not res:
                        raise RpcError("P0001", "fintrack:conflict" if op.get("on_missing") == "conflict"
                                       else "fintrack:not_found")
                    wrote = wrote or bool(res)
                else:
                    raise RpcError("22023", "fintrack:bad_op")
                results.append(res)
            version = self.bump(uid) if wrote else None
            return httpx.Response(200, json={"results": results, "version": version})
        except RpcError as e:
            self.tables = snapshot
            status = 409 if e.code in ("23505", "23503") else 400
            return httpx.Response(status, json={"code": e.code, "message": e.message})

    def bump(self, uid):
        import datetime as _dt
        v = _dt.datetime.now(_dt.UTC).isoformat()
        settings = self.tables.setdefault("app_settings", [])
        row = next((r for r in settings if r["user_id"] == uid and r["key"] == "last_supabase_sync"), None)
        if row:
            row["value"] = v
        else:
            settings.append({"user_id": uid, "key": "last_supabase_sync", "value": v})
        return v

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
            if k == "and":                                   # and=(col.op.val,col.op.val)
                parts = [p.split(".", 1) for p in v.strip("()").split(",")]
                out = [r for r in out if all(self._match(r, c, cond) for c, cond in parts)]
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
        if request.url.path == "/rest/v1/rpc/fintrack_apply":
            import json
            return self.rpc_apply(uid, json.loads(request.content)["ops"])
        if "/rpc/" in request.url.path:
            return httpx.Response(404, json={"code": "PGRST202", "message": "function not found"})
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
