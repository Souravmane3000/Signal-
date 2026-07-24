"""Disable APScheduler during API/unit test collection (SIG-023-deploy)."""

from __future__ import annotations

import os

# Must run before api.main lifespan / TestClient imports start the scheduler.
os.environ.setdefault("SIGNAL_SCHEDULER_ENABLED", "0")
