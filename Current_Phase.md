## Active Slice
App responsiveness — Sign In to tabs (Slices 1–4)

## Active Tasks
- Slice 1 Instant shell + SWR tabs — COMPLETE
- Slice 2 Cheap JWT + cheap GET /agent/status — COMPLETE
- Slice 3 Landing/first-paint assets — COMPLETE
- Slice 4 Briefings count query, indexes, PUT /config — COMPLETE

## Files In Scope This Slice
- frontend/index.html
- frontend/style.css (unchanged landing CSS)
- frontend/tailwind.config.js
- frontend/tw-input.css
- frontend/tailwind.built.css
- api/auth.py
- api/main.py
- api/routes.py
- database/schema.sql (additive indexes only)
- tests/test_api.py
- tests/test_auth.py
- tests/test_config_memory_api.py

## Slice Exit Criteria
- Sign In releases spinner on token; dashboard paints from /briefings without blocking on markdown
- Tab switches paint cached state then revalidate (no empty wipe)
- JWT JWKS client is process-cached; GET /agent/status skips graph.get_state on live/completed cheap paths
- Tailwind Play CDN replaced by committed built CSS
- GET /briefings uses grouped item counts; PUT /config returns RETURNING row

## Last Updated
2026-09-07

## Blocker / Human Action Required
- Apply additive indexes from database/schema.sql on the live database if not using schema bootstrap
- Restore frontend/config.js Northflank URL before any production ship
- SIG-033 remains COMPLETE pending Reviewer (separate from this campaign)
