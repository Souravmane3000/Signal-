"""SIG-026A — Run Metrics source_health + per-source count mapping tests."""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import patch

from fastapi.testclient import TestClient

from api.main import app

client = TestClient(app, raise_server_exceptions=False)

RUN_ID = "22222222-2222-2222-2222-222222222222"
METRICS_ID = "33333333-3333-3333-3333-333333333333"


class _FakeCursor:
    def __init__(self, shared):
        self._shared = shared
        self._last_sql = ""

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False

    def execute(self, sql, params=None):
        self._last_sql = " ".join(sql.split())
        self._shared["calls"].append((self._last_sql, params))

    def fetchall(self):
        if "FROM agent_run_metrics" in self._last_sql:
            return self._shared.get("rows", [])
        return []

    def fetchone(self):
        return None


class _FakeConn:
    def __init__(self, shared):
        self._shared = shared

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False

    def cursor(self):
        return _FakeCursor(self._shared)


def _pool(shared):
    def _factory():
        return _FakeConn(shared)

    return _factory


def _base_row(**overrides):
    run_at = datetime(2026, 8, 4, 10, 30, tzinfo=timezone.utc)
    row = {
        "id": METRICS_ID,
        "briefing_run_id": RUN_ID,
        "run_at": run_at,
        "findings_retrieved": 20,
        "findings_dropped_freshness": 2,
        "findings_dropped_scope": 1,
        "findings_dropped_dedup": 3,
        "findings_in_briefing": 8,
        "tokens_used": 1200,
        "estimated_cost_usd": 0.042,
        "run_duration_seconds": 15.5,
        "tavily_result_count": None,
        "yc_result_count": None,
        "hn_result_count": None,
        "rss_result_count": None,
        "sources_queried": ["tavily", "yc", "hn", "rss"],
        "graph_version": "1.0",
        "source_health": {
            "tavily": False,
            "yc": False,
            "hn": False,
            "rss": True,
        },
        "run_status": "completed",
    }
    row.update(overrides)
    return row


def test_metrics_endpoint_exists():
    paths = {route.path for route in app.routes}
    assert "/metrics/runs" in paths


def test_source_health_returned():
    shared = {"calls": [], "rows": [_base_row()]}

    with patch("api.routes.pool.connection", side_effect=_pool(shared)):
        response = client.get("/metrics/runs?limit=5")

    assert response.status_code == 200
    run = response.json()["runs"][0]
    assert run["source_health"] == {
        "tavily": False,
        "yc": False,
        "hn": False,
        "rss": True,
    }
    sql = shared["calls"][0][0]
    assert "m.source_health" in sql


def test_per_source_counts_round_trip_when_stored():
    shared = {
        "calls": [],
        "rows": [
            _base_row(
                tavily_result_count=12,
                yc_result_count=4,
                hn_result_count=7,
                rss_result_count=3,
            )
        ],
    }

    with patch("api.routes.pool.connection", side_effect=_pool(shared)):
        response = client.get("/metrics/runs")

    run = response.json()["runs"][0]
    assert run["tavily_result_count"] == 12
    assert run["yc_result_count"] == 4
    assert run["hn_result_count"] == 7
    assert run["rss_result_count"] == 3


def test_zero_values_only_when_actually_stored():
    """NULL DB counts must stay null — not coerced to fabricated zeros."""
    shared = {
        "calls": [],
        "rows": [
            _base_row(
                tavily_result_count=None,
                yc_result_count=None,
                hn_result_count=0,
                rss_result_count=None,
            )
        ],
    }

    with patch("api.routes.pool.connection", side_effect=_pool(shared)):
        response = client.get("/metrics/runs")

    run = response.json()["runs"][0]
    assert run["tavily_result_count"] is None
    assert run["yc_result_count"] is None
    assert run["hn_result_count"] == 0
    assert run["rss_result_count"] is None


def test_metrics_empty_state():
    shared = {"calls": [], "rows": []}

    with patch("api.routes.pool.connection", side_effect=_pool(shared)):
        response = client.get("/metrics/runs")

    assert response.status_code == 200
    assert response.json() == {"runs": []}


def test_metrics_api_failure_state():
    with patch(
        "api.routes.pool.connection",
        side_effect=RuntimeError("db unavailable"),
    ):
        response = client.get("/metrics/runs")

    assert response.status_code == 500
    health = client.get("/health")
    assert health.status_code == 200


def test_source_health_rendered_in_frontend():
    html = Path("frontend/index.html").read_text(encoding="utf-8")
    assert "Source health" in html
    assert "metrics-source-health" in html
    assert "source_health" in html
    assert "✓ ${label}" in html or '`✓ ${label}`' in html or '"✓ "' in html or "'✓ '" in html
    assert "✗ ${label}" in html or '`✗ ${label}`' in html or '"✗ "' in html or "'✗ '" in html
    # Null-aware per-source display (no fabricated zeros)
    assert "count === null || count === undefined" in html
    assert "Per-source counts" in html
