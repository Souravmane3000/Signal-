"""SIG-027 / SIG-027B / persistence fix — Configuration + Memory Inspector tests."""

from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock, patch
from uuid import UUID, uuid4

from fastapi.testclient import TestClient
from tests.conftest import TEST_USER_ID, attach_default_auth

from api.main import app

client = TestClient(app, raise_server_exceptions=False)
attach_default_auth(client)

_AUTH_UUID = UUID(TEST_USER_ID)

FRONTEND = Path("frontend/index.html")


class _FakeCursor:
    def __init__(self, shared):
        self._shared = shared
        self._last_sql = ""
        self._last_params = None

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False

    def execute(self, sql, params=None):
        self._last_sql = " ".join(sql.split())
        self._last_params = params
        self._shared["calls"].append((self._last_sql, params))

        # Mutate in-memory row on write so subsequent GET sees persisted values.
        if self._last_sql.startswith("UPDATE user_configs"):
            # params: delivery_email, keywords, verticals, stage_filter,
            #         schedule_freq, updated_at, user_id
            row = self._shared.get("config_row")
            if row is not None and params:
                row = dict(row)
                row["delivery_email"] = params[0]
                if len(params) >= 5:
                    row["keywords"] = list(params[1])
                    row["verticals"] = list(params[2])
                    row["stage_filter"] = list(params[3])
                    row["schedule_freq"] = params[4]
                self._shared["config_row"] = row
                self._shared["last_returning"] = row
            else:
                self._shared["last_returning"] = None
        elif self._last_sql.startswith("INSERT INTO user_configs"):
            # params: user_id, keywords, verticals, stage_filter, schedule_freq,
            #         delivery_email, created_at, updated_at
            row = {
                "user_id": params[0],
                "keywords": list(params[1]),
                "verticals": list(params[2]),
                "stage_filter": list(params[3]),
                "schedule_freq": params[4],
                "delivery_email": params[5],
            }
            self._shared["config_row"] = row
            self._shared["last_returning"] = row

    def fetchone(self):
        sql = self._last_sql
        if "FROM auth.users" in sql:
            return self._shared.get("auth_user")
        if sql.startswith("UPDATE user_configs") or sql.startswith(
            "INSERT INTO user_configs"
        ):
            return self._shared.get("last_returning")
        if "FROM user_configs" in sql:
            return self._shared.get("config_row")
        return None

    def fetchall(self):
        return []


class _FakeConn:
    def __init__(self, shared):
        self._shared = shared

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False

    def cursor(self):
        return _FakeCursor(self._shared)

    def commit(self):
        self._shared["committed"] = True


def _pool(shared):
    def _factory():
        return _FakeConn(shared)

    return _factory


def _base_config_row(user_uuid, email="old@example.com"):
    return {
        "user_id": str(user_uuid),
        "keywords": ["Indian startup"],
        "verticals": ["AI"],
        "stage_filter": ["seed"],
        "schedule_freq": "weekly",
        "delivery_email": email,
    }


def test_config_and_memory_endpoints_exist():
    paths = {route.path for route in app.routes}
    assert "/config" in paths
    assert "/memory/semantic" in paths
    assert "/memory/episodic" in paths
    assert "/memory/procedural" in paths


def test_config_loads_from_database_row():
    user_uuid = _AUTH_UUID
    shared = {
        "calls": [],
        "auth_user": {"id": user_uuid},
        "config_row": _base_config_row(user_uuid, email="founder@example.com"),
        "committed": False,
    }

    with patch("api.routes.pool.connection", side_effect=_pool(shared)), patch.dict(
        "os.environ", {"GRAPH_VERSION": "1.0"}, clear=False
    ):
        response = client.get("/config")

    assert response.status_code == 200
    body = response.json()
    assert body["delivery_email"] == "founder@example.com"
    assert body["schedule_freq"] == "weekly"
    assert body["from_defaults"] is False
    assert body["graph_version"] == "1.0"
    assert body["max_findings_per_run"] == 50
    sqls = [c[0] for c in shared["calls"]]
    assert any("FROM user_configs" in s for s in sqls)
    # Must query by resolved UUID — never by the Phase-1 string "user_001".
    assert any(
        c[1] and str(user_uuid) in [str(p) for p in c[1]]
        for c in shared["calls"]
        if c[1]
    )


def test_config_empty_falls_back_to_defaults_silently():
    user_uuid = _AUTH_UUID
    shared = {
        "calls": [],
        "auth_user": {"id": user_uuid},
        "config_row": None,
        "committed": False,
    }

    with patch("api.routes.pool.connection", side_effect=_pool(shared)), patch.dict(
        "os.environ", {"GRAPH_VERSION": "1.0"}, clear=False
    ):
        response = client.get("/config")

    assert response.status_code == 200
    body = response.json()
    assert body["from_defaults"] is True
    assert body["schedule_freq"] == "weekly"
    assert isinstance(body["keywords"], list)
    assert body["delivery_email"]


def test_config_defaults_when_auth_user_missing():
    shared = {
        "calls": [],
        "auth_user": None,
        "config_row": None,
        "committed": False,
    }

    with patch("api.routes.pool.connection", side_effect=_pool(shared)), patch.dict(
        "os.environ", {"GRAPH_VERSION": "1.0"}, clear=False
    ):
        response = client.get("/config")

    assert response.status_code == 200
    assert response.json()["from_defaults"] is True


def test_config_api_failure_state():
    with patch(
        "api.routes.pool.connection",
        side_effect=RuntimeError("db unavailable"),
    ):
        response = client.get("/config")

    assert response.status_code == 500
    health = client.get("/health")
    assert health.status_code == 200


def test_put_config_updates_delivery_email():
    user_uuid = _AUTH_UUID
    shared = {
        "calls": [],
        "auth_user": {"id": user_uuid},
        "config_row": _base_config_row(user_uuid, email="old@example.com"),
        "committed": False,
    }

    with patch("api.routes.pool.connection", side_effect=_pool(shared)), patch.dict(
        "os.environ", {"GRAPH_VERSION": "1.0"}, clear=False
    ):
        response = client.put(
            "/config",
            json={"delivery_email": "new@example.com"},
        )

    assert response.status_code == 200
    body = response.json()
    assert body["delivery_email"] == "new@example.com"
    assert body["from_defaults"] is False
    assert shared["committed"] is True
    assert shared["config_row"]["delivery_email"] == "new@example.com"
    sqls = [c[0] for c in shared["calls"]]
    assert any("UPDATE user_configs" in s for s in sqls)
    assert any("SET delivery_email" in s for s in sqls)
    assert sum(1 for s in sqls if "FROM user_configs" in s) == 1


def test_put_config_creates_row_when_missing():
    user_uuid = _AUTH_UUID
    shared = {
        "calls": [],
        "auth_user": {"id": user_uuid},
        "config_row": None,
        "committed": False,
    }

    with patch("api.routes.pool.connection", side_effect=_pool(shared)), patch.dict(
        "os.environ", {"GRAPH_VERSION": "1.0"}, clear=False
    ):
        response = client.put(
            "/config",
            json={"delivery_email": "created@example.com"},
        )

    assert response.status_code == 200
    assert response.json()["delivery_email"] == "created@example.com"
    assert shared["committed"] is True
    assert shared["config_row"]["delivery_email"] == "created@example.com"
    sqls = [c[0] for c in shared["calls"]]
    assert any("INSERT INTO user_configs" in s for s in sqls)


def test_put_then_get_returns_persisted_email():
    """Round-trip: PUT must leave a row that GET reads back (no model_copy mask)."""
    user_uuid = _AUTH_UUID
    shared = {
        "calls": [],
        "auth_user": {"id": user_uuid},
        "config_row": None,
        "committed": False,
    }

    with patch("api.routes.pool.connection", side_effect=_pool(shared)), patch.dict(
        "os.environ", {"GRAPH_VERSION": "1.0"}, clear=False
    ):
        put_res = client.put(
            "/config",
            json={"delivery_email": "persist@example.com"},
        )
        get_res = client.get("/config")

    assert put_res.status_code == 200
    assert put_res.json()["delivery_email"] == "persist@example.com"
    assert get_res.status_code == 200
    assert get_res.json()["delivery_email"] == "persist@example.com"
    assert get_res.json()["from_defaults"] is False


def test_schedule_freq_persistence():
    user_uuid = _AUTH_UUID
    shared = {
        "calls": [],
        "auth_user": {"id": user_uuid},
        "config_row": _base_config_row(user_uuid, email="sched@example.com"),
        "committed": False,
    }

    with patch("api.routes.pool.connection", side_effect=_pool(shared)), patch.dict(
        "os.environ", {"GRAPH_VERSION": "1.0"}, clear=False
    ):
        put_res = client.put("/config", json={"schedule_freq": "daily"})
        get_res = client.get("/config")

    assert put_res.status_code == 200
    assert put_res.json()["schedule_freq"] == "daily"
    assert get_res.status_code == 200
    assert get_res.json()["schedule_freq"] == "daily"
    assert shared["config_row"]["schedule_freq"] == "daily"


def test_stage_filter_persistence():
    user_uuid = _AUTH_UUID
    shared = {
        "calls": [],
        "auth_user": {"id": user_uuid},
        "config_row": _base_config_row(user_uuid, email="stage@example.com"),
        "committed": False,
    }

    with patch("api.routes.pool.connection", side_effect=_pool(shared)), patch.dict(
        "os.environ", {"GRAPH_VERSION": "1.0"}, clear=False
    ):
        put_res = client.put(
            "/config",
            json={"stage_filter": ["Seed", "Series B"]},
        )
        get_res = client.get("/config")

    assert put_res.status_code == 200
    assert put_res.json()["stage_filter"] == ["Seed", "Series B"]
    assert get_res.status_code == 200
    assert get_res.json()["stage_filter"] == ["Seed", "Series B"]
    assert shared["config_row"]["stage_filter"] == ["Seed", "Series B"]


def test_stage_filter_rejects_series_c():
    user_uuid = _AUTH_UUID
    shared = {
        "calls": [],
        "auth_user": {"id": user_uuid},
        "config_row": _base_config_row(user_uuid),
        "committed": False,
    }

    with patch("api.routes.pool.connection", side_effect=_pool(shared)):
        response = client.put(
            "/config",
            json={"stage_filter": ["Seed", "Series C"]},
        )

    assert response.status_code == 400


def test_get_does_not_always_return_defaults_when_row_exists():
    user_uuid = _AUTH_UUID
    shared = {
        "calls": [],
        "auth_user": {"id": user_uuid},
        "config_row": _base_config_row(user_uuid, email="stored@example.com"),
        "committed": False,
    }

    with patch("api.routes.pool.connection", side_effect=_pool(shared)):
        response = client.get("/config")

    body = response.json()
    assert body["delivery_email"] == "stored@example.com"
    assert body["delivery_email"] != "test@example.com"  # Phase-1 default
    assert body["from_defaults"] is False


def test_put_config_rejects_invalid_email():
    response = client.put("/config", json={"delivery_email": "not-an-email"})
    assert response.status_code == 400


def test_semantic_memory_loads():
    memory = {
        "seen_urls": ["https://inc42.com/a"],
        "seen_titles": ["Alpha"],
        "seen_company_dates": ["paynova|2025-03-10"],
        "embedding": [0.1, 0.2],
    }
    store = MagicMock()
    store.get.return_value = SimpleNamespace(
        key="memory",
        value=memory,
        created_at=None,
    )

    with patch("api.routes._get_store", return_value=store):
        response = client.get("/memory/semantic")

    assert response.status_code == 200
    body = response.json()
    assert body["empty"] is False
    assert body["memory"]["seen_urls"] == ["https://inc42.com/a"]
    assert "embedding" not in body["memory"]


def test_semantic_memory_empty_state():
    store = MagicMock()
    store.get.return_value = None

    with patch("api.routes._get_store", return_value=store):
        response = client.get("/memory/semantic")

    assert response.status_code == 200
    body = response.json()
    assert body["empty"] is True
    assert body["memory"] == {}


def test_episodic_memory_loads():
    episode = {
        "run_id": "run-abc",
        "thread_id": "thread-1",
        "timestamp": "2026-08-04T10:00:00+00:00",
        "item_titles": ["PayNova raises $8M"],
        "source_urls": ["https://inc42.com/paynova"],
        "company_names_normalized": ["paynova"],
        "briefing_summary": "Fintech funding highlight.",
        "embedding": [0.1, 0.2, 0.3],
    }
    store = MagicMock()
    store.search.return_value = [
        SimpleNamespace(key="run-abc", value=episode, created_at=None)
    ]

    with patch("api.routes._get_store", return_value=store):
        response = client.get("/memory/episodic")

    assert response.status_code == 200
    body = response.json()
    assert len(body["episodes"]) == 1
    ep = body["episodes"][0]
    assert ep["title"] == "PayNova raises $8M"
    assert ep["summary"] == "Fintech funding highlight."
    assert "embedding" not in ep


def test_episodic_memory_empty_state():
    store = MagicMock()
    store.search.return_value = []

    with patch("api.routes._get_store", return_value=store):
        response = client.get("/memory/episodic")

    assert response.status_code == 200
    assert response.json() == {"episodes": []}


def test_procedural_memory_loads():
    prefs = {
        "high_signal_categories": ["funding"],
        "low_signal_categories": [],
        "trusted_sources": ["inc42"],
        "preferred_stage": ["seed"],
        "query_boost_terms": ["Bengaluru"],
        "query_suppress_terms": ["Infosys"],
        "source_weights": {"tavily": 1.0, "yc": 1.0, "hn": 0.7, "google_news": 0.65},
        "min_confidence_threshold": 0.70,
        "embedding": [9.9],
    }
    store = MagicMock()
    store.get.return_value = SimpleNamespace(
        key="preferences",
        value=prefs,
        created_at=None,
    )

    with patch("api.routes._get_store", return_value=store):
        response = client.get("/memory/procedural")

    assert response.status_code == 200
    body = response.json()
    assert body["empty"] is False
    assert body["preferences"]["high_signal_categories"] == ["funding"]
    assert "embedding" not in body["preferences"]


def test_procedural_memory_empty_state():
    store = MagicMock()
    store.get.return_value = None

    with patch("api.routes._get_store", return_value=store):
        response = client.get("/memory/procedural")

    assert response.status_code == 200
    body = response.json()
    assert body["empty"] is True
    assert body["preferences"] == {}


def test_memory_api_failure_state():
    with patch("api.routes._get_store", side_effect=RuntimeError("store down")):
        sem = client.get("/memory/semantic")
        ep = client.get("/memory/episodic")
        pr = client.get("/memory/procedural")

    assert sem.status_code == 500
    assert ep.status_code == 500
    assert pr.status_code == 500
    health = client.get("/health")
    assert health.status_code == 200


def test_frontend_config_and_memory_screens():
    html = FRONTEND.read_text(encoding="utf-8")

    assert 'setView(\'config\')' in html or 'setView("config")' in html
    assert 'setView(\'memory\')' in html or 'setView("memory")' in html
    assert "view-config" in html
    assert "view-memory" in html
    assert "Memory Inspector" in html
    assert "Configuration" in html

    assert "user_configs" not in html
    assert "config-defaults-banner" not in html

    assert "saveDeliveryEmail" in html
    assert "saveScheduleFreq" in html
    assert "saveStageFilter" in html
    assert "config-schedule-select" in html
    assert "config-stage-filter" in html
    assert "method: 'PUT'" in html or 'method: "PUT"' in html
    assert "delivery_email" in html
    assert "schedule_freq" in html
    assert "stage_filter" in html
    # After save, frontend reloads from GET
    assert "await fetchConfig()" in html
    assert "Series C" not in html.split("CONFIG_STAGE_OPTIONS")[1].split("];")[0]

    assert "Semantic Memory" in html
    assert "Episodic Memory" in html
    assert "Procedural Memory" in html
    assert "/memory/semantic" in html
    assert "/memory/episodic" in html
    assert "/memory/procedural" in html
    assert "memory-semantic-empty" in html
    assert "No learned preferences yet" in html

    assert "Source health" in html
    assert "Per-source counts" not in html

    assert "Couldn't load configuration" in html
    assert "Couldn't load memory" in html
    assert "grid-cols-1 sm:grid-cols-2" in html
    assert "p-4 md:p-6" in html


def test_existing_runtime_endpoints_unchanged():
    paths = {route.path for route in app.routes}
    for required in (
        "/health",
        "/run",
        "/agent/status",
        "/briefings",
        "/metrics/runs",
        "/items/{item_id}/feedback",
    ):
        assert required in paths
