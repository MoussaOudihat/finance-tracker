"""Desktop : garde-fou anti-écrasement de la synchro Supabase et
déconnexion limitée à l'appareil."""
import datetime as dt
import sqlite3

import pytest

from database import Database
from sync_supabase import SYNC_TS_KEY, SupabaseSync


class _Q:
    def __init__(self, store, table):
        self.store, self.table, self.filters = store, table, {}

    def select(self, *_a, **_k):
        return self

    def eq(self, k, v):
        self.filters[k] = v
        return self

    def limit(self, _n):
        return self

    def delete(self):
        self.store.deleted.append(self.table)
        return self

    def execute(self):
        class R:
            pass
        r = R()
        r.data = [row for row in self.store.rows.get(self.table, [])
                  if all(row.get(k) == v for k, v in self.filters.items())]
        return r


class FakeSupabase:
    def __init__(self):
        self.rows, self.deleted = {}, []

    def table(self, name):
        return _Q(self, name)


def _ts(minutes_ago: int) -> str:
    return (dt.datetime.now(dt.timezone.utc) - dt.timedelta(minutes=minutes_ago)).isoformat()


@pytest.fixture
def setup(tmp_path):
    path = str(tmp_path / "f.db")
    Database(path).close()
    client = FakeSupabase()
    return client, path, SupabaseSync(client, path, "u1")


def _set_local_ts(path, value):
    con = sqlite3.connect(path)
    con.execute("INSERT OR REPLACE INTO app_settings(key,value) VALUES(?,?)", (SYNC_TS_KEY, value))
    con.commit()
    con.close()


def test_push_refused_when_remote_changed_elsewhere(setup):
    client, path, sync = setup
    _set_local_ts(path, _ts(60))                      # dernière synchro il y a 1 h
    client.rows["app_settings"] = [{"key": SYNC_TS_KEY, "value": _ts(5), "user_id": "u1"}]
    newer, msg = sync.check_remote_newer()
    assert newer and "modifiées ailleurs" in msg
    out = sync._do_push()
    assert out.startswith("⚠️") and client.deleted == []     # rien n'a été effacé


def test_push_allowed_when_local_is_up_to_date(setup):
    client, path, sync = setup
    same = _ts(5)
    _set_local_ts(path, same)
    client.rows["app_settings"] = [{"key": SYNC_TS_KEY, "value": same, "user_id": "u1"}]
    assert sync.check_remote_newer() == (False, "")


def test_no_remote_timestamp_is_not_a_conflict(setup):
    _, _, sync = setup
    assert sync.check_remote_newer() == (False, "")


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
