"""APScheduler weekly trigger for Signal (SIG-023-deploy application layer).

Invokes the same execute_pipeline path as POST /run.
Does not duplicate graph invocation logic.
"""

from __future__ import annotations

import logging
import os
import threading
from typing import Any, Optional

from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.cron import CronTrigger

logger = logging.getLogger(__name__)

JOB_ID = "signal_weekly_pipeline"
# Monday 09:00 UTC — weekly cadence (BUILD_SPEC Session 23 / PRD scheduler).
WEEKLY_CRON = CronTrigger(day_of_week="mon", hour=9, minute=0, timezone="UTC")

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


def _run_scheduled_pipeline() -> None:
    """Job callable: reuse api.routes.execute_pipeline (manual/scheduled single path)."""
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

        execute_pipeline(RunRequest(run_type="scheduled"))
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
                    trigger=WEEKLY_CRON,
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
            trigger=WEEKLY_CRON,
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
