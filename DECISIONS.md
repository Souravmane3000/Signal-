# DECISIONS.md

Project: Signal

Status: Architecture Decision Record (ADR)

Purpose:

Record important project decisions, rationale, alternatives considered, and consequences.

This document is the highest-priority source of truth in the project.

If DECISIONS.md conflicts with another planning document, DECISIONS.md wins.

## Decision Record Format

Every new decision must use the following format.

## DEC-XXX: Title

Date: YYYY-MM-DD

Status: Proposed | Accepted | Deprecated | Replaced

Decision: What was decided.

Context: Why the decision was needed.

Alternatives Considered:

- Option A
- Option B
- Option C

Reason For Selection: Why the chosen option won.

Consequences:

## Benefits

## Tradeoffs

## Affected Documents

Replaces: (optional)

## DEC-001: Single LangGraph Pipeline

Date: 2026-06-22

Status: Accepted

Decision: Signal uses a single orchestrated LangGraph pipeline.

Context: Signal's primary job is processing startup intelligence through a predictable sequence of steps.

Alternatives Considered:

- Multi-agent swarm
- Multiple specialized graphs
- Single graph pipeline

Reason For Selection: The workflow is fundamentally sequential - Research → Filter → Dedup → Synthesis → Delivery. A multi-agent system would add complexity without meaningful benefit.

Consequences:

Benefits:

- Lower cost
- Easier debugging
- Easier evaluation
- Easier observability

Tradeoffs:

- Less flexibility
- Future expansion may require graph restructuring

Affected Documents:

- PRD.md
- ARCHITECTURE.md

## DEC-002: Deterministic Filters Execute Before Expensive or Judgment-Based Steps _(revised - broadened to cover both ordering rules)_

Date: 2026-06-22

Status: Accepted

Decision: Freshness Validation executes before Entity Extraction. Scope Filter executes before Source Trust Scoring.

Context: LLM calls are the most expensive operation in the pipeline; judgment-based scoring should only run on data that has already survived cheaper, deterministic checks. Both orderings express the same underlying principle: cheap, deterministic checks run first, expensive or probabilistic checks only run on what survives.

Alternatives Considered:

- LLM first, filter later
- Filter first, LLM later
- Score first, filter later

Reason For Selection: Stale or out-of-scope findings should be removed before spending tokens or computing a trust score on data that's about to be discarded anyway.

Consequences:

Benefits:

- Lower cost
- Faster execution
- Reduced noise
- No wasted scoring on discarded findings

Tradeoffs:

- Potentially useful historical findings are removed earlier than a different ordering might allow

Affected Documents:

- ARCHITECTURE.md
- CURSOR_RULES.md
- EVAL.md

## DEC-003: Human-In-The-Loop After Synthesis

Date: 2026-06-22

Status: Accepted

Decision: Human review occurs after synthesis and before delivery.

Context: The briefing is the final user-facing artifact.

Alternatives Considered:

- No HITL
- HITL before synthesis
- HITL after synthesis

Reason For Selection: The human should review the final product, not intermediate data.

Consequences:

Benefits:

- Higher quality output
- Reduced hallucination risk

Tradeoffs:

- Slightly slower workflow

Affected Documents:

- ARCHITECTURE.md
- PRD.md

## DEC-004: Episodic Memory Before Delivery, Conditional on HITL Outcome _(revised - Reject-path behavior made explicit)_

Date: 2026-06-22

Status: Accepted

Decision: Episodic memory writes occur before delivery attempts, on the Approve and Edit paths only. The Reject path discards findings and does not write to episodic memory.

Context: Email delivery can fail, and deduplication history cannot be lost when it does - but a rejected briefing should not pollute future dedup behavior with content a human explicitly declined.

Alternatives Considered:

- Delivery before memory write
- Memory write before delivery, unconditionally on all HITL outcomes
- Memory write before delivery, conditional on Approve/Edit only

Reason For Selection: Signal must preserve run history even if delivery fails, but only for content a human actually approved or edited into approval.

Consequences:

Benefits:

- Stronger reliability
- Better dedup behavior
- Rejected content never contaminates episodic memory

Tradeoffs:

- Possible memory entries for approved-but-undelivered briefings

Affected Documents:

- ARCHITECTURE.md
- CURSOR_RULES.md
- EVAL.md

## DEC-005: Hybrid Dedup Strategy

Date: 2026-06-22

Status: Accepted

Decision: Dedup uses a staged approach.

Phase 1: Company + Date, URL Match, Title Match. Phase 2: Embedding Similarity.

Context: Embedding-based dedup is more expensive and unavailable until pgvector is provisioned.

Alternatives Considered:

- Embeddings only
- Exact match only
- Hybrid approach

Reason For Selection: Hybrid approach provides the best cost-performance balance - cheap exact-match stages catch most duplicates at zero embedding cost, fuzzy duplicates are caught later once Phase 2 lands.

Consequences:

Benefits:

- Cheap MVP
- Better future recall

Tradeoffs:

- Dedup quality (recall on fuzzy duplicates specifically) is lower before Phase 2

Affected Documents:

- ARCHITECTURE.md
- BUILD_SPEC.md
- EVAL.md

## DEC-006: GPT-4o Mini for Entity Extraction

Date: 2026-06-22

Status: Accepted

Decision: Entity extraction uses GPT-4o Mini.

Context: Entity extraction is high-volume - it runs on every surviving finding, every run.

Alternatives Considered:

- GPT-4o
- GPT-4o Mini
- Fully deterministic extraction

Reason For Selection: GPT-4o Mini provides acceptable accuracy at lower cost, which matters given the per-run volume.

Consequences:

Benefits:

- Reduced runtime cost

Tradeoffs:

- Slightly lower accuracy ceiling than GPT-4o

Affected Documents:

- PRD.md
- BUILD_SPEC.md

## DEC-007: Deterministic Procedural Memory

Date: 2026-06-22

Status: Accepted

Decision: Procedural memory updates are deterministic. LLMs may not rewrite procedural memory.

Context: Feedback loops can become unstable if an LLM is allowed to rewrite its own preference profile.

Alternatives Considered:

- LLM-generated updates
- Deterministic aggregation

Reason For Selection: Deterministic updates are auditable and predictable.

Consequences:

Benefits:

- Stability
- Explainability

Tradeoffs:

- Less adaptability

Affected Documents:

- CURSOR_RULES.md
- ARCHITECTURE.md

## DEC-008: Vertical Slice Development

Date: 2026-06-22

Status: Accepted

Decision: Signal is built using vertical slices.

Context: Phase-based development creates delayed feedback and defers integration risk to the end of the build.

Alternatives Considered:

- Traditional phase model
- Vertical slices
- Hybrid

Reason For Selection: Vertical slices provide earlier validation and a demoable artifact after every slice.

Consequences:

Benefits:

- Faster feedback
- Reduced rework

Tradeoffs:

- More planning discipline required

Affected Documents:

- CURSOR_RULES.md
- TASKS.md
- CURRENT_PHASE.md

## DEC-009: Builder + Reviewer Agent Model

Date: 2026-06-22

Status: Accepted

Decision: Signal's build uses a Builder Agent and a Reviewer Agent. The Architect role is external and on-demand, not a persistent Cursor agent.

Context: Additional standing agents increase complexity and cost without proportional benefit at this project's scale.

Alternatives Considered:

- Agent swarm
- Builder only
- Builder + Reviewer

Reason For Selection: Provides quality control with minimal overhead. See DEC-013 for the model strategy used within this structure.

Consequences:

Benefits:

- Simpler workflow
- Lower token consumption

Tradeoffs:

- Human remains final decision-maker on every merge

Affected Documents:

- CURSOR_RULES.md

## DEC-010: Evaluation Overrides Opinion

Date: 2026-06-22

Status: Accepted

Decision: EVAL.md results override subjective judgment.

Context: Teams naturally drift toward "looks good" as an unstated acceptance criterion.

Alternatives Considered:

- Human judgment only
- Metrics-only
- Metrics + human review

Reason For Selection: Objective evaluation against a fixed dataset prevents quality drift.

Consequences:

Benefits:

- Repeatable quality standards
- Easier regression detection

Tradeoffs:

- Additional evaluation effort

Affected Documents:

- EVAL.md
- CURSOR_RULES.md

## DEC-011: Supabase PostgreSQL + pgvector Over Pinecone/Qdrant/Weaviate _(new)_

Date: 2026-06-22

Status: Accepted

Decision: Signal's vector store and primary relational database are both Supabase PostgreSQL, using the pgvector extension for embedding similarity.

Context: Hybrid Dedup's Phase 2+ stage requires a vector store; the project separately needs a relational database for users, configs, briefings, and run metrics.

Alternatives Considered:

- Pinecone
- Qdrant
- Weaviate
- Supabase PostgreSQL + pgvector

Reason For Selection: A dedicated vector database alongside a separate relational database doubles infrastructure, cost, and operational surface. pgvector keeps both in one already-provisioned, free-tier database.

Consequences:

Benefits:

- Single database to manage
- Free tier
- RLS applies uniformly across vector and relational data
- No second vendor or API surface

Tradeoffs:

- pgvector's similarity search is less specialized than a dedicated vector database at very large scale - acceptable at Signal's data volume, would need revisiting under a large scale increase

Affected Documents:

- ARCHITECTURE.md
- BUILD_SPEC.md

## DEC-012: Sources Evaluated and Rejected _(new)_

Date: 2026-06-22

Status: Accepted

Decision: Twitter/X, LinkedIn scraping, the Crunchbase API, and Work at a Startup are excluded as Signal data sources.

Context: Four research nodes were selected (Tavily, YC directory, HN Algolia, Google News RSS); several other candidate sources were evaluated during planning and dropped.

Alternatives Considered:

- Twitter/X API
- LinkedIn scraping
- Crunchbase API
- Work at a Startup

Reason For Selection (rejection rationale): Twitter/X API requires a minimum \$100/month tier. LinkedIn scraping violates LinkedIn's Terms of Service. Crunchbase API costs \$299/month minimum. Work at a Startup relies on an undocumented internal endpoint with no stability guarantee.

Consequences:

Benefits:

- Zero additional source cost
- No ToS exposure
- No dependency on an unstable, undocumented endpoint

Tradeoffs:

- Narrower source coverage than a paid-source approach would provide

Affected Documents:

- PRD.md
- ARCHITECTURE.md

## DEC-013: Model Selection by Capability Tier, Not by Specific Model Name _(new)_

Date: 2026-06-22

Status: Accepted

Decision: CURSOR_RULES.md defines build-time model defaults by capability tier - fastest/cheapest for Tier 1, mid-tier reasoning for Tier 2, premium reserved as a last resort - rather than naming a specific model.

Context: An earlier draft defaulted Tier 2 work to a named premium model by default, which risked both unnecessary build-budget spend and staleness as model lineups change over time.

Alternatives Considered:

- Name a specific premium model as the Tier 2 default
- Name a specific cheap model with no tiering at all
- Capability-tier framing with no model names

Reason For Selection: Capability-tier framing protects the \$15 build budget by defaulting away from premium spend, while remaining valid regardless of which specific models are available later.

Consequences:

Benefits:

- Budget protection
- Future-proof against model lineup changes

Tradeoffs:

- Requires whoever operates Cursor to map "fastest/cheapest" and "mid-tier" to actual available models at build time, rather than reaching for a fixed name

Affected Documents:

- CURSOR_RULES.md

## DEC-014: Embedding Model and Similarity Threshold for Dedup Stage 4 _(new)_

Date: 2026-06-22

Status: Accepted

Decision: Hybrid Dedup's Phase 2+ embedding-similarity stage uses text-embedding-3-small with a 0.85 cosine similarity threshold.

Context: Stages 1-3 of dedup are exact-match and cannot catch fuzzy duplicates - same event, differently worded title, no shared URL. An embedding-based stage was needed to close this gap.

Alternatives Considered:

- Higher similarity thresholds
- Lower similarity thresholds
- Other embedding models

Reason For Selection: Validated directly in Spike 3 against real duplicate and near-duplicate story sets. 0.85 produced an acceptable precision/recall balance at this model's embedding scale.

Consequences:

Benefits:

- Validated against real data, not guessed
- Closes the fuzzy-duplicate gap stages 1-3 leave open

Tradeoffs:

- A fixed threshold may need revisiting as more real-world duplicate patterns are observed post-launch

Affected Documents:

- ARCHITECTURE.md
- EVAL.md

## DEC-015: Entity Extraction Prompt Locked at v3 _(new)_

Date: 2026-06-22

Status: Accepted

Decision: Entity Extraction's prompt is locked at v3. No further pre-build prompt iteration occurs unless extraction accuracy regresses below the threshold defined in EVAL.md.

Context: Prompt v3 was validated at 91% accuracy during pre-build spikes, clearing EVAL.md's 90% threshold with margin.

Alternatives Considered:

- Continue iterating the prompt pre-build
- Lock at v3, treat further changes as a Tier 2 task gated by EVAL.md regression

Reason For Selection: Further pre-build iteration has diminishing returns once a margin above threshold is established; locking conserves build budget for implementation rather than continued prompt tuning.

Consequences:

Benefits:

- Build budget protected
- Clear regression baseline for future evaluation

Tradeoffs:

- A real accuracy ceiling exists at v3 that future work may need to revisit

Affected Documents:

- PRD.md
- EVAL.md