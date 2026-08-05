## Active Slice
Slice 5 — Production Scheduler & Config Integration (SIG-032)

## Active Tasks
- SIG-032 Production Scheduler & User Configuration Integration — COMPLETE (pending Reviewer)

## Files In Scope This Slice
- api/scheduler.py
- api/routes.py (stage_filter normalize only)
- frontend/index.html (Configuration screen controls)
- tests/test_scheduler.py
- tests/test_config_memory_api.py

## Slice Exit Criteria
- Multi-user scheduled runs via execute_pipeline()
- Per-user daily/weekly schedule_freq respected
- Config UI: editable schedule + stage filter (Seed/Series A/Series B)
- One user failure does not stop remaining users
- Existing Trigger Run / graph unchanged

## Last Updated
2026-08-05

## Blocker / Human Action Required
- None for SIG-032. Auth JWT secret (SUPABASE_JWT_SECRET) still needed for protected routes in live env.
