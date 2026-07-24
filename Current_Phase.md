# CURRENT_PHASE.md

Project: Signal

Status: Active Execution Context

Purpose:

Provide the minimum context required for Builder Agent execution.

This file changes frequently.

This file is the primary execution context for Builder Agent.

# CURRENT SLICE

Name:

Vertical Slice 5 — API, Frontend & Scheduler

Status:

IN_PROGRESS

Goal:

Full system accessible via browser. User triggers runs, reviews briefings, approves/rejects from UI. Weekly scheduler runs autonomously.

**Slice exit criteria:**
- `uvicorn api.main:app` starts without error
- All 15 API endpoints in BUILD_SPEC.md Section 18 return 200 on valid requests
- `POST /agent/run` triggers real graph invoke
- `POST /briefings/{id}/approve` resumes interrupted graph on Approve/Edit branch
- `POST /briefings/{id}/reject` resumes on Reject branch — no episodic memory written (DEC-004)
- Frontend renders in browser: all 8 screens per PRD Section 21
- APScheduler triggers weekly run autonomously — confirmed by waiting or mocking time
- After ≥5 feedback signals: procedural memory updates, next run reflects changes (DEC-007)
-  "Frontend and backend share a stable runtime contract (thread_id, run_id, status lifecycle) suitable for future scheduler integration."

# CURRENT TASK


### SIG-023 — Procedural Memory Updater
**Tier:** 1 | **Owner:** Builder Agent | **Phase:** 3 | **Status:** TODO
**Depends on:** SIG-022, SIG-P2-API
**Spec ref:** BUILD_SPEC.md Section 17.6

**Files in Scope:**
- `agent/nodes/procedural_memory_updater.py`

**Critical — DEC-007 compliance:** No LLM may rewrite procedural memory. Logic is deterministic aggregation only. Source weights floored at 0.3. Minimum 5 feedback signals before any update fires.

**Acceptance criteria:**
- Imports `fetch_all_feedback_for_user` from `agent.memory.feedback_store` — no local redefinition
- Returns `{}` immediately if `len(all_feedback) < 5` — no update fires
- `high_signal_categories`: categories with >60% useful feedback ratio
- `low_signal_categories`: categories with >60% not_relevant feedback ratio
- `source_weights`: `max(0.3, ratio)` per source — no weight ever drops below 0.3 (DEC-007)
- `store.put(namespace=("user", user_id, "procedural"), key="preferences", value=updated)` called
- After ≥5 signals: `store.get` returns updated procedural memory with changed values
- Next `run_graph()` call: `search_planner` reads updated `source_weights` from state — confirmed in run output

**Stop conditions — escalate to human immediately if:**
- Any LLM call detected in this node — hard DEC-007 violation, stop immediately
- Source weight drops below 0.3 — hard DEC-007 violation
- Update fires with fewer than 5 feedback signals — threshold logic broken
- `fetch_all_feedback_for_user` import fails (SIG-022 not complete)

---


# BUDGET GATE

Before advancing to the next slice:

Human must review:

- Cursor usage
- Remaining budget
- Token consumption trend

Builder Agent may not advance across slices automatically.

# ARCHITECTURE CONSTRAINTS

Do not:


- Modify architecture documents
- Modify decision records
- Introduce new architecture patterns

Architecture is frozen.

Implementation only.

# FAILURE RULES

If task cannot be completed:

- Stop
- Explain blocker
- Reference affected task
- Reference dependency if applicable
- Suggest next action

Do not redesign architecture.

Do not invent requirements.

Do not bypass task boundaries.

# REVIEW PROCESS

After implementation:

- Builder Agent stops
- Human reviews output
- Human validates acceptance criteria
- Builder Agent updates TASKS.md task status to DONE
- Human regenerates CURRENT_PHASE.md for the next task

Builder Agent may not self-advance.

Builder Agent may not mark future tasks complete.


# NEXT TASK

Upon successful completion:

Task:

SIG-023-deploy

Title:

Northflank Deployment


Builder Agent must wait for human approval before work begins.

# HUMAN NOTES

- Entity Extraction OpenAI client wrapped with langsmith.wrappers.wrap_openai to enable LangSmith LLM child spans and token/cost observability. No architecture or extraction logic changed.

- The /config endpoint acceptance criterion is validated during the FastAPI implementation, not during the Config Loader upgrade.

# EXECUTION TIMESTAMP

Last Updated:


2026-07-22 17:38

Updated By:

Human