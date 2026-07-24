# Signal — Autonomous Indian Startup Intelligence Agent

> A production-architected LangGraph agent that monitors the Indian startup ecosystem, deduplicates across publications, learns from feedback, and delivers a weekly briefing to your inbox — fully autonomous.

---

## The Problem I Set Out to Solve

If you follow Indian startup news, you know the experience: the same funding round gets covered by Inc42, YourStory, Economic Times, and three aggregators — all in the same week, all with different headlines. You read it four times and still don't know if there's anything genuinely new.

There was no tool that:
- Monitored the market continuously and automatically
- Deduplicated against everything it had already reported to you
- Filtered by what you actually care about (stage, sector, amount)
- Learned from your feedback over time

So I built one.

---

## The Hardest Problem: Cross-Publication Deduplication

This is the core technical challenge Signal exists to solve, and it's harder than it sounds.

URL-based deduplication doesn't work. The same Series A announcement appears on four different domains with four different URLs. Title matching doesn't work either — Inc42's headline is not the same as YourStory's for the same event.

**The solution I designed and validated:** a staged hybrid dedup pipeline.

```
Stage 0 — Pre-filter: company_name_normalized + announced_date exact match
           → catches majority of cross-publication duplicates at zero cost

Stage 1 — URL exact match against episodic memory
           → fast, cheap, catches same-source republishes

Stage 2 — Normalized title exact match
           → catches near-identical reposts

Stage 3 (Phase 2+) — Embedding cosine similarity at 0.85 threshold
           → text-embedding-3-small on title + 300-char snippet
           → catches same event, differently worded, different publication
```

I validated the 0.85 cosine threshold during a pre-build spike against 3 real story sets with 3–4 publication versions each. Clean separation between true duplicates and distinct articles — no guessing.

The cheaper, deterministic stages run first. Embeddings (the expensive call) only run on what survives. This is the core cost discipline principle that runs through every layer of this system.

---

## The Second-Hardest Problem: Stale Content Masquerading as Fresh

Indian startup news has a specific republishing pattern: a funding round from three months ago resurfaces on an aggregator with a fresh URL and yesterday's date. Tavily surfaces it. Without intervention, it passes dedup (new URL, different title) and appears in the briefing as a "new" round.

I built a dedicated **Freshness Validation Node** that runs *before* any LLM call — specifically to avoid paying GPT-4o mini to process content that's going to be discarded anyway.

**Drop rule:** Drop only if `published_date` is parseable AND older than 30 days.  
**Retain rule:** Missing or ambiguous date → keep with a confidence penalty, never drop. A null field is ambiguity, not a rejection.

This rule — *drop only on confirmed violations, never on missing data* — is applied uniformly across every filter in the system.

---

## What I Built

Signal is a 15-node LangGraph `StateGraph` that runs on a schedule, persists memory across sessions, and improves its search strategy from user feedback over time. It is an **agent-as-system**, not a chatbot.

### The Full Pipeline

```
Trigger (APScheduler / manual POST /agent/run)
    │
    ▼
Config Loader         — reads user config + all 3 memory namespaces
    │
    ▼
Search Planner        — deterministic query generation (Phase 1)
                        reads procedural memory to adjust queries (Phase 2+)
    │
    ├── Tavily Search Node      ─┐
    ├── YC API Node             ─┤── parallel fan-out (Send API in Phase 2+)
    ├── HN Algolia Node         ─┤
    └── Google News RSS Node    ─┘
                │
                ▼
            Reducer               — operator.add merge checkpoint
                │
                ▼
    Freshness Validation          — deterministic, no LLM
                │                   drops stale, penalizes undated
                ▼
    Entity Extraction             — GPT-4o mini, Prompt v3 (91% accuracy)
                │                   Pydantic validation layer on output
                ▼
    Scope Filter                  — deterministic, no LLM
                │                   India-only / $500K–$50M / Seed–Series B
                ▼
    Source Trust Scoring          — deterministic confidence sort
                │
                ▼
    Hybrid Dedup                  — 3 exact-match stages (Phase 1)
                │                   + embedding similarity (Phase 2+)
                ▼
    Synthesis                     — GPT-4o builds structured weekly briefing
                │
                ▼
    HITL Interrupt                — interrupt(), graph pauses for human review
                │
        ┌───────┴───────┐
   [Approve/Edit]    [Reject]
        │                │
        ▼                ▼
Episodic Memory     Discard + Log
Writer (BEFORE      (no memory write —
delivery — run      reject path never
persisted even      pollutes dedup history)
if Gmail fails)
        │
        ▼
    Delivery              — smtplib + Gmail App Password
        │
        ▼
Run Metrics Writer        — per-stage drop counts, cost, runtime
        │
        ▼
Feedback Collector        — per-item useful/not_relevant rating
        │
        ▼
Procedural Memory         — deterministic aggregation, ≥5 signals required
Updater                     no LLM, source weights floored at 0.3
```

---

## Architecture Decisions Worth Explaining

These were real design decisions, each with a considered rationale. They live in `DECISIONS.md`.

**Single pipeline, not a multi-agent swarm (DEC-001)** — Signal's workflow is fundamentally sequential: Research → Filter → Dedup → Synthesis → Delivery. A swarm adds coordination overhead with no meaningful benefit at this problem's scale.

**Deterministic filters before LLM calls (DEC-002)** — Three pure-Python nodes (Freshness Validation, Scope Filter, pre-filter Dedup stages) sit between the research layer and GPT-4o mini. Every finding that gets dropped by a deterministic check is a GPT-4o mini call that never happens. At 80–100 findings per run, this matters.

**Episodic memory before delivery, always (DEC-004)** — Gmail delivery can fail. The dedup history must never be lost when it does. `EpisodicMemoryWriter` always executes before `Delivery` — this is enforced by graph edge order, not by application logic. If Gmail fails, the run is already persisted. Delivery failure is a delivery problem, not a data problem.

**Reject path never writes to episodic memory (DEC-004)** — A rejected briefing should not pollute future dedup behavior with content a human explicitly declined. The conditional routing after HITL is the sole enforcement mechanism — the memory writer node itself has no HITL awareness.

**Supabase PostgreSQL + pgvector over dedicated vector databases (DEC-011)** — Pinecone/Qdrant/Weaviate alongside a separate relational DB doubles infrastructure cost and operational surface. pgvector keeps everything in one free-tier database. Signal's data volume doesn't require a specialized vector store.

**Procedural memory is deterministic, no LLM (DEC-007)** — Feedback loops become unstable if an LLM can rewrite its own preference profile. Source weights are aggregated from counted feedback patterns, floored at 0.3 so no source is ever fully suppressed, and updated only after a minimum of 5 feedback signals.

---

## Pre-Build Validation (All Spikes Closed Before First Line of Code)

I ran three validation spikes before writing any implementation code. These are locked results, not open questions.

**Spike 1 — Source Validation**  
Finding: Tavily without `include_domains` returns LinkedIn, YouTube, and social noise — not Indian startup news. `include_domains` is now a mandatory parameter on every Tavily call, enforced as a hard architectural rule.  
Finding: Tavily's `published_date` is unreliable. Date extraction is the Entity Extraction node's responsibility, from article body text.

**Spike 2 — Entity Extraction**  
Finding: Prompt v3 scores 91% accuracy across 25 real Indian startup articles, 0 parse errors, 0 category violations. Prompt is locked — no further iteration needed pre-build.

**Spike 3 — Dedup Threshold**  
Finding: 0.85 cosine similarity on `text-embedding-3-small` (title + 300-char snippet) cleanly separates true duplicates from distinct articles. The `company_name_normalized + announced_date` pre-filter eliminates the majority of cross-publication duplicates before any embedding call.

---

## What Makes This System Observable

Signal's metrics are designed to answer one question: *is my data fresh and relevant this week?*

Every run writes to `agent_run_metrics`:

| Counter | What it tells you |
|---|---|
| `findings_retrieved` | Total findings before any filtering |
| `findings_dropped_freshness` | Stale content caught before LLM cost was incurred |
| `findings_dropped_scope` | Out-of-scope content removed deterministically |
| `findings_dropped_dedup` | Cross-publication duplicates caught |
| `findings_in_briefing` | What the user actually received |
| `source_health` | Which sources failed this run |

A spike in `findings_dropped_freshness` means aggregators are republishing stale content. A spike in `findings_dropped_dedup` means the same events are being covered heavily. A drop in `findings_retrieved` from a specific source means that source endpoint changed.

---

## Memory Architecture

Three LangGraph Store namespaces, keyed by `user_id` from day one — Phase 4 multi-tenancy is a config change, not a rebuild.

**Semantic memory** — background knowledge (known startups, investor profiles, tracked verticals) read before research starts.

**Episodic memory** — every completed run: titles, URLs, normalized company names, dates. This is what Hybrid Dedup compares every new finding against. Written before delivery, unconditionally on the Approve/Edit path.

**Procedural memory** — structured JSON preference profile updated from feedback. Drives query boost/suppress terms, source weights, preferred stages. Never rewritten by an LLM.

---

## Evaluation Framework

Signal has a two-level evaluation system. "Looks correct" is not an acceptance criterion.

**Level 1 — Golden Run (`golden_run.py`):** Fast regression suite, 11 tests, 10-finding frozen dataset, target under 30 seconds and $0.01. Run after every meaningful implementation change. Catches: graph compilation failures, state schema regressions, node ordering drift, guardrail removal, YC fallback chain breakage.

**Level 2 — Full Evaluation (EVAL.md):** Triggered on prompt changes, model changes, threshold changes, and pre-production. Runs against 6 frozen validation datasets (A–F). Human validates Tier 2 nodes (Entity Extraction, Dedup, Synthesis) against fixed accuracy thresholds.

Key thresholds:
- Entity Extraction: ≥90% field-level accuracy, ≥95% normalization accuracy, 0 category violations
- Dedup Phase 1: ≥99% precision, recall tracked but not gated (fuzzy duplicates intentionally not caught until Stage 4)
- Dedup Phase 2+: ≥90% precision, ≥85% recall
- Synthesis: 5/5 accuracy (zero hallucinations), ≥4/5 on coverage, relevance, freshness, readability
- Freshness Validation and Scope Filter: 100% correctness, any incorrect classification is a failure

---

## Tech Stack

| Layer | Choice | Reason |
|---|---|---|
| Agent framework | LangGraph | StateGraph, Send API, interrupt(), Store — all core concepts demonstrated |
| Extraction LLM | GPT-4o mini | High-volume node — cost matters. Prompt v3 validated at 91% accuracy |
| Synthesis LLM | GPT-4o | One call per run. Quality matters more than cost at this step |
| Embeddings | text-embedding-3-small | 0.85 threshold validated in Spike 3 |
| Search | Tavily API with `include_domains` | Free tier; domain restriction is mandatory (Spike 1 finding) |
| Database | Supabase PostgreSQL + pgvector | Free tier; single DB for both relational and vector workloads |
| Checkpointer | MemorySaver → PostgresSaver | Phase 1 → Phase 2 migration behind same interface |
| Memory store | InMemoryStore → PostgresStore | Same migration pattern |
| Scheduler | APScheduler | Pure Python, no infra needed locally |
| Backend | FastAPI | Async, pairs naturally with LangGraph's async execution |
| Observability | LangSmith | Free tier, every node traced from day one |
| Email | smtplib + Gmail App Password → Gmail OAuth | Zero-friction Phase 2, upgraded Phase 3 |
| Deploy | Northflank (backend) + Vercel (frontend) | No cold-start on Northflank — critical for scheduled agent |

**Sources evaluated and rejected:** Twitter/X ($100/month minimum), LinkedIn scraping (ToS violation), Crunchbase API ($299/month), Work at a Startup (undocumented internal endpoint, no stability guarantee).

---

## Build Approach

Signal is built in vertical slices, not phases. Each slice delivers a testable end-to-end capability.

| Slice | Goal | Status |
|---|---|---|
| 1 — Foundation | Repo scaffold, state schema, skeleton graph, test fixtures | In Progress |
| 2 — Research Pipeline | All 4 research nodes returning real findings | TODO |
| 3 — Processing + Phase 1 DOD | Full 15-node pipeline, end-to-end run, Golden Run passes | TODO |
| 4 — Infrastructure + HITL | PostgresSaver, HITL interrupt, Gmail delivery, Supabase | TODO |
| 5 — API + Frontend + Scheduler | Full product accessible via browser, weekly autonomy | TODO |

Phase-based development defers integration risk to the end. Vertical slices mean a working, demonstrable system at the end of every slice.

**Budget discipline:** Total Cursor build budget is $15 implementation + $5 debug reserve. Tier 1 tasks use the cheapest capable model. Tier 2 tasks use a mid-tier reasoning model. The most expensive model tier is never the default.

---

## Project Structure

```
signal/
├── agent/
│   ├── state.py                  # SignalState, all TypedDicts, ErrorCode, constants
│   ├── graph.py                  # LangGraph StateGraph — 15 nodes wired
│   ├── nodes/
│   │   ├── config_loader.py
│   │   ├── search_planner.py
│   │   ├── tavily_search.py
│   │   ├── yc_api.py
│   │   ├── hn_algolia.py
│   │   ├── google_news_rss.py
│   │   ├── reducer.py
│   │   ├── freshness_validation.py
│   │   ├── entity_extraction.py
│   │   ├── scope_filter.py
│   │   ├── source_trust_scoring.py
│   │   ├── hybrid_dedup.py
│   │   ├── synthesis.py
│   │   ├── episodic_memory_writer.py
│   │   └── run_metrics_writer.py
│   └── prompts/
│       └── entity_extraction_v3.txt   # Locked at 91% accuracy
├── api/
│   └── main.py                   # FastAPI — 15 endpoints
├── frontend/
│   └── index.html                # 8 screens, plain HTML/JS
├── tests/
│   └── fixtures/
│       └── sample_findings.py    # Reusable test data across all sessions
├── scripts/
│   ├── run_agent.py              # Manual trigger
│   └── test_langsmith.py         # Connectivity verification
├── validation/                   # Frozen evaluation datasets (never modified to pass tests)
│   ├── entity_extraction_gold.json
│   ├── dedup_duplicates.json
│   ├── dedup_false_positives.json
│   ├── scope_filter_gold.json
│   ├── synthesis_gold.json
│   └── freshness_gold.json
├── .env.example
├── requirements.txt
└── README.md
```

---

## Running Locally

```bash
# Clone and set up
git clone https://github.com/Souravmane3000/Signal-.git
cd signal
python -m venv venv && source venv/bin/activate
pip install -r requirements.txt

# Configure environment
cp .env.example .env
# Fill in: OPENAI_API_KEY, TAVILY_API_KEY, LANGCHAIN_API_KEY, GRAPH_VERSION=1.0

# Verify LangSmith connection
python scripts/test_langsmith.py

# Run the agent (Phase 1 — terminal output)
python scripts/run_agent.py
```

Phase 1 requires no database, no Gmail, no deployment. One working end-to-end run with console output.

---

## LangGraph Concepts Demonstrated

| Concept | Where |
|---|---|
| TypedDict state schema with reducers | `SignalState` — `raw_findings: Annotated[list, operator.add]` |
| Send API — parallel node fan-out | Research nodes → Reducer (Phase 2+) |
| Reducer functions | `operator.add` merge for parallel research results |
| Deterministic nodes between LLM nodes | Freshness Validation, Scope Filter, pre-filter Dedup stages |
| MemorySaver → PostgresSaver migration | Same interface, different persistence backend |
| InMemoryStore → PostgresStore migration | Three-namespace memory architecture |
| interrupt() — HITL | Graph pauses, serializes, resumes on human action |
| Conditional edges | HITL routing: Approve/Edit → memory write; Reject → discard |
| Scheduled execution | APScheduler — agent as continuously running system |
| Cross-session persistence | Full memory survives restarts |
| LangSmith tracing | Every node input/output logged from day one |
| Time travel | `thread_id` per run enables state replay |

---

## What's Production-Hardened (Not Just MVP)

- **Retry policy defined before first timeout:** every external node has a documented retry count and backoff schedule, matched to criticality. YC API (most fragile source) has a dedicated fallback chain — scrape fails → Tavily query scoped to `ycombinator.com` → log and continue without YC data.
- **Structured error envelope:** every node failure produces `{"code", "node", "message", "recoverable"}`. Graph can route around recoverable failures; non-recoverable failures (Synthesis exhausted, Gmail auth) abort or flag the run with explicit status.
- **Cost guardrails enforced at the right node:** `MAX_FINDINGS_PER_RUN` and `MAX_RUN_COST_USD` are enforced in Entity Extraction — the first node where a high-volume Tavily response (80 results) would otherwise translate into 80 uncapped GPT-4o mini calls.
- **RLS on every Supabase table:** every query auto-scoped to `user_id`. Phase 4 multi-tenancy is a refactor, not a rebuild.
- **Validation datasets are frozen assets:** they are never modified to make evaluations pass. Fix the implementation. Do not weaken the benchmark.

---

## Documents in /docs

| Document | Purpose |
|---|---|
| `PRD.md` | Product requirements, 15-node pipeline spec, state schema, memory architecture, API surface |
| `ARCHITECTURE.md` | System data flow, node ordering rules, filtering pipeline, error handling, tech stack |
| `BUILD_SPEC.md` | Session-by-session build plan, prompts to paste into Cursor, checkpoints |
| `DECISIONS.md` | 15 locked architecture decisions with rationale and rejected alternatives |
| `TASKS.md` | 40 tasks across 5 slices — tiered, dependency-ordered, with acceptance criteria |
| `CURRENT_PHASE.md` | Active execution context — updated by human at every task boundary |
| `EVAL.md` | Pass/fail thresholds for all quality-sensitive components, validation dataset governance |
| `GOLDEN_RUN_SPEC.md` | Fast regression suite — 11 tests, 10-finding frozen dataset, 30-second target |
| `CURSOR_RULES.md` | Agent execution rules, task tiering, model strategy, stop conditions |
| `AGENT_HANDOFF.md` | Builder/Reviewer agent roles, execution lifecycle, handoff package format |
| `validation/README.md` | Validation dataset structure, ownership, change control, freeze rules |

---

*Signal is built to be demonstrable at every slice boundary, observable in production, and architecturally honest about what each design decision costs and why it was made.*