"""SIG-023-deploy / SIG-032 — APScheduler multi-user schedule integration tests."""

from __future__ import annotations

import threading
from datetime import datetime, timezone
from unittest.mock import MagicMock, patch

import pytest
from fastapi.testclient import TestClient
from tests.conftest import attach_default_auth

from agent.graph import GraphRunResult
from api import scheduler as sched
from api.scheduler import (
    JOB_ID,
    _run_scheduled_pipeline,
    get_scheduler,
    is_running,
    is_user_due,
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


def test_scheduler_starts_once_and_registers_daily_job():
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


def test_scheduled_job_callable_is_shared_pipeline():
    start_scheduler()
    job = get_scheduler().get_job(JOB_ID)
    assert job is not None
    assert job.func is _run_scheduled_pipeline
    trigger = job.trigger
    assert hasattr(trigger, "fields") or trigger.__class__.__name__ == "CronTrigger"


def test_daily_schedule_is_due_every_day():
    monday = datetime(2026, 8, 3, 9, 0, tzinfo=timezone.utc)  # Monday
    tuesday = datetime(2026, 8, 4, 9, 0, tzinfo=timezone.utc)
    assert is_user_due("daily", monday) is True
    assert is_user_due("daily", tuesday) is True
    assert is_user_due("Daily", tuesday) is True


def test_weekly_schedule_is_due_on_monday_only():
    monday = datetime(2026, 8, 3, 9, 0, tzinfo=timezone.utc)
    tuesday = datetime(2026, 8, 4, 9, 0, tzinfo=timezone.utc)
    assert is_user_due("weekly", monday) is True
    assert is_user_due("weekly", tuesday) is False
    assert is_user_due(None, monday) is True  # default weekly


def test_scheduled_execution_calls_execute_pipeline_not_duplicate_graph():
    users = [
        {
            "user_id": "user-aaa",
            "schedule_freq": "daily",
            "delivery_email": "a@example.com",
            "stage_filter": ["Seed"],
        }
    ]
    with patch("api.routes.execute_pipeline") as mock_pipeline, patch(
        "api.scheduler._load_active_user_configs", return_value=users
    ), patch("api.scheduler.is_user_due", return_value=True):
        mock_pipeline.return_value = MagicMock()
        _run_scheduled_pipeline()
        mock_pipeline.assert_called_once()
        req = mock_pipeline.call_args.args[0]
        assert req.run_type == "scheduled"
        assert req.user_id == "user-aaa"


def test_multi_user_iteration_calls_pipeline_per_due_user():
    users = [
        {
            "user_id": "user-1",
            "schedule_freq": "daily",
            "delivery_email": "one@example.com",
            "stage_filter": ["Seed"],
        },
        {
            "user_id": "user-2",
            "schedule_freq": "weekly",
            "delivery_email": "two@example.com",
            "stage_filter": ["Series A"],
        },
        {
            "user_id": "user-3",
            "schedule_freq": "weekly",
            "delivery_email": "three@example.com",
            "stage_filter": ["Series B"],
        },
    ]

    # Only daily users are due in this scenario.
    with patch("api.routes.execute_pipeline") as mock_pipeline, patch(
        "api.scheduler._load_active_user_configs", return_value=users
    ), patch(
        "api.scheduler.is_user_due",
        side_effect=lambda freq, when=None: freq == "daily",
    ):
        mock_pipeline.return_value = MagicMock()
        _run_scheduled_pipeline()

    assert mock_pipeline.call_count == 1
    assert mock_pipeline.call_args.args[0].user_id == "user-1"


def test_multi_user_all_due_runs_each_once():
    users = [
        {
            "user_id": "u1",
            "schedule_freq": "daily",
            "delivery_email": "a@x.com",
            "stage_filter": ["Seed"],
        },
        {
            "user_id": "u2",
            "schedule_freq": "weekly",
            "delivery_email": "b@x.com",
            "stage_filter": ["Series A"],
        },
    ]
    with patch("api.routes.execute_pipeline") as mock_pipeline, patch(
        "api.scheduler._load_active_user_configs", return_value=users
    ), patch("api.scheduler.is_user_due", return_value=True):
        mock_pipeline.return_value = MagicMock()
        _run_scheduled_pipeline()

    assert mock_pipeline.call_count == 2
    ids = [c.args[0].user_id for c in mock_pipeline.call_args_list]
    assert ids == ["u1", "u2"]
    assert all(c.args[0].run_type == "scheduled" for c in mock_pipeline.call_args_list)


def test_one_user_failure_does_not_stop_remaining_users():
    users = [
        {
            "user_id": "fail-user",
            "schedule_freq": "daily",
            "delivery_email": "fail@x.com",
            "stage_filter": ["Seed"],
        },
        {
            "user_id": "ok-user",
            "schedule_freq": "daily",
            "delivery_email": "ok@x.com",
            "stage_filter": ["Seed"],
        },
    ]

    def side_effect(req):
        if req.user_id == "fail-user":
            raise RuntimeError("boom")
        return MagicMock()

    with patch("api.routes.execute_pipeline", side_effect=side_effect) as mock_pipeline, patch(
        "api.scheduler._load_active_user_configs", return_value=users
    ), patch("api.scheduler.is_user_due", return_value=True):
        _run_scheduled_pipeline()  # must not raise

    assert mock_pipeline.call_count == 2
    assert mock_pipeline.call_args_list[1].args[0].user_id == "ok-user"


def test_failure_recovery_keeps_scheduler_alive():
    start_scheduler()
    assert is_running()

    with patch(
        "api.scheduler._load_active_user_configs",
        side_effect=RuntimeError("db boom"),
    ):
        _run_scheduled_pipeline()  # must not raise

    assert is_running()
    assert get_scheduler().get_job(JOB_ID) is not None
    assert next_run_time() is not None


def test_overlapping_scheduled_runs_are_skipped():
    started = threading.Event()
    release = threading.Event()
    calls = {"n": 0}

    def slow_load():
        calls["n"] += 1
        started.set()
        release.wait(timeout=5)
        return []

    with patch("api.scheduler._load_active_user_configs", side_effect=slow_load):
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
            attach_default_auth(client)
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
