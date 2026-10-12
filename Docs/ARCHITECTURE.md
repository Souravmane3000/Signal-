# Signal - ARCHITECTURE.md

**Status:** Locked for build. Derived from PRD v1.2 (spikes validated) and Build Spec v3. This document is read-only for agents - it describes what exists and why, it is not where decisions get made. New architectural decisions belong in DECISIONS.md, not as edits here.

## 1\. System Summary

Signal is a LangGraph agent that runs on a schedule, researches the Indian startup/funding ecosystem across four sources, filters and deduplicates findings against its own memory, synthesizes a weekly briefing, pauses for human review, delivers via Gmail, and updates its own search preferences from feedback. It is one continuously-running graph, not a request/response chatbot - the architecture exists to serve one requirement above all others: **data coming in must be relevant and fresh.**

Three deterministic filter nodes (Freshness, Scope, Source Trust) sit between the LLM nodes specifically to keep cost and noise out of the expensive synthesis step. This shapes everything below.

## 2\. Node Graph (data flow, in execution order)

Trigger (APScheduler / manual POST /agent/run)  
│  
▼  
Config Loader - reads user_config + all memory namespaces from Store  
│  
▼  
Search Planner - deterministic (P1) → reads procedural memory (P2+)  
│ builds query_plan{tavily, yc, hn, rss}  
│ every Tavily query MUST carry include_domains  
│  
├──────────────┬──────────────┬──────────────┐ (sequential in P1, Send API parallel in P2+)  
▼ ▼ ▼ ▼  
Tavily Search YC API Node HN Algolia Google News RSS  
(include_domains (directory Node Node  
required) scrape, Tavily (feedparser)  
fallback chain)  
│ │ │ │  
└──────────────┴──────────────┴──────────────┘  
│  
▼  
Reducer - operator.add merge checkpoint, pass-through + count only  
│  
▼  
Freshness Validation - deterministic, no LLM. Drops >30 days old (parseable date only).  
Node Undated findings flagged with confidence penalty, never dropped.  
│  
▼  
Entity Extraction - GPT-4o mini, Prompt v3 (91% accuracy, locked).  
Output passes through EntityDataModel (Pydantic) before  
anything downstream touches it. Cost guardrails  
(MAX_FINDINGS_PER_RUN, MAX_RUN_COST_USD) enforced here.  
│  
▼  
Scope Filter Node - deterministic, no LLM. India-only / \$500K-\$50M / Seed-Series B.  
Drop only on explicit violation, never on a null field.  
│  
▼  
Source Trust Scoring - deterministic. Sorts by confidence_score (already computed  
during Entity Extraction) - does not recalculate.  
│  
▼  
Hybrid Dedup - 3 stages, in order:  
(1) pre-filter: company_name_normalized + announced_date exact match  
(2) URL exact match  
(3) normalized title match  
\[P2+ adds stage 4: pgvector cosine similarity ≥0.85\]  
│  
▼  
Synthesis - GPT-4o. Builds briefing_draft + briefing_items\[\].  
Skips the GPT call entirely if new_findings is empty.  
│  
▼  
HITL Interrupt - interrupt(). Graph pauses, persists, resumes on user action.  
│  
┌──────────┴──────────┐  
\[Approve/Edit\] \[Reject\]  
│ │  
▼ ▼  
Episodic Memory Writer Discard + Log  
(BEFORE delivery -  
run persisted even  
if Gmail fails)  
│  
▼  
Delivery - smtplib + Gmail App Password (P2) → Gmail OAuth (P3)  
│  
▼  
Run Metrics Writer - writes agent_run_metrics row (console in P1, DB in P2)  
│  
▼  
Feedback Collector - user rates items, writes to briefing_items  
│  
▼  
Procedural Memory - deterministic aggregation only, ≥5 signals required, no LLM  
Updater  
│  
▼  
\[Idle until next scheduled run\]

**Non-negotiable ordering rules** (these are architecture, not implementation detail - violating them breaks the system's core guarantee):

- Reducer sits directly after the four research nodes and directly before Freshness Validation - this is where Send API parallel results land in P2+.
- Freshness Validation runs before Entity Extraction. Filtering stale content before any LLM call is the entire reason this node exists - skipping the order means paying GPT-4o mini to process content that gets thrown away anyway.
- Scope Filter runs after Entity Extraction (needs extracted fields to filter on) and before Source Trust Scoring (no point scoring something about to be discarded).
- Episodic Memory Writer always runs before Delivery, in every phase, permanently. If Gmail fails, the run must already be persisted. This is the single most important ordering guarantee in the system.

## 3\. Node Inventory (15 nodes)

| **#** | **Node**               | **Type**                            | **Model**                         | **Determinism**                                     |
| ----- | ---------------------- | ----------------------------------- | --------------------------------- | --------------------------------------------------- |
| 1     | Config Loader          | Store read                          | None                              | Deterministic                                       |
| 2     | Search Planner         | Conditional logic                   | None (P1) / GPT-4o mini (P2+)     | Deterministic (P1)                                  |
| 3     | Tavily Search          | Parallel research (Send API in P2+) | None (API call)                   | External I/O                                        |
| 4     | YC API Node            | Parallel research                   | None (scraping + Tavily fallback) | External I/O                                        |
| 5     | HN Algolia Node        | Parallel research                   | None (API call)                   | External I/O                                        |
| 6     | Google News RSS Node   | Parallel research                   | None (feedparser)                 | External I/O                                        |
| 7     | Reducer                | Reducer function (operator.add)     | None                              | Deterministic                                       |
| 8     | Freshness Validation   | Pure Python                         | None                              | Deterministic                                       |
| 9     | Entity Extraction      | LLM structured output               | GPT-4o mini                       | Probabilistic, Pydantic-validated                   |
| 10    | Scope Filter           | Pure Python                         | None                              | Deterministic                                       |
| 11    | Source Trust Scoring   | Deterministic sort                  | None                              | Deterministic                                       |
| 12    | Hybrid Dedup           | Store read + embedding compare      | text-embedding-3-small (P2+)      | Mostly deterministic, P2+ has a probabilistic layer |
| 13    | Synthesis              | LLM generation                      | GPT-4o                            | Probabilistic                                       |
| 14    | Episodic Memory Writer | Store write                         | None                              | Deterministic                                       |
| 15    | Run Metrics Writer     | Store write                         | None                              | Deterministic                                       |

(HITL Interrupt, Delivery, Feedback Collector, and Procedural Memory Updater follow Synthesis and are part of the same graph but sit after the core research→briefing pipeline above; Build Spec Session 10 wires all 15 of the pipeline nodes through Run Metrics Writer as the Week 1 milestone - the remaining four are Week 2.)

**Why this split matters for build sequencing:** 6 of 15 nodes are pure deterministic Python with zero external dependency (Reducer, Freshness, Scope Filter, Source Trust Scoring, the non-embedding layers of Dedup, Episodic Memory Writer/Metrics Writer in P1). These are the cheapest, lowest-risk, most agent-automatable nodes in the system. Only 2 nodes carry real LLM judgment risk (Entity Extraction, Synthesis), and 1 node carries unofficial-API fragility risk (YC API Node) that no amount of prompt engineering fixes - it needs a coded fallback chain, not a smarter model.

## 4\. State Schema (SignalState)

Defined in agent/state.py, locked before any node code per Build Spec Session 1. Every node's inputs/outputs derive from this - it is the contract between all 15 nodes.

Key structural decisions baked into the schema:

- raw_findings: Annotated\[list\[RawFinding\], operator.add\] - the only field using a reducer. This is what lets parallel research nodes append instead of overwrite. Every other field is standard assignment.
- error: Optional\[dict\], never Optional\[str\] - structured envelope (code, node, message, recoverable) so node failures are identifiable and routable, not just loggable strings.
- published_date on RawFinding is explicitly marked unreliable (Spike 1 finding) - EntityData.announced_date, extracted from article body during Entity Extraction, is the canonical date field everywhere else in the system.
- ScoredFinding.duplicate_reason is a string enum (pre_filter | url_match | title_match | embedding_similarity), not just a boolean - dedup behavior needs to be debuggable after the fact, not just confirmed/denied.
- Drop counters are tracked separately per filter stage: findings_dropped_freshness, findings_dropped_scope, findings_dropped_dedup. This is the system's primary data-quality monitoring instrument - a spike in any one of these tells you which layer is misbehaving, instead of one opaque "findings dropped" number.

Full TypedDict definitions (RawFinding, EntityData, ScoredFinding, BriefingItem, SignalState) and the ErrorCode constants live in the PRD section 8-9 and get implemented verbatim in agent/state.py - this document doesn't repeat the schema, it explains why its shape is what it is.

## 5\. Memory Architecture

Three LangGraph Store namespaces, all keyed by ("user", user_id, &lt;type&gt;) - the user_id keying is what makes Phase 4 multi-tenancy a config change later, not a rebuild.

**Semantic memory** - background knowledge (known startups, investor profiles, tracked verticals) read before research starts. Informs Search Planner.

**Episodic memory** - every completed run: titles, URLs, normalized company names, announced dates, run summary. This is what Hybrid Dedup compares every new finding against. Written _before_ Delivery - the system's core reliability guarantee depends on this ordering, not on Gmail succeeding.

**Procedural memory** - structured JSON preference profile only (high/low-signal categories, trusted sources, query boost/suppress terms, source weights, confidence threshold). Updated by deterministic aggregation, never by an LLM rewriting the profile. Minimum 5 feedback signals required before any update; source weights floored at 0.3 so no source is ever fully zeroed out.

**Persistence migration path (architecturally significant, not just a config swap):**

- Checkpointer: MemorySaver (Phase 1, in-memory) → PostgresSaver (Phase 2, Supabase-backed)
- Store: InMemoryStore (Phase 1) → PostgresStore (Phase 2)

Both migrations are designed to be internal-implementation swaps behind the same function signatures - Build Spec Sessions 9.5 and 13 build the Phase 1 stand-ins specifically so Week 2 upgrades internals rather than inventing the nodes under time pressure.

## 6\. Filtering & Quality Pipeline (the architecture's actual purpose)

This is the part of the system the PRD calls the single most important requirement, so it's worth stating as its own section rather than burying it inside the node list.

| **Stage** | **Node**                     | **What it removes**                                       | **Why this stage, not another**                                                                                                                     |
| --------- | ---------------------------- | --------------------------------------------------------- | --------------------------------------------------------------------------------------------------------------------------------------------------- |
| 1         | Freshness Validation         | Republished stale content (>30 days, parseable date only) | Before any LLM cost - Indian startup news has a republishing pattern where 3-month-old stories resurface with fresh URLs and yesterday's date       |
| 2         | Entity Extraction (implicit) | Malformed LLM output                                      | Pydantic validation layer (EntityDataModel) rejects bad shapes before they reach Scope Filter                                                       |
| 3         | Scope Filter                 | Non-Indian, out-of-range funding, out-of-range stage      | After extraction (needs the fields), before scoring (no point scoring something about to be discarded)                                              |
| 4         | Hybrid Dedup                 | Cross-publication duplicates                              | URL matching alone misses the same story appearing on 3 different domains - the company+date pre-filter catches most of this at zero embedding cost |

The recurring design principle across all four stages: **drop only on an explicit, confirmed violation - never because a field is missing.** A null location is ambiguous, not a rejection. This rule appears identically in Freshness, Scope Filter, and is the reason the pre-filter dedup stage exists before the embedding stage - cheap deterministic checks run first, expensive/probabilistic checks only run on what survives.

## 7\. Error Handling & Resilience

Every node failure produces the same structured envelope - {code, node, message, recoverable} - defined once in agent/state.py, never improvised per-node. recoverable: True means the graph retries or continues with degraded data; False means the run aborts.

**Recoverable:** Tavily/HN/RSS timeouts (retry, then skip that source and continue), entity extraction failure on a single item (skip that item, log to failed_findings, continue the run).

**Non-recoverable:** Gmail auth failure (needs human - abort and flag), Synthesis failure after retries exhausted (no briefing possible without it - abort run, status = failed).

Per-node retry policy (documented now, before the first real timeout, per PRD section 10):

| **Node**                     | **Retries** | **On final failure**                                                   |
| ---------------------------- | ----------- | ---------------------------------------------------------------------- |
| Tavily Search                | 2           | Log + continue with other sources                                      |
| YC API                       | 2           | Log + continue (has its own fallback chain - see below)                |
| HN Algolia                   | 2           | Log + continue                                                         |
| RSS Feeds                    | 1           | Log + continue, lowest-criticality source                              |
| Entity Extraction (per item) | 1           | Skip item, log, continue run                                           |
| Synthesis                    | 1           | Abort run, status = failed                                             |
| Gmail Delivery               | 3           | Log delivery_failed - run already persisted via Episodic Memory Writer |

**YC API Node gets a dedicated fallback chain, not just retries** - it's the most fragile source in the system (unofficial, undocumented endpoint). Primary: directory scrape. Fallback: Tavily query scoped to ycombinator.com via include_domains. Final: log failure, continue without YC data. This chain is written as a visible code comment, not left implicit.

**Cost guardrails** (MAX_FINDINGS_PER_RUN, MAX_RUN_COST_USD) are defined in agent/state.py but enforced in Entity Extraction - the first node where a bad news week (Tavily returning 80 results) would otherwise translate directly into 80 uncapped GPT-4o mini calls.

## 8\. Database Schema (Supabase PostgreSQL, Phase 2+)

Phase 1 runs entirely without Supabase (MemorySaver + InMemoryStore, console output). The schema below is created in Phase 2, Build Spec Session 11.

Core tables: user_configs, briefing_runs (with thread_id for LangGraph time-travel and run_config JSONB snapshot for evaluation replay), briefing_items (with embedding vector(1536) for pgvector dedup, requires the extension enabled before Phase 2 starts), companies (data shape exists Phase 1 inside briefing_items.entities JSONB, migrates to its own table Phase 2), funding_rounds (Phase 2), agent_run_metrics (Phase 1-critical - created even before other DB tables exist conceptually, since it's the primary data-quality monitoring instrument: per-stage drop counts, per-source result counts, cost, duration), evaluation_datasets and failed_findings (Phase 3), agent_memory (backing store for the three memory namespaces).

PostgresSaver creates its own checkpointer tables automatically - these are never defined manually.

RLS is enabled on every custom table, auto-scoping every query to user_id - this is also what makes Phase 4 multi-tenancy a refactor rather than a rebuild, since the namespace key is already user_id everywhere.

## 9\. API Surface (FastAPI, Phase 2+)

Grouped by auth requirement, not by node - this is the external interface, not the internal graph:

- **Auth** (Supabase-handled): signup, login
- **Agent control** (JWT): POST /agent/run (manual trigger), GET /agent/status (idle/running/pending_hitl)
- **Briefings** (JWT): list, get-one, approve (resumes HITL interrupt), edit, reject
- **Feedback** (JWT): per-item useful/not_relevant + reason
- **Config** (JWT): get/update user config
- **Metrics** (JWT): /metrics/runs, /metrics/sources - surfaces agent_run_metrics to the UI
- **Memory** (JWT, read-only): semantic/episodic/procedural inspectors

Auth model: Supabase Auth (email/password) issues a JWT, stored in frontend memory (never localStorage), validated by FastAPI middleware against the Supabase JWT secret, RLS enforces row-level scoping independently of application logic.

## 10\. Tech Stack

| **Layer**                     | **Choice**                                 | **Locked reason**                                                                                                                 |
| ----------------------------- | ------------------------------------------ | --------------------------------------------------------------------------------------------------------------------------------- |
| Language                      | Python 3.11+                               | LangGraph is Python-first                                                                                                         |
| Agent framework               | LangGraph                                  | Core learning objective; StateGraph + Send API + Store + interrupt() all demonstrated                                             |
| Extraction/classification LLM | GPT-4o mini                                | Cheap, fast - Prompt v3 locked at 91% accuracy, no further iteration needed                                                       |
| Synthesis LLM                 | GPT-4o                                     | Briefing quality matters more than cost at this single call per run                                                               |
| Embeddings                    | text-embedding-3-small                     | 0.85 cosine threshold validated in Spike 3                                                                                        |
| Search                        | Tavily API                                 | Free tier; include_domains is mandatory on every call (Spike 1)                                                                   |
| Database                      | Supabase PostgreSQL + pgvector             | Free tier; pgvector must be enabled before Phase 2 dedup upgrade                                                                  |
| Checkpointer                  | MemorySaver → PostgresSaver                | Phase 1 → Phase 2 migration, same interface                                                                                       |
| Memory store                  | InMemoryStore → PostgresStore              | Same migration pattern                                                                                                            |
| Auth                          | Supabase Auth                              | Email/password, JWT                                                                                                               |
| Observability                 | LangSmith                                  | Free tier (5,000 traces/month), every node traced from day one                                                                    |
| Email                         | smtplib + Gmail App Password → Gmail OAuth | Zero-friction start, upgraded Phase 3                                                                                             |
| Scheduler                     | APScheduler                                | Pure Python, no infra locally; production needs an external cron trigger since APScheduler's process dies on most deploy restarts |
| Backend                       | FastAPI                                    | Async, pairs naturally with LangGraph's async execution                                                                           |
| Frontend                      | Plain HTML/JS                              | Deliberate - keeps focus on the agent architecture, not frontend complexity                                                       |
| Deploy target                 | Northflank (backend) + Vercel (frontend)   | Per Build Spec Session 23-24                                                                                                      |

**Sources explicitly evaluated and dropped:** Twitter/X (299/mo), Work at a Startup (undocumented internal endpoint). These belong in DECISIONS.md as rejected alternatives once that file exists, not just here.

## 11\. Phase Boundaries (architectural, not just scheduling)

**Phase 1** ships a complete, correct, single-run pipeline with zero infrastructure: no Supabase, no Gmail, no scheduler, no HITL, no auth, no embeddings. The architectural bet here is that all the deterministic filtering logic (Freshness, Scope, pre-filter Dedup) and the LLM nodes (Entity Extraction, Synthesis) can be fully validated against MemorySaver/InMemoryStore before any infra complexity is introduced - infra bugs and logic bugs never get debugged at the same time.

**Phase 2** is the infrastructure-and-product phase: Supabase, persistence migration, embeddings, scheduling, HITL, delivery, and the UI screens that make the agent usable by an actual human instead of a terminal script.

**Phase 3** is the learning-and-evaluation phase: procedural memory becomes live (not just defined), LangSmith evaluation against a golden dataset, ATS sources added, structured failure logging.

**Phase 4** (multi-tenancy) is explicitly out of scope for the build and described as a refactor, not a rebuild - enabled by the user_id-keyed namespacing decisions made from Phase 1 onward.

_This document is the system's shared understanding of how Signal works and why. It does not change without a corresponding \`DECISIONS.md\` entry._