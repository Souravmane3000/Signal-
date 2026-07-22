# CURRENT_PHASE.md

Project: Signal

Status: Active Execution Context

Purpose:

Provide the minimum context required for Builder Agent execution.

This file changes frequently.

This file is the primary execution context for Builder Agent.

# CURRENT SLICE

Name:

Vertical Slice 4 — Phase 2 Infrastructure + HITL

Status:

IN_PROGRESS

Goal:

PostgresSaver live, HITL interrupt working, conditional routing correct per DEC-004, delivery working, all memory and metrics writing to Supabase.

**Slice exit criteria:**
- `MemorySaver` fully replaced by `PostgresSaver` — graph state persists across process restarts
- `graph.invoke` pauses at `hitl_node` — confirmed via LangSmith interrupt span
- Approve path: `episodic_memory_writer` executes → delivery proceeds → episode in PostgresStore
- Reject path: `discard_and_log` executes → `episodic_memory_writer` does NOT execute → no episode in PostgresStore (DEC-004, EVAL.md Section 13)
- `run_metrics_writer` executes on BOTH approve and reject paths
- Approved briefing arrives in `delivery_email` inbox
- `agent_run_metrics` table has one row per run with `graph_version` and `source_health` as separate columns
- Embedding dedup (SIG-014B) catches fuzzy duplicate that stages 0–2 missed



# CURRENT TASK


### SIG-022 — Feedback Collector
**Tier:** 1 | **Owner:** Builder Agent | **Phase:** 2 | **Status:** TODO
**Depends on:** SIG-P2-001, SIG-020A
**Spec ref:** BUILD_SPEC.md Section 18 (feedback endpoint), PRD Section 7

**Files in Scope:**
- `agent/nodes/feedback_collector.py`
- `agent/memory/feedback_store.py`

**Acceptance criteria:**
- `agent/memory/feedback_store.py` created with `fetch_all_feedback_for_user(user_id: str) -> list[dict]` function
- `fetch_all_feedback_for_user` queries `user_feedback` table filtered by `user_id`, returns all rows as list of dicts
- `user_feedback` table accepts inserts with: `user_id`, `briefing_item_id`, `category`, `source_name`, `feedback` (`"useful"` or `"not_relevant"`), `reason`
- Direct Supabase INSERT from Python test script works
- `SIG-023` imports `fetch_all_feedback_for_user` from `agent.memory.feedback_store` — no duplication

**Stop conditions — escalate to human immediately if:**
- `user_feedback` table missing from Supabase (SIG-P2-001 not complete)
- `fetch_all_feedback_for_user` returns non-list type
- Supabase INSERT raises constraint violation — check schema column types

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

SIG-P2-API

Title:

FastAPI Backend


Builder Agent must wait for human approval before work begins.

# HUMAN NOTES

- Entity Extraction OpenAI client wrapped with langsmith.wrappers.wrap_openai to enable LangSmith LLM child spans and token/cost observability. No architecture or extraction logic changed.

- The /config endpoint acceptance criterion is validated during the FastAPI implementation, not during the Config Loader upgrade.

# EXECUTION TIMESTAMP

Last Updated:


2026-07-22 11:41

Updated By:

Human