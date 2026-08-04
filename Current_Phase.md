## Active Slice
Slice 5-Auth — Supabase Auth Flow Completion

## Active Tasks
- Auth flow (signup/login/JWT/RLS/guards) — PENDING VALIDATION

## Files In Scope This Slice
- api/main.py
- api/routes.py (and auth modules as needed)
- frontend/index.html
- frontend/config.js
- supabase migrations / RLS policies
- tests/test_auth*.py (and related)

## Slice Exit Criteria
- Signup → JWT → Onboarding (first-time) / Dashboard (returning)
- JWT in memory only; Bearer on all protected calls
- FastAPI JWT middleware; 401 without valid token
- RLS audited on all custom tables
- Auth + RLS tests pass

## Last Updated
2026-08-04

## Blocker / Human Action Required
- Add `SUPABASE_JWT_SECRET` to `.env` (Supabase Dashboard → Project Settings → API → JWT Secret). Without it, protected routes fail closed (500), never open.
