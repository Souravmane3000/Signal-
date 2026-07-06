# EVAL.md

Project: Signal

Status: Evaluation Source of Truth

Purpose: Define objective pass/fail criteria for all judgment-based and business-critical components in Signal.

This document is the validation framework referenced by CURSOR_RULES.md Section 19.

Evaluation results override subjective opinion.

"Looks correct" is not an acceptance criterion.

## 1\. EVALUATION PHILOSOPHY

Signal exists to deliver:

- Relevant intelligence
- Fresh intelligence
- Accurate intelligence

Evaluation therefore prioritizes:

- Accuracy
- Relevance
- Freshness
- Consistency
- Cost Discipline
- Resilience

Above:

- Prompt elegance
- Model sophistication
- Architectural preferences

A component is considered complete only if it passes its defined evaluation threshold.

## 2\. EVALUATION LEVELS

Signal uses two evaluation levels.

**Level 1 - Fast Regression Validation**

Purpose: Catch regressions after routine implementation work.

Trigger:

- Node implementation changes
- Refactors
- Bug fixes
- Routine PR reviews

Tool: golden_run.py

Characteristics:

- Small fixed dataset
- Fast execution
- Low cost
- Frequent execution

Expected Usage: After every meaningful implementation change.

**Level 2 - Full Evaluation**

Purpose: Validate quality-sensitive behavior.

Trigger:

- Prompt changes
- Threshold changes
- Model changes
- Release candidates
- Pre-production validation

Dataset: Datasets A-F

Characteristics:

- Larger dataset
- More expensive
- Less frequent
- Higher confidence

Expected Usage: Only when quality-sensitive behavior changes.

## 3\. VALIDATION DATASET GOVERNANCE

Validation datasets are frozen assets.

Location: /validation

Rules:

- Datasets may not be edited to make evaluations pass.
- Dataset changes require:
  - Human approval
  - DECISIONS.md entry
  - Dataset version increment

Validation data is a source of truth.

## 4\. VALIDATION DATASET STRUCTURE

**Dataset A - Funding Articles**

Purpose: Entity Extraction evaluation. Target: 25 real Indian startup articles. Sources: Inc42, YourStory, Economic Times, YC announcements.

**Dataset B - Duplicate Story Groups**

Purpose: Dedup evaluation. Target: 20 duplicate groups. Each group contains: same event, different publication, different title, different URL. Note: this dataset exceeds the original Spike 3 validation scope (3 story sets) and represents new validation work, consistent with Dataset F.

**Dataset C - Non-Duplicates**

Purpose: False-positive prevention. Target: 20 unrelated startup stories. Note: this dataset exceeds the original Spike 3 validation scope and represents new validation work, consistent with Dataset F.

**Dataset D - Freshness Cases**

Purpose: Freshness Validation evaluation. Target: 20 findings. Contains: recent stories, stale stories, republished stories, missing dates, ambiguous dates.

**Dataset E - Scope Filter Cases**

Purpose: Scope Filter evaluation. Target: 20 findings. Contains: Indian startups, non-Indian startups, funding outside range, Series C+, missing fields.

**Dataset F - Weekly Briefing Dataset**

Purpose: Synthesis evaluation. Target: 50 curated findings. Contains: funding, hiring, accelerator, founder moves, pivots, shutdowns, ecosystem trends. Note: Dataset F is new production-grade validation work and is not covered by the original spikes.

## 5\. ENTITY EXTRACTION EVALUATION

Node: Entity Extraction Model: GPT-4o Mini

Evaluation Frequency: Prompt change, model change, release candidate.

**Required Fields**

Raw Fields: company_name, founder_name, investor_names, funding_amount_usd, funding_stage, sector, location, announced_date, category.

Normalized Fields: company_name_normalized, investor_names_normalized.

**Scoring Method**

Per-field: Correct = 1, Incorrect = 0, Missing = 0.

**Normalization Evaluation**

Normalization is evaluated independently.

Examples: Razorpay, Razor Pay, Razor-Pay - must normalize to the same canonical value.

Pass Threshold: Normalization Accuracy ≥ 95%.

**Category Evaluation**

Allowed Categories: funding, hiring, founder_move, accelerator, shutdown, pivot, ecosystem_trend.

Category Violations Allowed: 0.

**Structured Output Validation**

Pydantic validation must reject: missing required fields, invalid field types, malformed JSON, schema violations.

Expected Result: rejected findings are logged. Malformed outputs do not propagate downstream.

**Pass Threshold**

| **Metric**              | **Threshold** |
| ----------------------- | ------------- |
| Overall Accuracy        | ≥ 90%         |
| Date Accuracy           | ≥ 90%         |
| Funding Amount Accuracy | ≥ 90%         |
| Normalization Accuracy  | ≥ 95%         |
| Category Violations     | 0             |
| JSON Parse Failures     | 0             |

## 6\. DEDUP EVALUATION _(revised - phase-specific thresholds)_

Node: Hybrid Dedup

Evaluation Frequency: Threshold change, model change, release candidate.

**Phase 1 Evaluation**

Active Stages:

- company_name_normalized + announced_date
- URL Match
- Normalized Title Match

Embedding Similarity (Stage 4): Not active. Not evaluated.

All three active stages are deterministic, exact-match logic - they are not designed to catch fuzzy duplicates (same event, differently worded title, no shared URL). Recall is therefore expected to be incomplete by design at this phase; precision is the meaningful gate, since correct exact-match code should produce almost no false positives.

| **Metric**          | **Phase 1 Threshold** | **Note**                                                                  |
| ------------------- | --------------------- | ------------------------------------------------------------------------- |
| Precision           | ≥ 99%                 | Exact-match logic - near-zero false positives expected if code is correct |
| False Positive Rate | ≤ 1%                  | Same reasoning                                                            |
| Recall              | Tracked, not gated    | Fuzzy duplicates intentionally not caught until Stage 4 exists            |
| False Negative Rate | Tracked, not gated    | Same reasoning                                                            |

**Phase 2+ Evaluation**

Additional Stage: 4. Embedding Similarity. Threshold: 0.85. Model: text-embedding-3-small.

Once Stage 4 is active, recall is expected to rise substantially as fuzzy duplicates get caught. The blended thresholds below apply only from this phase onward - they would be the wrong bar for Phase 1's purely deterministic stages.

| **Metric**          | **Phase 2+ Threshold** |
| ------------------- | ---------------------- |
| Precision           | ≥ 90%                  |
| Recall              | ≥ 85%                  |
| False Positive Rate | ≤ 10%                  |
| False Negative Rate | ≤ 15%                  |

## 7\. FRESHNESS VALIDATION EVALUATION

Node: Freshness Validation Type: Deterministic

**Validation Rules**

Older than 30 days: Dropped. Within 30 days: Retained. Missing date: Retained with penalty. Ambiguous date: Retained with penalty.

**Pass Threshold**

100% correctness. Any incorrect classification: failure.

## 8\. SCOPE FILTER EVALUATION

Node: Scope Filter Type: Deterministic

**Must Reject**

Non-Indian startups, funding &lt; \$500K, funding &gt; \$50M, Series C+.

**Must Retain**

Null location, null funding amount, null funding stage.

**Pass Threshold**

100% correctness. Any incorrect decision: failure.

## 9\. YC RESILIENCE EVALUATION

Purpose: Validate fallback chain behavior.

**Test Scenario**

Simulate: YC directory scrape failure.

Expected Behavior:

- YC scrape fails
- Tavily fallback executes
- Failure logged
- Run continues
- Briefing still generated

**Pass Threshold**

No unhandled exception. Run completes successfully. Fallback invoked correctly.

## 10\. RUNTIME GUARDRAIL EVALUATION

Purpose: Validate production cost protection.

**Test Case A**

Input: Findings > MAX_FINDINGS_PER_RUN. Expected: excess findings skipped, reason logged, run continues safely.

**Test Case B**

Input: Estimated cost exceeds MAX_RUN_COST_USD. Expected: processing stops, reason logged, run remains healthy.

**Pass Threshold**

100% correctness. Any guardrail bypass: failure.

## 11\. SOURCE TRUST SCORING EVALUATION

Source Trust Scoring is intentionally excluded from quality evaluation.

Reason: it does not generate new information. It only applies predefined trust weights defined elsewhere in the system.

Validation is limited to: unit tests, configuration verification. No separate quality benchmark is required.

## 12\. SYNTHESIS EVALUATION

Node: Synthesis Model: GPT-4o

Evaluation Frequency: Prompt change, model change, narrative change, release candidate.

**Human Review Rubric** (scale 1-5)

| **Category** | **Minimum**                                 |
| ------------ | ------------------------------------------- |
| Coverage     | 4/5                                         |
| Accuracy     | 5/5 (any hallucination = automatic failure) |
| Relevance    | 4/5                                         |
| Freshness    | 4/5                                         |
| Readability  | 4/5                                         |

**Pass Threshold**

Average Score ≥ 4.25. Accuracy: 5/5 mandatory. Hallucinations: 0.

## 13\. EPISODIC MEMORY, HITL & PROCEDURAL MEMORY EVALUATION _(new)_

**Episodic Memory Writer**

Purpose: validate the system's core reliability guarantee - episodic memory is written before delivery, regardless of delivery outcome.

_Test Scenario 1 - Delivery failure does not affect persistence._ Simulate: Gmail delivery failure (auth failure or send exception) after an Approve action. Expected: Episodic Memory Writer has already executed before the delivery attempt. The run is marked delivery_failed, not data-lost. Dedup-relevant data (titles, URLs, normalized company names, dates) is present in episodic memory for the next run regardless of delivery outcome.

_Test Scenario 2 - Reject path does not pollute memory._ Simulate: HITL Reject action. Expected: Episodic Memory Writer does not execute. Findings are discarded and logged. No dedup-relevant data from a rejected briefing enters episodic memory.

_Test Scenario 3 - Approve/Edit path writes correctly._ Simulate: HITL Approve and HITL Edit actions. Expected: Episodic Memory Writer executes before Delivery in both cases. If Edit was used, the edited content - not the original draft - is what gets persisted.

**HITL Interrupt/Resume**

Purpose: validate the graph correctly pauses and resumes across the human review step.

_Test Scenario 4 - Interrupt persists and resumes correctly._ Simulate: interrupt() triggered, process restarted or delayed before resume. Expected: graph state persists correctly across the pause. Resume on Approve/Edit/Reject produces the correct downstream behavior per Scenarios 1-3. No state loss, no duplicate execution of upstream nodes on resume.

**Pass Threshold**

No unhandled exception in any scenario. Reject path: 0% episodic memory writes. Approve/Edit path: 100% episodic memory writes before the delivery attempt, regardless of delivery success.

**Procedural Memory Updater - deferred**

Procedural memory updates are Phase 3 functionality. Phase 1-2 define the mechanism but do not exercise it in production. Evaluation criteria - minimum-5-signal threshold behavior, source-weight floor at 0.3, deterministic-only aggregation - will be specified before Phase 3 begins, not before this freeze. Noted here as an intentional deferral, not an omission.

## 14\. END-TO-END SYSTEM EVALUATION _(revised - critical nodes defined)_

Dataset: Weekly Briefing Dataset

**Workflow**

Research → Freshness → Entity Extraction → Scope Filter → Trust Scoring → Dedup → Synthesis → HITL → Episodic Memory Writer → Delivery

**Critical vs. Recoverable Nodes**

Per Architecture.md's recoverable/non-recoverable failure table:

- **Critical (non-recoverable):** Synthesis (no briefing possible without it - failure aborts the run); Gmail Delivery auth (failure flags the run for human attention, even though Episodic Memory Writer has already persisted the run's data).
- **Recoverable/degradable:** the four research source nodes (Tavily, YC, HN, RSS) individually; per-item Entity Extraction failures (skip item, continue run).

**Success Definition**

Success does NOT require every source to succeed. Signal is intentionally designed for graceful degradation.

Success means: run completes, briefing generated, no unhandled exceptions, critical nodes (above) succeed, source failures handled correctly.

Permitted: individual source failures, YC fallback activation, retry exhaustion on non-critical sources.

Not permitted: run termination, missing briefing, unhandled exceptions.

**Pass Threshold**

100% successful completion under the above definition.

## 15\. REGRESSION TESTING POLICY

Run Fast Regression Validation:

- After every meaningful implementation change
- Before merge

Run Full Evaluation:

- Prompt changes
- Model changes
- Threshold changes
- Release candidates
- Production deployment

## 16\. FAILURE HANDLING

If any evaluation fails:

- Stop implementation
- Do not merge
- Document failure
- Create remediation task
- Re-run evaluation

No component may bypass evaluation.

## 17\. PRODUCTION READINESS CRITERIA _(revised - Episodic Memory/HITL added)_

Signal is production-ready only if:

- Entity Extraction passes
- Dedup passes (Phase-appropriate thresholds)
- Freshness Validation passes
- Scope Filter passes
- YC Resilience passes
- Runtime Guardrails pass
- Synthesis passes
- Episodic Memory & HITL evaluation passes
- End-to-End evaluation passes

Failure of any category means Signal is not production-ready.

Evaluation results override subjective opinion.