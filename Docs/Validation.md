# validation/README.md

Project: Signal

Status: Validation Dataset Specification

Purpose:

Define the structure, ownership, and requirements of all validation datasets used by EVAL.md.

This directory is the source of truth for validation inputs.

Datasets are frozen assets.

They are not modified to make evaluations pass.

Any dataset modification requires:

- Human approval
- DECISIONS.md entry
- Dataset version increment

# DIRECTORY STRUCTURE

validation/  
├── README.md  
├── schemas/  
│  
├── funding_articles/  
├── duplicate_groups/  
├── non_duplicates/  
├── freshness_cases/  
├── scope_filter_cases/  
└── briefing_dataset/

# DATASET OWNERSHIP

Human Responsibilities:

- Source collection
- Ground truth verification
- Dataset approval

Agent Responsibilities:

- Dataset formatting
- Schema validation
- Evaluation execution

Agents may not invent validation data.

Agents may not alter validation data.

# DATASET A

Directory:

validation/funding_articles/

Purpose:

Entity Extraction evaluation.

Referenced By:

- EVAL.md Section 5

Target Size:

25 articles

Required Sources:

- Inc42
- YourStory
- Economic Times
- YC announcements

Ground Truth Required:

{  
"company_name": "",  
"company_name_normalized": "",  
"founder_name": \[\],  
"investor_names": \[\],  
"investor_names_normalized": \[\],  
"funding_amount_usd": 0,  
"funding_stage": "",  
"sector": "",  
"location": "",  
"announced_date": "",  
"category": ""  
}

Pass Criteria:

Defined in EVAL.md.

# DATASET B

Directory:

validation/duplicate_groups/

Purpose:

Dedup evaluation.

Referenced By:

- EVAL.md Section 6

Target Size:

20 duplicate groups

Definition:

Multiple articles describing the same event.

Requirements:

Each group must contain:

- Different publication
- Different URL
- Different title

Ground Truth Required:

{  
"group_id": "",  
"canonical_company": "",  
"canonical_event": "",  
"members": \[\]  
}

# DATASET C

Directory:

validation/non_duplicates/

Purpose:

False-positive prevention.

Referenced By:

- EVAL.md Section 6

Target Size:

20 stories

Definition:

Articles that must never be classified as duplicates.

Ground Truth Required:

{  
"article_id": "",  
"company": "",  
"event": ""  
}

# DATASET D

Directory:

validation/freshness_cases/

Purpose:

Freshness Validation evaluation.

Referenced By:

- EVAL.md Section 7

Target Size:

20 cases

Required Coverage:

- Recent
- Stale
- Republished
- Missing date
- Ambiguous date

Ground Truth Required:

{  
"case_id": "",  
"expected_result": "",  
"reason": ""  
}

Expected Results:

RETAIN  
DROP  
RETAIN_WITH_PENALTY

# DATASET E

Directory:

validation/scope_filter_cases/

Purpose:

Scope Filter evaluation.

Referenced By:

- EVAL.md Section 8

Target Size:

20 cases

Coverage:

- Indian startup
- Non-Indian startup
- Funding below threshold
- Funding above threshold
- Series C+
- Missing fields

Ground Truth Required:

{  
"case_id": "",  
"expected_result": "",  
"reason": ""  
}

Expected Results:

RETAIN  
DROP

# DATASET F

Directory:

validation/briefing_dataset/

Purpose:

Synthesis evaluation.

Referenced By:

- EVAL.md Section 12
- EVAL.md Section 14

Target Size:

50 findings

Coverage:

- Funding
- Hiring
- Accelerator
- Founder Move
- Pivot
- Shutdown
- Ecosystem Trend

Ground Truth Required:

{  
"finding_id": "",  
"priority": "",  
"expected_category": "",  
"expected_summary": ""  
}

# SCHEMAS

Directory:

validation/schemas/

Purpose:

Validation dataset schema definitions.

Files:

entity_extraction.schema.json  
duplicate_group.schema.json  
freshness_case.schema.json  
scope_filter_case.schema.json  
briefing_item.schema.json

All validation data must pass schema validation.

# VERSIONING

Current Version:

v1

Version Format:

v1  
v2  
v3

Dataset changes require version increment.

# CHANGE CONTROL

Dataset changes are allowed only when:

- New evaluation requirement introduced
- Existing dataset proven incorrect
- Human approval granted

Dataset modifications must never be used to artificially improve evaluation scores.

# FREEZE RULE

Validation datasets are considered production assets.

Passing evaluation by changing validation data is prohibited.

Fix the implementation.

Do not change the benchmark.