# Validation Dataset README

## Purpose

The `validation/` directory contains the frozen evaluation datasets used to validate Signal's Tier 2 nodes.

These datasets are the human-approved source of truth for evaluation.

They are **not** production data.

They are **not** training data.

They must remain deterministic and reproducible.

---

# Ownership

Owner: Human

Status: Frozen after H-001 approval

Any modification after freezing requires an explicit review and approval before being committed.

---

# Validation Datasets

| File                          | Purpose                                    |
| ----------------------------- | ------------------------------------------ |
| `entity_extraction_gold.json` | Entity Extraction evaluation (Dataset A)   |
| `dedup_duplicates.json`       | Confirmed duplicate evaluation (Dataset B) |
| `dedup_false_positives.json`  | False-positive protection (Dataset C)      |
| `freshness_gold.json`         | Freshness Validation evaluation            |
| `scope_filter_gold.json`      | Scope Filter evaluation                    |
| `synthesis_gold.json`         | Weekly Briefing / Synthesis evaluation     |

---

# Evaluation Order

Validation follows the production pipeline.

Freshness Validation

↓

Entity Extraction

↓

Scope Filter

↓

Source Trust

↓

Hybrid Dedup

↓

Synthesis

Datasets must never assume a different node order.

---

# Dataset A — Entity Extraction

Purpose

Evaluate Prompt v3 extraction quality.

Validation checks include:

* Company extraction
* Founder extraction
* Investor extraction
* Funding amount
* Funding stage
* Sector
* Location
* Date extraction
* Entity normalization
* Category assignment

Human reviewers compare model output against the expected ground truth.

Passing threshold is defined in EVAL.md.

---

# Dataset B — Confirmed Duplicates

Purpose

Validate Hybrid Dedup.

Each record contains a confirmed duplicate group.

Each group includes metadata indicating the applicable evaluation phase.

## Phase Fields

```json
{
  "phase": 1,
  "phase_1_eval": true
}
```

### Phase 1

Evaluate only records where:

```text
phase_1_eval == true
```

These represent deterministic duplicate stages only:

* pre_filter
* url_match
* title_match

### Phase 2

Evaluate all records.

Phase 2 includes:

* embedding_similarity

Embedding-based duplicate groups must be excluded from Phase 1 scoring.

---

# Dataset C — False Positives

Purpose

Verify that different companies or genuinely distinct stories are **not** incorrectly merged.

Each record contains:

* `pair_id`
* `finding_a`
* `finding_b`

Evaluation is performed per pair.

Expected result:

Both findings remain independent.

No duplicate should be created.

---

# Freshness Dataset

Purpose

Validate deterministic freshness filtering.

Freshness datasets use relative date semantics.

Example:

```json
{
  "published_date_offset_days": -7
}
```

Evaluation runners must resolve offsets using a single evaluation reference date.

Example:

```
resolved_date = reference_date + offset_days
```

The same reference date must be used for every record in the evaluation run.

---

# Scope Filter Dataset

Purpose

Validate deterministic scope filtering.

Inputs use the production `ScoredFinding` schema.

Important:

`category` belongs to the top-level finding.

It is **not** part of `EntityData`.

---

# Synthesis Dataset

Purpose

Evaluate weekly briefing quality.

Validation includes:

* Executive Summary
* Funding Highlights
* Market Trends
* Watchlist

Human reviewers score outputs using EVAL.md.

---

# Determinism Requirements

Validation datasets must remain deterministic.

Do not include:

* Current dates
* Random values
* Time-dependent expectations
* Environment-specific values

Where dates are required, use relative offsets or fixed historical values as documented.

---

# Evaluation Harness Rules

## Dataset B

Phase 1:

Evaluate only:

```text
phase_1_eval == true
```

Phase 2:

Evaluate all duplicate groups.

---

## Dataset C

Iterate by:

```text
pair_id
```

Compare:

* finding_a
* finding_b

Expected outcome:

```text
expected_duplicate = false
```

---

## Freshness

Resolve:

```text
published_date_offset_days
```

using one evaluation reference date for the entire run.

---

# Document Alignment

Current project authority:

1. DECISIONS.md
2. ARCHITECTURE.md
3. BUILD_SPEC.md
4. PRD.md
5. TASKS.md
6. CURRENT_PHASE.md
7. CURSOR_RULES.md
8. EVAL.md

If documentation conflicts occur, follow the project Source of Truth hierarchy.

---

# Maintenance Rules

Do not modify datasets during Builder tasks.

Do not modify datasets to make failing implementations pass.

If a dataset defect is discovered:

1. Stop implementation.
2. Raise the issue to the human reviewer.
3. Correct the dataset through an approved validation update.
4. Re-freeze the dataset before resuming implementation.

---

# Freeze Status

These datasets are intended to remain stable throughout project implementation.

Any future additions should:

* preserve deterministic evaluation,
* remain aligned with BUILD_SPEC,
* remain aligned with ARCHITECTURE,
* remain aligned with TASKS and EVAL,
* avoid introducing phase-specific ambiguity.

Production code should adapt to the documented project architecture—not to the validation datasets.

