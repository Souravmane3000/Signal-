# CURSOR_RULES.md

Project: Signal Status: Mandatory Rules Applies To: Builder Agent, Reviewer Agent (Bugbot), Composer, Background Agents, Subagents, and any future AI coding tool used on this project

# 1\. PRIMARY OBJECTIVE

Signal is an autonomous startup intelligence agent.

The primary objective is:

Deliver relevant and fresh Indian startup intelligence.

All implementation decisions must optimize for:

- Relevance
- Freshness
- Reliability
- Cost efficiency

Do not optimize for architectural elegance at the expense of these goals.

# 2\. SOURCE OF TRUTH HIERARCHY

If documents conflict, use this priority order:

- DECISIONS.md
- ARCHITECTURE.md
- BUILD_SPEC.md
- PRD.md
- TASKS.md

Never invent a new architecture when an answer already exists in a higher-priority document.

# 3\. AGENT SYSTEM

Two persistent agents exist on this project. No third standing agent.

**Builder Agent** Implements, tests, and documents all Tier 1 and Tier 2 tasks (see Section 5).

- Tier 1 mode: batch execution, may run in background, may spawn subagents (Section 24).
- Tier 2 mode: single task at a time, interactive/foreground, halts after implementation and waits for human validation against /validation (Section 19) before continuing to the next Tier 2 task.

**Reviewer Agent (Bugbot)** Runs automatically on every PR, before human merge. Read-only. Flags bugs, security issues, edge cases. Never blocks or approves a merge unilaterally - the human makes the final call.

**Architect Role - not a persistent Cursor agent** Invoked on demand, outside Cursor, via an external chat LLM (not metered against the Cursor build budget). Used for: major redesign, new subsystem, new data model, or any failure escalated per Section 20. Every Architect session that changes a decision produces a DECISIONS.md entry and a re-spec for Builder Agent to implement. Estimated frequency: a small fraction of total project time, not continuous.

# 4\. MODEL STRATEGY _(revised - model-agnostic)_

This section defines behavior by capability tier, not by naming a specific model. Model lineups change; the cost-discipline behavior below should not need rewriting when they do.

- Tier 1 tasks: default to the fastest/cheapest available model capable of mechanical implementation work.
- Tier 2 tasks: default to a mid-tier reasoning model - deliberately not the cheapest available, and not the most expensive available either.
- The most expensive/premium model tier is never used by default, under any circumstance.
- If a Tier 2 task or an escalated failure genuinely requires more reasoning power than the mid-tier default provides, the next step is Architect Role escalation (Section 3) - not reaching for a more expensive in-Cursor model first.
- The premium tier is reserved only as a last resort, and only if Architect Role escalation has already failed to resolve the issue.

# 5\. TASK TIERING

Every task in TASKS.md must carry one of these tier labels.

**Tier 1 - Deterministic implementation.** Correctness is verifiable by a test or assertion. Owned by Builder Agent in batch mode. No approval needed beyond the standard PR review.

**Tier 2 - Judgment-based implementation.** Correctness requires comparing real output against the /validation dataset. Owned by Builder Agent in interactive mode. Requires human validation before merge.

**Tier 3 - Human-only.** Never enters an agent's task queue, regardless of how simple it looks. See Section 7.

Classification rule: if "correct" can be defined by a test assertion → Tier 1. If "correct" requires looking at real output and judging quality against /validation → Tier 2. If it touches credentials, infra, or money → Tier 3, full stop, regardless of apparent simplicity.

# 6\. ARCHITECTURE FREEZE RULES

The following files are architecture documents.

- PRD.md
- BUILD_SPEC.md
- ARCHITECTURE.md

Agents may read them.

Agents may NOT modify them.

If implementation reveals a problem:

- Stop
- Create a proposal
- Explain:
  - Problem
  - Root cause
  - Suggested solution
  - Files affected
- Wait for human approval

Do not self-modify architecture.

# 7\. HUMAN-ONLY OPERATIONS (TIER 3)

Immediately stop and request human approval if work involves:

- OAuth setup
- API key creation
- Secret management
- Environment variables
- Supabase project creation
- Vercel configuration
- Northflank configuration
- Production deployment
- Production database changes
- Billing settings
- Domain configuration
- Email account configuration

Never guess infrastructure settings. These operations bypass the Failure Escalation classes in Section 20 entirely - zero retries, human immediately. (See Class C, Section 20.)

# 8\. TASK EXECUTION RULES

A task must satisfy all requirements:

- Maximum 1 concern
- Maximum 1 feature
- Maximum 3 files modified
- Maximum 90 minutes of human-equivalent effort

If a task exceeds these limits: stop and split it. Do not continue.

Operating mode follows the task's tier (Section 5): Tier 1 tasks may run in background/batch; Tier 2 tasks always run interactively, one at a time, never batched.

# 9\. CONTEXT LOADING RULES

Always read:

- CURRENT_PHASE.md
- TASKS.md

Read only when relevant:

- ARCHITECTURE.md
- BUILD_SPEC.md
- PRD.md
- DECISIONS.md
- AGENT_HANDOFF.md - read at the start of any new session to verify agent role, handoff protocol, and stop conditions.

Never load large documents unnecessarily. Minimize context size. Token efficiency is mandatory. CURRENT_PHASE.md reflects the current vertical slice (Section 23) - it is the primary context source for routine work, not the full document set.

# 10\. SIGNAL NODE ORDER RULES

The following node order is mandatory.

Config Loader → Search Planner → Research Nodes → Reducer → Freshness Validation → Entity Extraction → Scope Filter → Source Trust Scoring → Hybrid Dedup → Synthesis → HITL → Episodic Memory Writer → Delivery → Metrics Writer → Feedback Collector → Procedural Memory Updater

Do not reorder nodes. Do not bypass nodes. Do not merge nodes.

# 11\. DATA QUALITY RULES

Freshness Validation always executes before Entity Extraction.

Scope Filter always executes before Source Trust Scoring.

Episodic Memory Writer always executes before Delivery.

These rules are non-negotiable.

# 12\. FILTERING RULES

Drop only on confirmed violations. Never drop because a field is null.

Allowed reasons to drop:

- non-Indian location
- funding amount outside range
- stale article older than threshold

Not allowed as reasons to drop:

- location unknown
- funding amount unknown
- stage unknown

Ambiguous data is retained.

# 13\. JUDGMENT & LLM USAGE RULES

Three areas carry judgment risk on this project:

- Entity Extraction (LLM - GPT-4o mini)
- Synthesis (LLM - GPT-4o)
- Hybrid Dedup's embedding-similarity threshold behavior (not an LLM call, but a judgment-tuned parameter - the 0.85 cosine threshold)

All three require human validation per Section 19 before being considered correct.

Do not introduce additional LLM calls beyond Entity Extraction and Synthesis without an approved DECISIONS.md entry.

Prefer deterministic code wherever a deterministic approach is viable. Never replace a deterministic node with LLM reasoning to "simplify" it.

# 14\. SIGNAL RUNTIME COST CONTROL RULES

This section governs the cost of running Signal in production. It is separate from Section 15, which governs the cost of building Signal in Cursor.

Respect:

- MAX_FINDINGS_PER_RUN
- MAX_RUN_COST_USD

Never bypass these limits.

If a limit is reached:

- Stop processing additional findings
- Log the reason
- Continue run safely

Never remove guardrails.

# 15\. CURSOR BUILD BUDGET RULES

This section governs the cost of building Signal in Cursor. It is separate from Section 14, which governs Signal's own production runtime cost.

- Total build budget: \$15 implementation + \$5 reserved for debugging. The \$5 reserve is not spent during normal building - it exists for the unplanned hard bug.
- Budget checkpoint after every vertical slice (Section 23), not just at project end.
- Cost priority: Tier 1 work (cheap model, high volume) should consume the majority of spend. Tier 2 work (mid-tier model, lower volume, higher cost-per-task) is a smaller, deliberate portion.
- If projected total spend exceeds \$15 before all slices are complete: pause, reprioritize remaining slices, or downgrade model tier for remaining Tier 1 work. This is a human decision - never made automatically by an agent.

# 16\. STATE SCHEMA RULES _(revised - reducer protection added)_

SignalState is a system contract.

Agents may not:

- rename fields
- remove fields
- duplicate fields
- change reducer behavior

without approval. Reducer behavior is explicitly protected - raw_findings's operator.add reducer is what allows parallel research nodes to append instead of overwrite each other. A silent change here breaks Send API parallelism with no obvious error, just quietly missing data.

Any SignalState modification requires:

- justification
- migration plan
- affected nodes list

# 17\. DATABASE SAFETY RULES

Never:

- DROP tables
- DROP columns
- TRUNCATE tables
- Disable RLS
- Delete data without approval

All schema changes must be reversible. All migrations must be timestamped. All migrations require an entry in DECISIONS.md.

# 18\. TESTING RULES

Every implementation task must pass:

- Imports work
- Type checks pass
- Existing tests pass
- New tests added when behavior changes

Every PR additionally passes through Reviewer Agent (Bugbot, Section 3) before human merge.

Never mark a task complete without verification.

# 19\. VALIDATION RULES

For deterministic (Tier 1) nodes: agent validates. Examples - Reducer, Freshness Validation, Scope Filter, Metrics Writer.

For judgment (Tier 2) nodes: human validates. Examples - Entity Extraction, Dedup threshold behavior, Synthesis quality.

Human validation means comparing real output against the fixed /validation dataset (20 companies, 20 funding events, 20 duplicate cases, 20 false-positive cases) and the accuracy thresholds defined in EVAL.md. "Looks right" is not an acceptance criterion - a number against the fixed dataset is.

The /validation dataset is frozen once authored. It does not get modified mid-build to make a result look better.

Agents may not self-certify judgment quality.

# 20\. FAILURE ESCALATION RULES _(revised - Class A/B/C structure)_

**Class A - Build failures, type errors, import errors.** Agent retries allowed. If a Class A failure persists past 2 attempts, it is not actually a Class A issue - reclassify as Class B and escalate accordingly. A mechanical error that doesn't resolve quickly is usually a logic problem wearing a mechanical costume.

**Class B - Logic failures, incorrect outputs, validation failures.** Maximum 2 attempts. On the 2nd identical failure: stop, escalate to the Architect Role (Section 3) before any further attempt. Do not attempt a 3rd identical retry inside Cursor under any circumstance.

**Class C - Infrastructure, OAuth, secrets, deployments, production database.** Immediate human escalation. Zero retries. See Section 7 (Human-Only Operations) and Section 17 (Database Safety) - Class C is governed by those sections directly; this classification does not duplicate their content, it points to it.

When escalating (Class B or C): always provide what was attempted, root cause (if known), and recommended next step.

# 21\. YC NODE RULE _(revised - availability clause added)_

YC API Node must preserve:

- Directory scrape
- Tavily fallback restricted to ycombinator.com
- Graceful degradation - log failure, continue run

Do not remove this fallback chain.

Do not make YC availability a requirement for successful runs. This guards specifically against a future "cleanup refactor" adding a hard dependency on YC data succeeding - which would invert the resilience design this node exists for.

# 22\. MEMORY RULES

Episodic memory is the source of dedup truth.

Procedural memory is updated deterministically.

No LLM may rewrite procedural memory.

Minimum 5 feedback signals required before procedural memory updates.

# 23\. VERTICAL SLICE & PHASE TRACKING RULES _(revised - explicit slice-discipline rule added)_

Signal is built and executed slice by slice - for example, Slice 1: research nodes → deterministic filters → dedup → synthesis/output, end to end; Slice 2: scoring; Slice 3: email digest - rather than strictly phase-by-phase.

A vertical slice must:

- Produce a testable end-to-end capability
- Cross all required layers (research nodes → deterministic filters → LLM processing → output/delivery)
- Be independently verifiable

CURRENT_PHASE.md tracks the current slice: scope, blockers, files in scope, acceptance criteria for every task in the slice, and the slice's exit criteria.

Builder Agent may not advance to the next slice until the current slice's exit criteria - not just the last task's acceptance criteria - are confirmed passing.

**Agents must complete the current slice before beginning the next.** Do not begin work on a future slice because its dependencies appear obvious. Partial future implementation is prohibited - this includes scaffolding, stub functions, or "while I'm here" additions that belong to a later slice.

CURRENT_PHASE.md is regenerated by the human at the start of each slice.

# 24\. SUBAGENT RULES

Subagents may be spawned by Builder Agent only, and only for Tier 1 work.

Each subagent is scoped to one node-task within the current slice, with file access narrower than the parent task.

Subagents inherit every rule in this document - they do not get a separate or relaxed rule set.

Subagents are never spawned for Tier 2 or Tier 3 work.

# 25\. DOCUMENT UPDATE RULES

Agents may update:

- TASKS.md
- CURRENT_PHASE.md

Agents may propose updates to:

- DECISIONS.md

Agents may not modify, without approval:

- PRD.md
- BUILD_SPEC.md
- ARCHITECTURE.md

# 26\. DEFINITION OF DONE _(revised - Tier 2 line and status phrasing added)_

A task is complete only when:

- Acceptance criteria passed
- Tests passed (Section 18)
- Reviewer Agent has reviewed the PR (Section 3, 18)
- No architecture rules violated
- No guardrails bypassed
- Human validation completed for Tier 2 tasks (Section 19) - does not apply to Tier 1
- CURRENT_PHASE.md updated
- TASKS.md updated

If any item is incomplete, task status remains **In Progress.**

A slice is complete only when all of its tasks meet the above **and** the slice's exit criteria (Section 23) are confirmed passing.

# 27\. DEFAULT BEHAVIOR

When uncertain:

Do not guess. Do not invent. Do not redesign.

Stop. Explain uncertainty. Request clarification.