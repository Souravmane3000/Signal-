"""APScheduler trigger for Signal scheduled runs.

Invokes the same execute_pipeline path as POST /run, once per eligible user.
Does not duplicate graph invocation logic.
"""

from __future__ import annotations

import logging
import os
import threading
from datetime import datetime, timezone
from typing import Any, Optional

from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.cron import CronTrigger

logger = logging.getLogger(__name__)

JOB_ID = "signal_scheduled_pipeline"
# Daily 09:00 UTC tick — per-user schedule_freq decides daily vs weekly eligibility.
DAILY_CRON = CronTrigger(hour=9, minute=0, timezone="UTC")
# Backward-compatible alias for older imports/tests.
WEEKLY_CRON = DAILY_CRON

_scheduler: Optional[BackgroundScheduler] = None
_run_lock = threading.Lock()
_execution_in_progress = False
_lock = threading.Lock()  # guards scheduler create/start/stop


def scheduler_enabled() -> bool:
    """Allow tests to disable auto-start without changing production default."""
    return os.getenv("SIGNAL_SCHEDULER_ENABLED", "1").strip().lower() not in {
        "0",
        "false",
        "no",
        "off",
    }


def get_scheduler() -> Optional[BackgroundScheduler]:
    return _scheduler


def is_running() -> bool:
    return _scheduler is not None and _scheduler.running


def next_run_time() -> Optional[Any]:
    if _scheduler is None:
        return None
    job = _scheduler.get_job(JOB_ID)
    if job is None:
        return None
    return job.next_run_time


def _normalize_schedule_freq(value: Any) -> str:
    freq = str(value or "weekly").strip().lower()
    if freq == "daily":
        return "daily"
    return "weekly"


def is_user_due(schedule_freq: Any, when: Optional[datetime] = None) -> bool:
    """Return True when this user's cadence should fire at `when` (UTC)."""
    now = when or datetime.now(timezone.utc)
    if now.tzinfo is None:
        now = now.replace(tzinfo=timezone.utc)
    else:
        now = now.astimezone(timezone.utc)

    freq = _normalize_schedule_freq(schedule_freq)
    if freq == "daily":
        return True
    # Weekly: Monday 09:00 UTC tick only.
    return now.weekday() == 0


def _load_active_user_configs() -> list[dict[str, Any]]:
    """Load every user_configs row that can receive scheduled delivery."""
    from agent.graph import pool

    with pool.connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT user_id, schedule_freq, delivery_email, stage_filter
                FROM user_configs
                WHERE delivery_email IS NOT NULL
                  AND TRIM(delivery_email) <> ''
                ORDER BY updated_at DESC NULLS LAST
                """
            )
            rows = cur.fetchall() or []

    results: list[dict[str, Any]] = []
    seen: set[str] = set()
    for row in rows:
        data = dict(row) if not isinstance(row, dict) else row
        user_id = str(data.get("user_id") or "").strip()
        if not user_id or user_id in seen:
            continue
        email = str(data.get("delivery_email") or "").strip()
        if not email:
            continue
        seen.add(user_id)
        results.append(
            {
                "user_id": user_id,
                "schedule_freq": _normalize_schedule_freq(data.get("schedule_freq")),
                "delivery_email": email,
                "stage_filter": list(data.get("stage_filter") or []),
            }
        )
    return results


def _run_scheduled_pipeline() -> None:
    """Job callable: reuse api.routes.execute_pipeline once per eligible user."""
    global _execution_in_progress

    if not _run_lock.acquire(blocking=False):
        logger.warning(
            "Scheduled execution skipped: previous scheduled run still in progress"
        )
        return

    _execution_in_progress = True
    try:
        logger.info("Scheduled execution started")
        from api.routes import execute_pipeline
        from api.schemas import RunRequest

        now = datetime.now(timezone.utc)
        try:
            users = _load_active_user_configs()
        except Exception:
            logger.exception("Failed to load user_configs for scheduled run")
            return

        if not users:
            logger.info("Scheduled execution: no configured users")
            return

        due_users = [u for u in users if is_user_due(u.get("schedule_freq"), now)]
        logger.info(
            "Scheduled execution: %s configured user(s), %s due",
            len(users),
            len(due_users),
        )

        for user in due_users:
            user_id = user["user_id"]
            try:
                logger.info(
                    "Scheduled pipeline for user_id=%s schedule_freq=%s",
                    user_id,
                    user.get("schedule_freq"),
                )
                execute_pipeline(
                    RunRequest(user_id=user_id, run_type="scheduled")
                )
            except Exception:
                # One user's failure must not stop remaining users.
                logger.exception(
                    "Scheduled execution failed for user_id=%s", user_id
                )

        logger.info("Scheduled execution finished")
    except Exception:
        logger.exception("Scheduled execution failed")
        # Do not re-raise — scheduler must keep running (failure recovery).
    finally:
        _execution_in_progress = False
        _run_lock.release()


def execution_in_progress() -> bool:
    return _execution_in_progress


def start_scheduler() -> Optional[BackgroundScheduler]:
    """Create and start a single BackgroundScheduler; idempotent."""
    global _scheduler

    if not scheduler_enabled():
        logger.info("Scheduler disabled via SIGNAL_SCHEDULER_ENABLED")
        return None

    with _lock:
        if _scheduler is not None and _scheduler.running:
            if _scheduler.get_job(JOB_ID) is None:
                _scheduler.add_job(
                    _run_scheduled_pipeline,
                    trigger=DAILY_CRON,
                    id=JOB_ID,
                    replace_existing=True,
                    max_instances=1,
                    coalesce=True,
                )
            logger.info(
                "Scheduler already running (idempotent start); next_run=%s",
                next_run_time(),
            )
            return _scheduler

        if _scheduler is None:
            _scheduler = BackgroundScheduler(timezone="UTC")

        _scheduler.add_job(
            _run_scheduled_pipeline,
            trigger=DAILY_CRON,
            id=JOB_ID,
            replace_existing=True,
            max_instances=1,
            coalesce=True,
        )

        if not _scheduler.running:
            _scheduler.start()

        logger.info(
            "Scheduler started; job=%s next_run=%s",
            JOB_ID,
            next_run_time(),
        )
        return _scheduler


def stop_scheduler(wait: bool = False) -> None:
    """Stop scheduler cleanly; safe to call multiple times."""
    global _scheduler

    with _lock:
        if _scheduler is None:
            return
        if _scheduler.running:
            _scheduler.shutdown(wait=wait)
            logger.info("Scheduler stopped")
        _scheduler = None


def job_count() -> int:
    if _scheduler is None:
        return 0
    return len(_scheduler.get_jobs())
