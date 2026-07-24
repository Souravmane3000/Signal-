"""SIG-023-deploy — APScheduler integration tests (application layer only)."""

from __future__ import annotations

import threading
import time
from unittest.mock import MagicMock, patch

import pytest
from fastapi.testclient import TestClient

from agent.graph import GraphRunResult
from api import scheduler as sched
from api.scheduler import (
    JOB_ID,
    _run_scheduled_pipeline,
    get_scheduler,
    is_running,
    job_count,
    next_run_time,
    start_scheduler,
    stop_scheduler,
)


@pytest.fixture(autouse=True)
def _clean_scheduler(monkeypatch):
    """Isolate each test with a fresh scheduler; force enable for these tests."""
    monkeypatch.setenv("SIGNAL_SCHEDULER_ENABLED", "1")
    stop_scheduler(wait=False)
    yield
    stop_scheduler(wait=False)


def test_scheduler_starts_once_and_registers_weekly_job():
    s1 = start_scheduler()
    assert s1 is not None
    assert is_running()
    assert job_count() == 1
    assert s1.get_job(JOB_ID) is not None
    assert next_run_time() is not None

    s2 = start_scheduler()
    assert s2 is s1
    assert job_count() == 1  # no duplicate jobs


def test_scheduler_stops_cleanly():
    start_scheduler()
    assert is_running()
    stop_scheduler(wait=False)
    assert not is_running()
    assert get_scheduler() is None


def test_weekly_job_callable_is_shared_pipeline():
    start_scheduler()
    job = get_scheduler().get_job(JOB_ID)
    assert job is not None
    assert job.func is _run_scheduled_pipeline
    # Cron weekly (Monday) — trigger has day_of_week field
    trigger = job.trigger
    assert hasattr(trigger, "fields") or trigger.__class__.__name__ == "CronTrigger"


def test_scheduled_execution_calls_execute_pipeline_not_duplicate_graph():
    with patch("api.routes.execute_pipeline") as mock_pipeline:
        mock_pipeline.return_value = MagicMock()
        _run_scheduled_pipeline()
        mock_pipeline.assert_called_once()
        req = mock_pipeline.call_args.args[0]
        assert req.run_type == "scheduled"


def test_failure_recovery_keeps_scheduler_alive():
    start_scheduler()
    assert is_running()

    with patch(
        "api.routes.execute_pipeline",
        side_effect=RuntimeError("boom"),
    ):
        _run_scheduled_pipeline()  # must not raise

    assert is_running()
    assert get_scheduler().get_job(JOB_ID) is not None
    assert next_run_time() is not None


def test_overlapping_scheduled_runs_are_skipped():
    started = threading.Event()
    release = threading.Event()
    calls = {"n": 0}

    def slow_pipeline(_request):
        calls["n"] += 1
        started.set()
        release.wait(timeout=5)

    with patch("api.routes.execute_pipeline", side_effect=slow_pipeline):
        t = threading.Thread(target=_run_scheduled_pipeline)
        t.start()
        assert started.wait(timeout=2)

        # Second trigger while first holds the lock
        _run_scheduled_pipeline()
        assert calls["n"] == 1

        release.set()
        t.join(timeout=5)

    assert calls["n"] == 1


def test_manual_post_run_still_works_with_scheduler_lifecycle():
    """Regression: POST /run uses execute_graph; scheduler lifecycle must not break it."""
    from api.main import app

    mock_state = {
        "run_id": "run-sched-regression",
        "thread_id": "run_abc123",
        "briefing_final": "ok",
        "delivery_status": "sent",
        "run_duration_seconds": 1.0,
        "tokens_used": 10,
        "estimated_cost_usd": 0.01,
        "findings_retrieved": 1,
        "findings_dropped_freshness": 0,
        "findings_dropped_scope": 0,
        "findings_dropped_dedup": 0,
        "graph_version": "1.0",
        "error": None,
    }

    with patch("api.routes.execute_graph") as mock_execute:
        mock_execute.return_value = GraphRunResult(
            state=mock_state,
            checkpoint_next=(),
        )
        with TestClient(app) as client:
            # Lifespan starts scheduler (enabled in this module via fixture)
            assert is_running() or not sched.scheduler_enabled()
            response = client.post("/run", json={"run_type": "manual"})

    assert response.status_code == 200
    body = response.json()
    assert body["run_id"] == "run-sched-regression"
    assert body["status"] == "completed"
    mock_execute.assert_called_once()


def test_disabled_env_skips_start(monkeypatch):
    monkeypatch.setenv("SIGNAL_SCHEDULER_ENABLED", "0")
    assert start_scheduler() is None
    assert not is_running()
