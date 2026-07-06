# GOLDEN_RUN_SPEC.md

Project: Signal

Status: Frozen Specification

Purpose:

Define the requirements for golden_run.py.

This file defines the fast regression suite that executes after meaningful implementation changes.

It is not a replacement for EVAL.md.

It is a regression detector.

# PRIMARY OBJECTIVE

Detect:

- Regressions
- Contract violations
- Architecture violations
- State schema breakages
- Node ordering drift
- Guardrail removal

within seconds.

golden_run.py must be:

- Fast
- Cheap
- Deterministic
- Repeatable

# RELATIONSHIP TO EVAL.md

| **System**    | **Purpose**          |
| ------------- | -------------------- |
| golden_run.py | Regression detection |
| EVAL.md       | Quality validation   |

golden_run.py answers:

"Did we break something?"

EVAL.md answers:

"Is it good enough?"

# EXECUTION TRIGGERS

Run after:

- Node implementation
- Refactor
- Bug fix
- Prompt wiring change
- State schema change
- Reducer change

Run before:

- Merge
- Builder Agent completion

# EXECUTION TIME TARGET

Maximum:

60 seconds

Target:

< 30 seconds

# COST TARGET

Maximum:

\$0.05

Preferred:

\$0.01

If cost exceeds threshold:

Golden Run fails.

# DATASET SIZE

Golden Run uses:

10 findings

Only.

Not Dataset A-F.

Those belong to EVAL.md.

# DATASET COMPOSITION

| **Type**            | **Count** |
| ------------------- | --------- |
| Valid Funding       | 4         |
| Duplicate Story     | 2         |
| Non-Duplicate Story | 2         |
| Stale Story         | 1         |
| Out-of-Scope Story  | 1         |

Total:

10 findings

Dataset is frozen.

# LOCATION

validation/golden/  
├── golden_input.json  
├── golden_expected.json  
└── malformed_entity.json

# GOVERNANCE

golden_input.json and golden_expected.json are versioned together.

Any dataset modification requires:

- Update both files
- Validation rerun
- DECISIONS.md entry
- Version increment

Dataset changes must never be used to make tests pass.

Fix the implementation.

Do not weaken the benchmark.

# REQUIRED TESTS

## TEST 1

Graph Compilation

Purpose:

Detect graph construction failures.

Pass:

- Graph builds successfully
- Nodes register correctly

## TEST 2

SignalState Validation

Purpose:

Detect state contract violations.

Pass:

- SignalState validates
- Reducers validate
- State schema loads successfully

## TEST 2A

Execution Order Validation

Purpose:

Protect frozen architecture ordering.

Assert execution order matches:

Configuration  
→ Search Planner  
→ Research  
→ Reducer  
→ Freshness  
→ Entity Extraction  
→ Scope Filter  
→ Trust Scoring  
→ Dedup  
→ Synthesis  
→ HITL  
→ Episodic Memory  
→ Delivery  
→ Metrics  
→ Feedback

Any ordering drift:

FAIL.

## TEST 3

Node Execution

Purpose:

Detect runtime failures.

Pass:

All active nodes execute successfully.

## TEST 3A

YC Fallback Chain

Purpose:

Protect mandatory resilience behavior.

Scenario:

Mock YC scrape failure.

Assertions:

- YC scrape fails
- Tavily fallback executes
- Failure logged
- Run continues
- Briefing still generated

Any missing fallback:

FAIL.

## TEST 3B

MAX_FINDINGS_PER_RUN Guardrail

Purpose:

Protect cost controls.

Scenario:

Input exceeds maximum findings limit.

Assertions:

- Processing capped
- Excess findings skipped
- Log entry created

Any bypass:

FAIL.

## TEST 3C

MAX_RUN_COST_USD Guardrail

Purpose:

Protect runtime spend.

Scenario:

Simulated cost exceeds configured threshold.

Assertions:

- Processing stops
- Guardrail activates
- Event logged

Any bypass:

FAIL.

## TEST 4

Freshness Validation

Purpose:

Detect incorrect filtering.

Assertions:

- Stale story removed
- Remaining stories preserved

## TEST 5

Scope Filter Validation

Purpose:

Detect incorrect filtering.

Assertions:

- Out-of-scope finding removed
- In-scope findings preserved

## TEST 6

Entity Extraction Contract

Purpose:

Protect EntityData schema.

Required Fields:

- company_name
- company_name_normalized
- investor_names_normalized
- announced_date
- category

Assertions:

- Schema valid
- Required fields present
- Normalized fields generated

Missing field:

FAIL.

## TEST 6A

Malformed Entity Rejection

Purpose:

Protect Pydantic validation layer.

Input:

malformed_entity.json

Assertions:

- Rejected
- Logged
- Not propagated downstream

Any propagation:

FAIL.

## TEST 7

Dedup Validation

Purpose:

Protect duplicate detection.

Assertions:

Duplicate group collapses correctly.

## TEST 7A

Dedup Phase Protection

Phase 1 Assertions:

- No embedding API calls made
- Exact-match stages execute

Phase 2+ Assertions:

- Embedding subsystem available
- Embedding stage executes when enabled

This test validates architecture phase boundaries.

## TEST 8

Synthesis Generation

Purpose:

Detect briefing generation failures.

Pass:

- Briefing generated successfully

No quality scoring performed.

Quality belongs to EVAL.md.

## TEST 9

HITL Approve Path

Purpose:

Protect approval workflow.

Assertions:

- Approve path exists
- Resume path exists
- Workflow continues correctly

## TEST 9A

HITL Reject Path

Purpose:

Prevent memory pollution.

Assertions:

- Reject path executes
- Briefing discarded
- No memory write occurs

Any memory write:

FAIL.

## TEST 10

Memory Contract

Purpose:

Protect episodic memory guarantees.

Assertions:

- Approved findings persisted
- Persistence successful

## TEST 10A

Memory Before Delivery

Purpose:

Protect DEC-004.

Assertions:

memory_write_timestamp  
<  
delivery_attempt_timestamp

or equivalent execution ordering proof.

Any reversal:

FAIL.

## TEST 11

Metrics Contract

Purpose:

Protect observability.

Assertions:

Required counters exist:

- findings_dropped_freshness
- findings_dropped_scope
- findings_dropped_dedup

Missing metric:

FAIL.

# REQUIRED ASSERTIONS

golden_expected.json contains frozen expected outputs.

Example:

{  
"input_findings": 10,  
"freshness_drops": 1,  
"scope_drops": 1,  
"duplicate_groups": 1,  
"surviving_findings": 7,  
"briefing_generated": true  
}

Actual values are determined when the frozen dataset is created.

Expected values are derived from the dataset itself and must remain synchronized with it.

# FAILURE POLICY

If any test fails:

Exit Code:

1

Output:

FAILED

Include:

- failing test
- expected value
- actual value
- runtime

Execution stops immediately.

# SUCCESS POLICY

Exit Code:

0

Output:

PASSED

Include:

- runtime
- findings processed
- tests executed

Cost Reporting:

If actual API cost information is available:

- Report actual spend

Otherwise:

- Report estimated spend
- Mark as ESTIMATED

# ARCHITECTURE PROTECTION

golden_run.py must fail if:

- SignalState changes unexpectedly
- Required nodes disappear
- Node order changes
- Guardrails disappear
- YC fallback disappears
- State contracts break
- Memory ordering changes

Architecture drift is failure.

# CURSOR INTEGRATION

Before marking a task COMPLETE:

Builder Agent must:

- Run golden_run.py
- Confirm PASS
- Attach result summary

If golden_run.py fails:

Task remains IN_PROGRESS.

# DEFINITION OF SUCCESS

golden_run.py is successful if:

- Executes in under 60 seconds
- Uses frozen dataset
- Produces deterministic results
- Detects architecture regressions
- Detects state contract regressions
- Detects node execution failures
- Detects guardrail removal
- Detects resilience regressions

It is intentionally NOT a quality benchmark.

Quality remains the responsibility of EVAL.md.