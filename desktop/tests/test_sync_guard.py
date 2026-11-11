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


class _Rpc:
    def __init__(self, store, name, params):
        self.store, self.name, self.params = store, name, params

    def execute(self):
        self.store.rpc_calls.append((self.name, self.params))
        if self.store.rpc_error:
            err = self.store.rpc_error
            if isinstance(err, Exception):
                raise err
            raise RuntimeError(err)

        class R:
            pass
        r = R()
        r.data = self.store.rpc_result
        return r


class FakeSupabase:
    def __init__(self):
        self.rows, self.deleted = {}, []
        self.rpc_calls, self.rpc_error, self.rpc_result = [], None, "2026-11-10T10:00:00.000001+00:00"

    def table(self, name):
        return _Q(self, name)

    def rpc(self, name, params):
        return _Rpc(self, name, params)


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


def test_pc_clock_ahead_cannot_hide_a_web_edit(setup):
    """Ancien bug : comparaison « distant <= local + 1 s » entre deux
    horloges. Un PC en avance (dernier envoi daté de demain) prenait une
    saisie web d'aujourd'hui pour plus ancienne et l'écrasait."""
    client, path, sync = setup
    future = (dt.datetime.now(dt.timezone.utc) + dt.timedelta(days=1)).isoformat()
    _set_local_ts(path, future)
    client.rows["app_settings"] = [{"key": SYNC_TS_KEY, "value": _ts(1), "user_id": "u1"}]
    newer, _ = sync.check_remote_newer()
    assert newer
    assert sync._do_push().startswith("⚠️") and client.rpc_calls == []


def test_push_is_one_atomic_rpc_and_stores_new_version(setup):
    client, path, sync = setup
    same = _ts(5)
    _set_local_ts(path, same)
    client.rows["app_settings"] = [{"key": SYNC_TS_KEY, "value": same, "user_id": "u1"}]
    assert sync._do_push() == "✅  Synchronisation Supabase OK"
    assert client.deleted == []                       # plus de DELETE table par table
    [(name, params)] = client.rpc_calls
    assert name == "fintrack_replace_snapshot"
    assert params["p_expected"] == same and params["p_force"] is False
    assert set(params["p_tables"]) >= {"categories", "months", "expenses"}
    assert "smtp_pass" in params["p_exclude"]
    assert SYNC_TS_KEY not in params["p_settings"]
    assert not any(k in params["p_settings"] for k in ("smtp_pass", "ai_api_key"))
    assert sync._local_version() == client.rpc_result      # version renvoyée par le serveur


def test_server_side_conflict_keeps_local_version(setup):
    client, path, sync = setup
    same = _ts(5)
    _set_local_ts(path, same)
    client.rows["app_settings"] = [{"key": SYNC_TS_KEY, "value": same, "user_id": "u1"}]
    client.rpc_error = "{'code': 'P0001', 'message': 'fintrack:sync_conflict'}"
    out = sync._do_push()
    assert "modifiées ailleurs" in out and sync._local_version() == same


def test_failed_push_reports_error_and_changes_nothing_locally(setup):
    client, path, sync = setup
    client.rpc_error = "connexion perdue"
    out = sync._do_push()
    assert out.startswith("⚠️  Push échoué") and sync._local_version() is None


def test_pull_decision_uses_version_equality(setup, monkeypatch):
    client, path, sync = setup
    client.rows["months"] = [{"id": 1, "user_id": "u1"}]
    pulled = []
    monkeypatch.setattr(sync, "_do_pull", lambda: pulled.append(1))
    v = _ts(3)
    _set_local_ts(path, v)
    client.rows["app_settings"] = [{"key": SYNC_TS_KEY, "value": v, "user_id": "u1"}]
    assert sync.pull_if_newer()[0] is False and pulled == []
    # Version distante différente, même « plus ancienne » : on récupère.
    client.rows["app_settings"] = [{"key": SYNC_TS_KEY, "value": _ts(60), "user_id": "u1"}]
    assert sync.pull_if_newer()[0] is True and pulled == [1]


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


class _ApiError(Exception):
    """Forme des erreurs de postgrest-py : attributs code / message."""
    def __init__(self, code, message):
        super().__init__(message)
        self.code, self.message = code, message


@pytest.mark.parametrize("code,message,expected", [
    ("PGRST202", "Could not find the function public.fintrack_replace_snapshot", "non migrée"),
    ("57014", "canceling statement due to statement timeout", "délai dépassé"),
    # le nom de la fonction dans le texte ne suffit plus à conclure « non migrée »
    ("23503", "insert or update violates foreign key (fintrack_replace_snapshot)", "Push échoué : insert"),
])
def test_push_errors_are_classified_by_code(setup, code, message, expected):
    client, _, sync = setup
    client.rpc_error = _ApiError(code, message)
    assert expected in sync._do_push()


def test_pull_reads_version_before_data_and_aborts_on_table_error(setup, monkeypatch):
    """Revue v2.3 : la version distante était lue APRÈS les tables. Une
    saisie web pendant le téléchargement donnait une base locale marquée à
    jour sans cette saisie, et l'envoi suivant l'effaçait."""
    client, path, sync = setup
    client.rows["app_settings"] = [{"key": SYNC_TS_KEY, "value": "V1", "user_id": "u1"}]
    fetched = []

    def fetch(table):
        fetched.append(table)
        if table == "expenses":     # saisie web pendant le téléchargement
            client.rows["app_settings"] = [{"key": SYNC_TS_KEY, "value": "V2", "user_id": "u1"}]
        return []
    monkeypatch.setattr(sync, "_fetch_all", fetch)
    sync._do_pull()
    assert sync._local_version() == "V1"           # l'ancienne : l'envoi sera refusé
    assert sync.check_remote_newer()[0] is True

    def broken(table):
        raise RuntimeError("réseau coupé")
    monkeypatch.setattr(sync, "_fetch_all", broken)
    with pytest.raises(RuntimeError):
        sync._do_pull()                             # plus d'échec silencieux
    assert sync._local_version() == "V1"           # sauvegarde restaurée


def test_pull_aborts_when_remote_settings_cannot_be_read(setup, monkeypatch):
    """Revue v2.3 (2e passe) : réglages distants illisibles -> la base locale
    ne doit pas être marquée à jour (l'envoi suivant les effacerait)."""
    client, path, sync = setup
    _set_local_ts(path, "V0")
    client.rows["app_settings"] = [{"key": SYNC_TS_KEY, "value": "V1", "user_id": "u1"}]
    monkeypatch.setattr(sync, "_fetch_all", lambda table: [])
    real_table = client.table

    def table(name):
        q = real_table(name)
        if name == "app_settings" and q.filters == {} and getattr(table, "armed", False):
            raise RuntimeError("503 Service Unavailable")
        return q
    original_remote_version = sync._remote_version

    def remote_version():
        v = original_remote_version()
        table.armed = True            # les lectures suivantes d'app_settings échouent
        return v
    monkeypatch.setattr(client, "table", table)
    monkeypatch.setattr(sync, "_remote_version", remote_version)
    with pytest.raises(RuntimeError):
        sync._do_pull()
    table.armed = False
    assert sync._local_version() == "V0"            # sauvegarde restaurée, pas « V1 »
