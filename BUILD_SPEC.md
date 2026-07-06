# Signal - Build Spec 

## Node-by-Node Execution Guide | 2-Week Sprint

**Revision note:** This version fixes 9 gaps found during review of v1 - missing Reducer node, missing retry policy, hardcoded YC batch, missing test fixtures, missing Phase 1 memory/metrics stubs, missing embedding dedup session, missing graph_version and source_health persistence, and an unstated memory-before-delivery ordering rule. Details of each fix are marked inline with \[FIX\] tags so you can see exactly what changed and why.

## How to Use This Document

This is your single source of truth for building Signal. Every session has one job. You finish the job, run the checkpoint, and only then move to the next session.

**Rules that do not bend:**

- Never start a new session until the checkpoint for the current one passes
- Never write code for Session N+1 inside Session N
- Every prompt you paste into Cursor must include the context block at the top of each session
- If a checkpoint fails, fix it before moving forward - do not skip and "come back to it"

## How to Prompt the LLM Effectively

Before you start Session 1, read this once. These rules apply to every prompt you write in Cursor throughout the entire build.

**Rule 1 - Always open with context.**  
Every prompt starts with what already exists. Paste the relevant file or the relevant function before asking the LLM to write something new. If you skip this, the LLM invents code that conflicts with what you have.

**Rule 2 - One task per prompt.**  
Do not ask the LLM to write the node AND write the test AND update the state schema in the same prompt. Ask for one thing. Verify it. Then ask for the next.

**Rule 3 - Be explicit about the output format.**  
Tell the LLM exactly what you want back. "Write a Python function called run_freshness_validation that takes state: SignalState as input and returns SignalState. Do not write a class. Do not add any imports I haven't listed. Return only the function."

**Rule 4 - Paste the SignalState schema in every node prompt.**  
The LLM cannot see your other files unless you paste them. Every node prompt must include the relevant TypedDict definitions so the LLM uses the exact field names you have defined.

**Rule 5 - When something breaks, paste the full error.**  
Do not describe the error. Paste the exact traceback. Then paste the exact code that caused it. Ask the LLM to fix only that specific error without rewriting anything else.

**Rule 6 - The spec is what you build. Not more.**  
If the LLM adds extra features, logging, helper classes, or abstractions you didn't ask for, reject them. Ask it to remove them. Scope creep from the LLM is the most common reason builds break.

## Project Directory Structure

Set this up in Session 0. Every file created in every session goes into this structure.

signal/  
├── .env # All API keys. Never commit this.  
├── .env.example # Keys without values. Commit this.  
├── .gitignore  
├── requirements.txt  
├── README.md  
│  
├── agent/  
│ ├── \__init_\_.py  
│ ├── state.py # SignalState, all TypedDicts, ErrorCode, constants  
│ ├── graph.py # The LangGraph StateGraph - wired in Session 10  
│ │  
│ ├── nodes/  
│ │ ├── \__init_\_.py  
│ │ ├── config_loader.py  
│ │ ├── search_planner.py  
│ │ ├── tavily_search.py  
│ │ ├── yc_api.py  
│ │ ├── hn_algolia.py  
│ │ ├── google_news_rss.py  
│ │ ├── reducer.py # \[FIX Gap 1\] Now has its own session  
│ │ ├── freshness_validation.py  
│ │ ├── entity_extraction.py  
│ │ ├── scope_filter.py  
│ │ ├── source_trust_scoring.py  
│ │ ├── hybrid_dedup.py  
│ │ ├── synthesis.py  
│ │ ├── episodic_memory_writer.py # \[FIX Gap 8\] Phase 1 stub built in Week 1  
│ │ └── run_metrics_writer.py # \[FIX Gap 9\] Phase 1 stub built in Week 1  
│ │  
│ └── prompts/  
│ └── entity_extraction_v3.txt # The validated prompt from Spike 2  
│  
├── tests/  
│ ├── \__init_\_.py  
│ └── fixtures/  
│ └── sample_findings.py # \[FIX Recommendation\] Built in Session 0.5  
│  
└── scripts/  
└── run_agent.py # Manual trigger for local runs

## Week 1 - Phase 1: One Working Run

### SESSION 0 - Environment Bootstrap

**Time estimate: 2-3 hours**  
**Goal: Project exists, Python runs, LangSmith is connected, nothing else.**

#### Step 0.1 - Install Python and create the project

Open your terminal. Run these commands one at a time:

\# Check Python version - must be 3.11 or higher  
python3 --version  
<br/>\# Create project folder  
mkdir signal && cd signal  
<br/>\# Create virtual environment  
python3 -m venv venv  
<br/>\# Activate it (Mac/Linux)  
source venv/bin/activate  
<br/>\# Confirm you are in the venv - should show (venv) in terminal prompt

#### Step 0.2 - Create requirements.txt

Create requirements.txt in the project root with exactly this content:

langgraph==0.2.50  
langchain-openai==0.2.10  
langsmith==0.1.147  
tavily-python==0.5.0  
feedparser==6.0.11  
httpx==0.27.2  
python-dotenv==1.0.1  
pydantic==2.9.2  
openai==1.54.0

Then install:

pip install -r requirements.txt

If any package fails to install, paste the exact error into Cursor and ask it to fix only the requirements.txt - do not change anything else.

#### Step 0.3 - Create .env file

Create .env in the project root:

OPENAI_API_KEY=your_key_here  
TAVILY_API_KEY=your_key_here  
LANGCHAIN_TRACING_V2=true  
LANGCHAIN_API_KEY=your_key_here  
LANGCHAIN_PROJECT=signal-agent  
GRAPH_VERSION=1.0

**Where to get each key:**

- OpenAI: platform.openai.com → API Keys
- Tavily: app.tavily.com → sign up free → API Keys
- LangSmith: smith.langchain.com → sign up free → Settings → API Keys → Create API Key → name it "signal-local"

Create .env.example with the same keys but empty values. Add .env to .gitignore.

#### Step 0.4 - Create .gitignore

venv/  
.env  
\__pycache_\_/  
\*.pyc  
.DS_Store

#### Step 0.5 - Create the directory structure

mkdir -p agent/nodes agent/prompts tests/fixtures scripts  
touch agent/\__init_\_.py agent/nodes/\__init_\_.py tests/\__init_\_.py

#### Step 0.6 - Verify LangSmith connection

Create scripts/test_langsmith.py:

import os  
from dotenv import load_dotenv  
load_dotenv()  
<br/>from langsmith import Client  
<br/>client = Client()  
print("LangSmith connected:", client.list_projects())

Run it:

python scripts/test_langsmith.py

You should see your project listed. If you see an auth error, your LANGCHAIN_API_KEY is wrong - re-copy it from smith.langchain.com.

#### Step 0.7 - Initialize git

git init  
git add .  
git commit -m "chore: project bootstrap"

**SESSION 0 CHECKPOINT - Do not proceed until all pass:**

- python3 --version shows 3.11+
- pip install -r requirements.txt completed with no errors
- .env file exists with all four keys filled in
- python scripts/test_langsmith.py prints without error
- Directory structure matches the spec above exactly
- First git commit made

### SESSION 0.5 - Test Fixtures \[FIX - Recommendation\]

**Time estimate: 45 minutes**  
**Goal: One file of reusable sample data that every later test session imports from, instead of each session writing its own ad-hoc test dicts.**

This session did not exist in v1 of this spec. Every test session from here on will import from this file rather than redefining sample findings inline. This saves time across roughly 8 later sessions and keeps test data consistent.

**Prompt to paste into Cursor:**

I am building a LangGraph agent called Signal. I need reusable test fixtures.  
<br/>Here is RawFinding TypedDict (paste it).  
Here is EntityData TypedDict (paste it).  
Here is ScoredFinding TypedDict (paste it).  
<br/>Write \`tests/fixtures/sample_findings.py\` containing these module-level constants:  
<br/>1\. SAMPLE_FUNDING_FINDING - a RawFinding dict representing a real-looking funding article:  
title: "Bengaluru fintech startup PayNova raises \$8M Series A led by Elevation Capital"  
summary: "PayNova, a Bengaluru-based fintech platform, announced an \$8 million Series A round led by Elevation Capital with participation from existing investors in March 2025."  
source_url: "<https://inc42.com/buzz/paynova-series-a>"  
source_name: "inc42"  
published_date: "2025-03-10"  
<br/>2\. SAMPLE_HIRING_FINDING - a RawFinding dict about hiring signal:  
title: "AI startup Sarvam doubles engineering team in Q1 2025"  
summary: "Sarvam AI has grown its engineering headcount from 20 to 45 in the first quarter, with a focus on hiring NLP researchers."  
source_url: "<https://yourstory.com/sarvam-hiring>"  
source_name: "yourstory"  
published_date: "2025-04-01"  
<br/>3\. SAMPLE_SHUTDOWN_FINDING - a RawFinding dict about a shutdown:  
title: "Quick commerce startup Dunzo shuts down operations after funding crunch"  
summary: "Dunzo has officially ceased operations citing inability to raise further funding amid a prolonged cash crunch."  
source_url: "<https://economictimes.indiatimes.com/dunzo-shutdown>"  
source_name: "economictimes"  
published_date: "2025-02-15"  
<br/>4\. SAMPLE_ACCELERATOR_FINDING - a RawFinding dict about YC acceptance:  
title: "Chennai-based logistics startup RouteBox accepted into YC W25 batch"  
summary: "RouteBox, a logistics optimization startup from Chennai, has been accepted into Y Combinator's Winter 2025 batch."  
source_url: "<https://ycombinator.com/companies/routebox>"  
source_name: "yc"  
published_date: "2025-01-20"  
<br/>5\. SAMPLE_OLD_FINDING - a RawFinding dict that is more than 30 days old relative to today (use a fixed date 60 days before this fixture file was created - hardcode as "2024-11-01"):  
title: "Old funding round republished by aggregator"  
summary: "This is a stale story that should be dropped by freshness validation."  
source_url: "<https://aggregator-site.com/old-story>"  
source_name: "rss_other"  
published_date: "2024-11-01"  
<br/>6\. SAMPLE_UNDATED_FINDING - a RawFinding dict with published_date set to None:  
title: "Startup news with no parseable date"  
summary: "This finding has no date and should be penalized but not dropped."  
source_url: "<https://example.com/undated>"  
source_name: "hn"  
published_date: None  
<br/>7\. SAMPLE_OUT_OF_SCOPE_FINDING - a ScoredFinding dict (full shape, all fields populated) representing a non-Indian company that should be dropped by scope filter:  
\- All base fields filled with placeholder text  
\- entities.location: "San Francisco"  
\- entities.funding_amount_usd: 5000000  
\- entities.funding_stage: "series_a"  
\- category: "funding"  
\- source_trust_score: 0.9  
\- freshness_penalty_applied: False  
\- confidence_score: 0.9  
\- is_duplicate: False  
\- duplicate_reason: None  
<br/>8\. SAMPLE_SCORED_FUNDING_FINDING - a ScoredFinding dict (full shape) representing a valid, in-scope, fully-populated finding for India:  
\- Based on SAMPLE_FUNDING_FINDING's base fields  
\- entities.company_name: "PayNova"  
\- entities.company_name_normalized: "paynova"  
\- entities.funding_amount_usd: 8000000  
\- entities.funding_stage: "series_a"  
\- entities.location: "Bengaluru"  
\- entities.announced_date: "2025-03-10"  
\- category: "funding"  
\- source_trust_score: 0.90  
\- freshness_penalty_applied: False  
\- confidence_score: 0.90  
\- is_duplicate: False  
\- duplicate_reason: None  
<br/>9\. ALL_SAMPLE_RAW_FINDINGS - a list containing fixtures 1 through 4 (the four category examples) for tests that need multiple findings at once.  
<br/>Write each as a plain Python dict literal matching the TypedDict shape exactly. No functions, no classes, no fixtures using pytest decorators - just plain importable dicts and one list.

Test the fixtures import cleanly:

\# tests/test_fixtures.py  
from tests.fixtures.sample_findings import (  
SAMPLE_FUNDING_FINDING, SAMPLE_HIRING_FINDING, SAMPLE_SHUTDOWN_FINDING,  
SAMPLE_ACCELERATOR_FINDING, SAMPLE_OLD_FINDING, SAMPLE_UNDATED_FINDING,  
SAMPLE_OUT_OF_SCOPE_FINDING, SAMPLE_SCORED_FUNDING_FINDING, ALL_SAMPLE_RAW_FINDINGS  
)  
<br/>def test_fixtures_exist():  
assert SAMPLE_FUNDING_FINDING\["title"\]  
assert SAMPLE_UNDATED_FINDING\["published_date"\] is None  
assert SAMPLE_OUT_OF_SCOPE_FINDING\["entities"\]\["location"\] == "San Francisco"  
assert SAMPLE_SCORED_FUNDING_FINDING\["entities"\]\["location"\] == "Bengaluru"  
assert len(ALL_SAMPLE_RAW_FINDINGS) == 4  
print("Fixtures test passed.")  
<br/>if \_\_name\_\_ == "\__main_\_":  
test_fixtures_exist()

Run:

python tests/test_fixtures.py

**SESSION 0.5 CHECKPOINT:**

- tests/fixtures/sample_findings.py exists with all 9 fixtures
- python tests/test_fixtures.py prints "Fixtures test passed."
- Every later test session in this document imports from this file instead of writing inline dicts

### SESSION 1 - State Schema + Constants

**Time estimate: 1-2 hours**  
**Goal: \`agent/state.py\` exists and is importable. This is the foundation every node builds on.**

This session has zero LangGraph graph code. It is pure Python TypedDict definitions and constants.

**Prompt to paste into Cursor:**

I am building a LangGraph agent called Signal. I need you to create the file \`agent/state.py\`.  
<br/>This file must contain exactly the following and nothing else - no extra classes, no helper functions, no imports beyond what is listed:  
<br/>IMPORTS NEEDED:  
\- from typing import TypedDict, Annotated, Optional  
\- import operator  
\- from enum import Enum  
<br/>Write the following in this exact order:  
<br/>1\. ALLOWED_CATEGORIES constant - a Python list of strings:  
\["funding", "hiring", "founder_move", "accelerator", "shutdown", "pivot", "ecosystem_trend"\]  
<br/>2\. SOURCE_TRUST constant - a Python dict mapping source name strings to float values:  
yc: 1.0, techcrunch: 0.95, inc42: 0.90, yourstory: 0.90,  
economictimes: 0.85, mint: 0.85, hn: 0.70, google_news: 0.65, rss_other: 0.60  
<br/>3\. ErrorCode class - a plain Python class (not Enum) with these string constants as class attributes:  
ENTITY_EXTRACTION_FAILED, TAVILY_TIMEOUT, YC_API_UNAVAILABLE,  
DEDUP_EMBEDDING_FAILED, SYNTHESIS_FAILED, DELIVERY_FAILED, GMAIL_AUTH_FAILED  
<br/>4\. RawFinding TypedDict with fields:  
\- title: str  
\- summary: str  
\- source_url: str  
\- source_name: str  
\- published_date: Optional\[str\] # unreliable from Tavily; canonical date is in EntityData.announced_date  
<br/>5\. EntityData TypedDict with fields:  
\- company_name: Optional\[str\]  
\- company_name_normalized: Optional\[str\]  
\- founder_name: Optional\[str\]  
\- investor_names: Optional\[list\[str\]\]  
\- investor_names_normalized: Optional\[list\[str\]\]  
\- funding_amount_usd: Optional\[int\]  
\- funding_stage: Optional\[str\]  
\- sector: Optional\[str\]  
\- location: Optional\[str\]  
\- announced_date: Optional\[str\]  
<br/>6\. ScoredFinding TypedDict (not inheriting from RawFinding - copy the fields explicitly) with fields:  
\- title: str  
\- summary: str  
\- source_url: str  
\- source_name: str  
\- published_date: Optional\[str\]  
\- entities: EntityData  
\- category: str  
\- source_trust_score: float  
\- freshness_penalty_applied: bool  
\- confidence_score: float  
\- is_duplicate: bool  
\- duplicate_reason: Optional\[str\]  
<br/>7\. BriefingItem TypedDict with fields:  
\- id: str  
\- title: str  
\- summary: str  
\- source_url: str  
\- source_name: str  
\- category: str  
\- confidence_score: float  
\- entities: EntityData  
<br/>8\. SignalState TypedDict with exactly these fields in exactly these sections:  
<br/>\# Run metadata  
run_id: str  
user_id: str  
thread_id: str  
run_type: str  
graph_version: str  
<br/>\# Config  
user_config: dict  
semantic_memory: dict  
procedural_memory: dict  
query_plan: dict  
<br/>\# Research - this field MUST use Annotated with operator.add  
raw_findings: Annotated\[list\[RawFinding\], operator.add\]  
<br/>\# Processing  
scored_findings: list\[ScoredFinding\]  
new_findings: list\[ScoredFinding\]  
<br/>\# Synthesis  
briefing_draft: str  
briefing_items: list\[BriefingItem\]  
briefing_final: str  
<br/>\# HITL  
hitl_decision: Optional\[str\]  
hitl_edits: Optional\[dict\]  
<br/>\# Delivery  
delivery_status: Optional\[str\]  
<br/>\# Metrics  
sources_queried: list\[str\]  
findings_retrieved: int  
findings_dropped_freshness: int  
findings_dropped_dedup: int  
findings_dropped_scope: int  
tokens_used: int  
estimated_cost_usd: float  
run_duration_seconds: float  
<br/>\# Snapshot  
run_config_snapshot: dict  
<br/>\# Error - structured dict when a node fails, None when healthy  
error: Optional\[dict\]  
<br/>\# Source health - one boolean per source, True means it errored  
source_failures: dict  
<br/>Do not add anything beyond what I have listed. No docstrings on the TypedDicts. No \__all_\_. No if \_\_name\_\_ == "\__main_\_" block.

After Cursor generates the file, verify it manually:

- Open agent/state.py
- Confirm raw_findings uses Annotated\[list\[RawFinding\], operator.add\] - this is critical
- Confirm error is Optional\[dict\] not Optional\[str\]
- Confirm source_trust_score and freshness_penalty_applied exist in ScoredFinding

Then create tests/test_state.py:

from agent.state import (  
ALLOWED_CATEGORIES, SOURCE_TRUST, ErrorCode,  
RawFinding, EntityData, ScoredFinding, BriefingItem, SignalState  
)  
<br/>def test_allowed_categories():  
assert len(ALLOWED_CATEGORIES) == 7  
assert "funding" in ALLOWED_CATEGORIES  
assert "ecosystem_trend" in ALLOWED_CATEGORIES  
<br/>def test_source_trust():  
assert SOURCE_TRUST\["yc"\] == 1.0  
assert SOURCE_TRUST\["google_news"\] == 0.65  
<br/>def test_error_code():  
assert ErrorCode.TAVILY_TIMEOUT == "TAVILY_TIMEOUT"  
assert ErrorCode.SYNTHESIS_FAILED == "SYNTHESIS_FAILED"  
<br/>def test_imports():  
assert RawFinding is not None  
assert SignalState is not None  
<br/>if \_\_name\_\_== "\__main_\_":  
test_allowed_categories()  
test_source_trust()  
test_error_code()  
test_imports()  
print("All state tests passed.")

Run:

python tests/test_state.py

**SESSION 1 CHECKPOINT - Do not proceed until all pass:**

- agent/state.py exists and has no syntax errors
- python tests/test_state.py prints "All state tests passed."
- raw_findings field uses Annotated\[list\[RawFinding\], operator.add\]
- error field is Optional\[dict\]
- ScoredFinding has both source_trust_score and freshness_penalty_applied
- source_failures: dict exists in SignalState

### SESSION 2 - Config Loader Node

**Time estimate: 1 hour**  
**Goal: Config Loader node reads a hardcoded static config dict and returns it in state. No database, no API calls.**

**Prompt to paste into Cursor:**

I am building a LangGraph agent called Signal. I need you to write the Config Loader node.  
<br/>First, here is the SignalState TypedDict from agent/state.py (paste the full SignalState definition here).  
<br/>Write a single Python function in \`agent/nodes/config*loader.py\` called \`config_loader\`.  
<br/>The function signature must be:  
def config_loader(state: SignalState) -> dict:  
<br/>This is a LangGraph node. In LangGraph, a node takes the current state as input and returns a dict of the fields it wants to update. It does NOT return the full state - it returns only the keys it is changing.  
<br/>The function must:  
1\. Load .env variables using python-dotenv  
2\. Build a hardcoded static user_config dict with these values:  
\- user_id: "user_001"  
\- keywords: \["Indian startup", "funding India", "seed round India", "Series A India"\]  
\- verticals: \["AI", "fintech", "healthtech", "B2B SaaS", "climate", "edtech"\]  
\- stage_filter: \["seed", "series_a", "series_b"\]  
\- delivery_email: "<test@example.com>"  
\- schedule_freq: "weekly"  
3\. Return a dict with these keys updated:  
\- user_config: the dict above  
\- user_id: "user_001"  
\- thread_id: a string of "run*" + current UTC timestamp as integer  
\- run_type: "manual"  
\- graph_version: os.getenv("GRAPH_VERSION", "1.0")  
\- semantic_memory: empty dict  
\- procedural_memory: the default procedural memory JSON below  
\- source_failures: {"tavily": False, "yc": False, "hn": False, "rss": False}  
<br/>Default procedural memory to return:  
{  
"high_signal_categories": \["funding", "accelerator"\],  
"low_signal_categories": \[\],  
"trusted_sources": \["inc42", "yc"\],  
"preferred_stage": \["seed", "series_a"\],  
"query_boost_terms": \["Bengaluru", "B2B SaaS"\],  
"query_suppress_terms": \["Infosys", "Wipro", "IT services"\],  
"source_weights": {"tavily": 1.0, "yc": 1.0, "hn": 0.7, "google_news": 0.65},  
"min_confidence_threshold": 0.70  
}  
<br/>Imports allowed: os, from datetime import datetime, timezone, from dotenv import load_dotenv, from agent.state import SignalState  
<br/>Do not add logging. Do not add try/except. Do not add any other functions or classes.

Then create tests/test_config_loader.py:

from agent.state import SignalState  
from agent.nodes.config*loader import config_loader  
<br/>def test_config_loader():  
fake_state = {}  
result = config_loader(fake_state)  
<br/>assert "user_config" in result  
assert "user_id" in result  
assert result\["user_id"\] == "user_001"  
assert "thread_id" in result  
assert result\["thread_id"\].startswith("run*")  
assert "procedural_memory" in result  
assert "source_failures" in result  
assert result\["source_failures"\]\["tavily"\] == False  
assert result\["graph_version"\] == "1.0"  
print("Config loader test passed.")  
<br/>if \_\_name\_\_== "\__main_\_":  
test_config_loader()

Run:

python tests/test_config_loader.py

**SESSION 2 CHECKPOINT:**

- agent/nodes/config_loader.py exists with no syntax errors
- python tests/test_config_loader.py prints "Config loader test passed."
- thread*id starts with "run*"
- source_failures dict has four keys all set to False

### SESSION 3 - Search Planner Node \[FIX - Gap 5: dynamic YC batch\]

**Time estimate: 1 hour**  
**Goal: Search Planner reads procedural memory and outputs a query_plan dict. Deterministic, no LLM.**

**What changed from v1:** The YC batch was previously hardcoded as "batch=W25". Six months from now W25 stops being current and the agent silently goes stale. This version computes the batch dynamically from the current date, and queries the two most recent batches instead of one.

YC batches follow the pattern: January-April → Winter (W), May-August → Summer (S), September-December → Fall (F). So 2026-06 falls in Summer → S26.

**Prompt to paste into Cursor:**

I am building a LangGraph agent called Signal. I need you to write the Search Planner node.  
<br/>Here is SignalState TypedDict (paste it).  
Here is ALLOWED_CATEGORIES and SOURCE_TRUST from agent/state.py (paste them).  
<br/>Write a single function \`search_planner\` in \`agent/nodes/search_planner.py\`.  
<br/>Signature: def search_planner(state: SignalState) -> dict:  
<br/>This is a LangGraph node - return only the keys being updated, not the full state.  
<br/>FIRST, write a helper function \`get_recent_yc_batches() -> list\[str\]\` that computes YC batch codes dynamically - DO NOT hardcode a batch name anywhere:  
1\. Get current UTC year and month using datetime.now(timezone.utc)  
2\. Determine season: months 1-4 = "W" (Winter), months 5-8 = "S" (Summer), months 9-12 = "F" (Fall)  
3\. Get the two-digit year (e.g. 2026 → "26")  
4\. Build the current batch code as: season + two_digit_year (e.g. "S26")  
5\. Also compute the PREVIOUS batch (the season before current, same logic - if current is "W26" the previous is "F25")  
6\. Return a list of both batch codes, most recent first: \[current_batch, previous_batch\]  
<br/>THEN, the main function must:  
1\. Read state\["procedural_memory"\] to get query_boost_terms and query_suppress_terms  
2\. Build a query_plan dict with four keys: "tavily", "yc", "hn", "rss"  
3\. Each key maps to a list of query strings  
<br/>Tavily queries (5 queries - these are plain search strings, domains are NOT embedded here, they get passed separately as include_domains by the Tavily node):  
\- "Indian startup funding seed round this week"  
\- "India Series A funding announcement {current_month_name} {current_year}" ← compute current_month_name and current_year from datetime.now()  
\- "YC batch India founder startup"  
\- "Indian B2B SaaS startup funding"  
\- "Bengaluru Mumbai startup ecosystem news"  
<br/>Add any query_boost_terms from procedural memory as additional standalone queries, max 3 terms.  
<br/>YC queries - call get_recent_yc_batches() and build one query string per batch:  
\- For each batch code returned, add a query string: f"batch={batch_code}"  
\- This means yc queries will be like \["batch=S26", "batch=F25"\] - computed fresh every run, never hardcoded  
<br/>HN queries (3 queries):  
\- "Indian startup"  
\- "Show HN India founder"  
\- "Who is hiring India startup"  
<br/>RSS queries (2 queries - these are feed URLs):  
\- "<https://news.google.com/rss/search?q=indian+startup+funding&hl=en-IN&gl=IN&ceid=IN:en>"  
\- "<https://news.google.com/rss/search?q=India+Series+A+seed+funding&hl=en-IN&gl=IN&ceid=IN:en>"  
<br/>Also return these in the output dict:  
\- sources_queried: \["tavily", "yc", "hn", "rss"\]  
\- run_config_snapshot: {"query_plan": &lt;the query_plan&gt;, "procedural_memory": state.get("procedural_memory", {})}  
<br/>Imports allowed: from datetime import datetime, timezone, from agent.state import SignalState  
<br/>No LLM calls. No API calls. No logging. No try/except. Pure deterministic logic only.

Test:

\# tests/test_search_planner.py  
from agent.nodes.config_loader import config_loader  
from agent.nodes.search_planner import search_planner  
<br/>def test_search_planner():  
state = config_loader({})  
result = search_planner(state)  
<br/>assert "query_plan" in result  
assert "tavily" in result\["query_plan"\]  
assert "yc" in result\["query_plan"\]  
assert "hn" in result\["query_plan"\]  
assert "rss" in result\["query_plan"\]  
assert len(result\["query_plan"\]\["tavily"\]) >= 5  
assert len(result\["query_plan"\]\["hn"\]) == 3  
<br/>\# Confirm YC batch was computed dynamically, not hardcoded  
yc_queries = result\["query_plan"\]\["yc"\]  
assert len(yc_queries) == 2  
assert all(q.startswith("batch=") for q in yc_queries)  
print("Computed YC batches:", yc_queries)  
<br/>assert "sources_queried" in result  
print("Search planner test passed.")  
<br/>if \_\_name\_\_ == "\__main_\_":  
test_search_planner()

**SESSION 3 CHECKPOINT:**

- agent/nodes/search_planner.py exists with no syntax errors
- python tests/test_search_planner.py prints "Search planner test passed."
- query_plan has all four keys
- YC batch codes are computed from current date, not hardcoded - verify by reading the printed batch codes and confirming they match the current season
- Tavily queries are strings, not dicts

### SESSION 4 - Parallel Research Nodes \[FIX - Gap 6: retry policy added\]

**Time estimate: 2-3 hours**  
**Goal: All four research nodes exist, each returns raw_findings\[\], each is independently testable, and each retries on transient failure instead of giving up on the first error.**

**What changed from v1:** Every node now wraps its external call in a retry loop. This matches the PRD's Retry Policy table - 2 retries for Tavily/YC/HN, 1 retry for RSS, with short fixed backoff. This is the simplified Phase 1 version; the PRD's full backoff schedule (5s, 15s) is used here directly since Phase 1 doesn't need anything more sophisticated.

Write each node one at a time. Test each one before writing the next.

**Prompt for Tavily node (\`agent/nodes/tavily_search.py\`):**

I am building a LangGraph agent called Signal. Write the Tavily Search node.  
<br/>Here is RawFinding TypedDict (paste it).  
Here is SignalState TypedDict (paste it).  
Here is ErrorCode class (paste it).  
<br/>Write a single function \`tavily_search\` in \`agent/nodes/tavily_search.py\`.  
<br/>Signature: def tavily_search(state: SignalState) -> dict:  
<br/>This function must:  
1\. Get queries from state\["query_plan"\]\["tavily"\] - this is a list of strings  
2\. For each query, call the Tavily API using the tavily-python client, WITH RETRY:  
\- Attempt the call up to 3 times total (1 initial + 2 retries)  
\- Wait 5 seconds before retry 1, 15 seconds before retry 2 (use time.sleep)  
\- If all 3 attempts fail for a given query, skip that query and continue to the next one - do not abort the whole node  
3\. CRITICAL: Every Tavily search call must include include_domains parameter:  
include_domains=\["inc42.com", "yourstory.com", "economictimes.indiatimes.com", "entrackr.com", "techcrunch.com", "livemint.com", "thehindu.com"\]  
4\. Use search_depth="advanced" and max_results=5 per query  
5\. For each result returned, create a RawFinding dict with:  
\- title: result\["title"\]  
\- summary: result.get("content", "")\[:500\]  
\- source_url: result\["url"\]  
\- source_name: extract domain from URL (e.g. "inc42.com" → "inc42")  
\- published_date: result.get("published_date", None)  
6\. Collect all RawFinding dicts into a list called findings  
7\. Return {"raw_findings": findings, "source_failures": {\*\*state.get("source_failures", {}), "tavily": &lt;True if every single query failed all 3 attempts, else False&gt;}}  
<br/>Structure the retry as a small helper function \`\_call_with_retry(client, query, include_domains, max_attempts=3)\` that returns the results list or None if all attempts failed. Use it inside the main loop.  
<br/>Print a line for each failed attempt: f"Tavily query '{query}' failed attempt {attempt}, retrying..."  
<br/>Imports allowed: os, time, from tavily import TavilyClient, from urllib.parse import urlparse, from dotenv import load_dotenv, from agent.state import SignalState, RawFinding  
<br/>The TavilyClient is initialized as: client = TavilyClient(api_key=os.getenv("TAVILY_API_KEY"))  
Call it as: results = client.search(query=query, search_depth="advanced", max_results=5, include_domains=\[...\])  
The results are in results\["results"\] - a list of dicts.  
<br/>No logging library. Print only.

Test Tavily immediately after writing it:

\# tests/test_tavily.py  
from agent.nodes.config_loader import config_loader  
from agent.nodes.search_planner import search_planner  
from agent.nodes.tavily_search import tavily_search  
<br/>def test_tavily():  
state = config_loader({})  
state.update(search_planner(state))  
result = tavily_search(state)  
<br/>print(f"Tavily returned {len(result\['raw_findings'\])} findings")  
if result\["raw_findings"\]:  
print("First finding:", result\["raw_findings"\]\[0\]\["title"\])  
print("Source:", result\["raw_findings"\]\[0\]\["source_name"\])  
assert "raw_findings" in result  
print("Tavily test passed.")  
<br/>if \_\_name\_\_ == "\__main_\_":  
test_tavily()

This makes a real API call. You should see real Indian startup headlines. If you see 0 results, your include_domains is filtering everything - check the domain names.

**Prompt for YC node (\`agent/nodes/yc_api.py\`):**

Write the YC API node for the Signal agent.  
<br/>Here is RawFinding TypedDict (paste it).  
Here is SignalState TypedDict (paste it).  
<br/>Write a single function \`yc_api_node\` in \`agent/nodes/yc_api.py\`.  
<br/>Signature: def yc_api_node(state: SignalState) -> dict:  
<br/>This function fetches recent YC batches and filters for Indian-founded companies.  
<br/>Use state\["query_plan"\]\["yc"\] for the list of batch query strings (e.g. \["batch=S26", "batch=F25"\]) - DO NOT hardcode any batch name here. Parse the batch code out of each query string (it follows "batch=").  
<br/>Steps:  
1\. For each batch query string in state\["query_plan"\]\["yc"\]:  
a. Extract the batch code (the part after "batch=")  
b. Fetch with retry (up to 3 attempts, 5s then 15s backoff, same pattern as Tavily node):  
<https://api.ycombinator.com/v0.1/companies?batch={batch_code}&country=India>  
c. If all 3 attempts fail for this batch, print a message and continue to the next batch - do not abort  
2\. For each company returned, create a RawFinding:  
\- title: company\["name"\] + " accepted into YC " + company.get("batch", "")  
\- summary: company.get("one_liner", "") + " | " + company.get("long_description", "")\[:300\]  
\- source_url: "<https://www.ycombinator.com/companies/>" + company.get("slug", "")  
\- source_name: "yc"  
\- published_date: None  
3\. Return {"raw_findings": findings, "source_failures": {\*\*state.get("source_failures", {}), "yc": &lt;True if every batch failed all attempts, else False&gt;}}  
<br/>Use httpx.get() with a timeout of 10 seconds, wrapped in the same retry helper pattern as Tavily.  
Parse response with response.json() - the companies are in response_json\["companies"\].  
If that key doesn't exist, try treating the entire response as a list.  
<br/>Imports: httpx, time, from agent.state import SignalState, RawFinding

**Prompt for HN node (\`agent/nodes/hn_algolia.py\`):**

Write the HN Algolia node for the Signal agent.  
<br/>Here is RawFinding TypedDict (paste it).  
Here is SignalState TypedDict (paste it).  
<br/>Write a single function \`hn_algolia_node\` in \`agent/nodes/hn_algolia.py\`.  
<br/>Signature: def hn_algolia_node(state: SignalState) -> dict:  
<br/>Steps:  
1\. Get queries from state\["query_plan"\]\["hn"\]  
2\. For each query, fetch with retry (up to 3 attempts, 5s then 15s backoff):  
<https://hn.algolia.com/api/v1/search?query={query}&tags=story&hitsPerPage=5>  
3\. If all 3 attempts fail for a query, skip it and continue  
4\. For each hit in response\["hits"\], create a RawFinding:  
\- title: hit.get("title", "")  
\- summary: hit.get("story_text", "") or hit.get("comment_text", "") - take first 400 chars, default to ""  
\- source_url: hit.get("url", "") or "<https://news.ycombinator.com/item?id=>" + str(hit.get("objectID", ""))  
\- source_name: "hn"  
\- published_date: hit.get("created_at", None)  
5\. Skip hits with empty title or empty url  
6\. Return {"raw_findings": findings, "source_failures": {\*\*state.get("source_failures", {}), "hn": &lt;True if every query failed all attempts, else False&gt;}}  
<br/>Imports: httpx, time, urllib.parse.quote, from agent.state import SignalState, RawFinding

**Prompt for RSS node (\`agent/nodes/google_news_rss.py\`):**

Write the Google News RSS node for the Signal agent.  
<br/>Here is RawFinding TypedDict (paste it).  
Here is SignalState TypedDict (paste it).  
<br/>Write a single function \`google_news_rss_node\` in \`agent/nodes/google_news_rss.py\`.  
<br/>Signature: def google_news_rss_node(state: SignalState) -> dict:  
<br/>Steps:  
1\. Get feed URLs from state\["query_plan"\]\["rss"\]  
2\. For each URL, parse it with feedparser.parse(url), WITH RETRY:  
\- Attempt up to 2 times total (1 initial + 1 retry per the PRD retry policy - RSS gets fewer retries than the others)  
\- Wait 5 seconds before the retry  
\- If both attempts fail, skip this feed and continue  
3\. For each entry in feed.entries (take first 10 per feed), create a RawFinding:  
\- title: entry.get("title", "")  
\- summary: entry.get("summary", "")\[:400\]  
\- source_url: entry.get("link", "")  
\- source_name: "google_news"  
\- published_date: entry.get("published", None)  
4\. Skip entries with empty title  
5\. Return {"raw_findings": findings, "source_failures": {\*\*state.get("source_failures", {}), "rss": &lt;True if every feed failed both attempts, else False&gt;}}  
<br/>Imports: feedparser, time, from agent.state import SignalState, RawFinding

Test all four together:

\# tests/test_all_research_nodes.py  
from agent.nodes.config_loader import config_loader  
from agent.nodes.search_planner import search_planner  
from agent.nodes.tavily_search import tavily_search  
from agent.nodes.yc_api import yc_api_node  
from agent.nodes.hn_algolia import hn_algolia_node  
from agent.nodes.google_news_rss import google_news_rss_node  
<br/>def test_all():  
state = config_loader({})  
state.update(search_planner(state))  
<br/>r1 = tavily_search(state)  
r2 = yc_api_node(state)  
r3 = hn_algolia_node(state)  
r4 = google_news_rss_node(state)  
<br/>all_findings = (  
r1.get("raw_findings", \[\]) +  
r2.get("raw_findings", \[\]) +  
r3.get("raw_findings", \[\]) +  
r4.get("raw_findings", \[\])  
)  
<br/>print(f"Tavily: {len(r1.get('raw_findings', \[\]))} findings, source_failures: {r1.get('source_failures', {}).get('tavily')}")  
print(f"YC: {len(r2.get('raw_findings', \[\]))} findings, source_failures: {r2.get('source_failures', {}).get('yc')}")  
print(f"HN: {len(r3.get('raw_findings', \[\]))} findings, source_failures: {r3.get('source_failures', {}).get('hn')}")  
print(f"RSS: {len(r4.get('raw_findings', \[\]))} findings, source_failures: {r4.get('source_failures', {}).get('rss')}")  
print(f"Total: {len(all_findings)} findings")  
<br/>assert len(all_findings) > 0, "No findings from any source - check API keys"  
assert len(all_findings) >= 5, f"Expected at least 5 total, got {len(all_findings)}"  
print("All research nodes test passed.")  
<br/>if \_\_name\_\_== "\__main_\_":  
test_all()

**SESSION 4 CHECKPOINT:**

- All four node files exist with no syntax errors
- python tests/test_all_research_nodes.py passes
- At least 5 total findings returned across all sources
- At least 2 distinct source_name values appear in the findings
- No node crashes - errors are caught, retried, and printed
- Each node's retry behavior was visibly tested at least once (you can temporarily break your internet or use a wrong API key briefly to confirm retry + graceful failure, then restore it)

### SESSION 4.5 - Reducer Node \[FIX - Gap 1\]

**Time estimate: 30 minutes**  
**Goal: A dedicated Reducer node sits between the parallel research nodes and Freshness Validation, matching the PRD architecture exactly.**

**What changed from v1:** v1 wired the four research nodes directly into Freshness Validation with no Reducer in between. This worked because raw_findings already uses Annotated\[list, operator.add\], which merges automatically regardless of whether a dedicated node exists. But the PRD explicitly defines the Reducer as its own architectural step, and it matters for two real reasons: (1) when Phase 2 introduces the Send API for true parallel fan-out, this is the exact node that receives the fanned-in results - having it already in place means the migration is a routing change, not a new node; (2) it gives you one clean place to log "merge complete, N total findings before any filtering" rather than that logic being implicit.

This is intentionally a small node. Do not let Cursor add anything beyond what's specified.

**Prompt to paste into Cursor:**

I am building a LangGraph agent called Signal. Write the Reducer node.  
<br/>Here is SignalState TypedDict (paste it).  
<br/>Write a single function \`reducer\` in \`agent/nodes/reducer.py\`.  
<br/>Signature: def reducer(state: SignalState) -> dict:  
<br/>This node runs immediately after the four parallel research nodes (Tavily, YC, HN, RSS) and immediately before Freshness Validation. By the time this node runs, state\["raw_findings"\] has ALREADY been merged by LangGraph's operator.add reducer on the Annotated field - this node's job is NOT to merge anything itself. Its job is to be an explicit checkpoint in the graph that:  
<br/>1\. Reads state\["raw_findings"\] (already merged)  
2\. Prints a summary: f"Reducer: {len(raw_findings)} total findings merged from all research nodes"  
3\. Returns {"raw_findings": state\["raw_findings"\]} - pass through unchanged, this is intentional  
<br/>Do not deduplicate here. Do not filter here. Do not add any logic beyond the print statement and pass-through. This node exists for architectural clarity and to prepare for Send API in Phase 2, not to transform data.  
<br/>Imports allowed: from agent.state import SignalState  
<br/>No LLM. No API calls. No filtering logic of any kind.

Test:

\# tests/test_reducer.py  
from tests.fixtures.sample_findings import ALL_SAMPLE_RAW_FINDINGS  
from agent.nodes.reducer import reducer  
<br/>def test_reducer():  
state = {"raw_findings": ALL_SAMPLE_RAW_FINDINGS}  
result = reducer(state)  
<br/>assert "raw_findings" in result  
assert len(result\["raw_findings"\]) == len(ALL_SAMPLE_RAW_FINDINGS)  
assert result\["raw_findings"\] == ALL_SAMPLE_RAW_FINDINGS  
print("Reducer test passed.")  
<br/>if \_\_name\_\_ == "\__main_\_":  
test_reducer()

**SESSION 4.5 CHECKPOINT:**

- agent/nodes/reducer.py exists with no syntax errors
- python tests/test_reducer.py prints "Reducer test passed."
- The node does nothing except pass through and print a count - no filtering, no transformation

### SESSION 5 - Freshness Validation Node

**Time estimate: 1 hour**  
**Goal: Stale findings are dropped before any LLM call. Undated findings are penalized but kept.**

**Prompt to paste into Cursor:**

I am building a LangGraph agent called Signal. Write the Freshness Validation node.  
<br/>Here is RawFinding TypedDict (paste it).  
Here is SignalState TypedDict (paste it).  
<br/>Write a single function \`freshness_validation\` in \`agent/nodes/freshness_validation.py\`.  
<br/>Signature: def freshness_validation(state: SignalState) -> dict:  
<br/>This node runs AFTER the Reducer. It filters stale content.  
<br/>Logic:  
1\. Get findings from state\["raw_findings"\]  
2\. Get today's date as datetime.now(timezone.utc).date()  
3\. For each finding:  
a. Try to parse finding\["published_date"\] into a date object  
\- Try these formats in order: "%Y-%m-%dT%H:%M:%SZ", "%Y-%m-%d", "%a, %d %b %Y %H:%M:%S %z"  
\- If parsing fails or published_date is None → mark as undated  
b. If undated: keep the finding, set a flag "freshness_penalized" = True on a copy of the finding dict  
c. If parsed successfully AND (today - parsed_date).days > 30 → DROP the finding, increment dropped count  
d. If parsed successfully AND age <= 30 days → keep, set "freshness_penalized" = False  
<br/>4\. Return:  
\- raw_findings: the filtered list (keeping valid + undated, dropping only confirmed-stale)  
\- findings_dropped_freshness: count of dropped findings  
\- findings_retrieved: len(state\["raw_findings"\]) # total before filtering  
<br/>Add "freshness_penalized" key to each kept finding dict. Do not create a new TypedDict for this - just add the key to the dict directly.  
<br/>Print a summary: f"Freshness validation: {kept} kept, {dropped} dropped, {penalized} penalized (no date)"  
<br/>Imports: from datetime import datetime, date, timezone, from agent.state import SignalState  
<br/>No LLM. No API calls. Pure Python date logic only.

Test:

\# tests/test_freshness.py  
from tests.fixtures.sample_findings import SAMPLE_OLD_FINDING, SAMPLE_UNDATED_FINDING, SAMPLE_FUNDING_FINDING  
from agent.nodes.freshness_validation import freshness_validation  
<br/>def test_freshness():  
state = {  
"raw_findings": \[SAMPLE_OLD_FINDING, SAMPLE_FUNDING_FINDING, SAMPLE_UNDATED_FINDING\]  
}  
<br/>result = freshness_validation(state)  
<br/>assert result\["findings_retrieved"\] == 3  
assert result\["findings_dropped_freshness"\] == 1  
assert len(result\["raw_findings"\]) == 2  
<br/>titles = \[f\["title"\] for f in result\["raw_findings"\]\]  
assert SAMPLE_OLD_FINDING\["title"\] not in titles  
assert SAMPLE_UNDATED_FINDING\["title"\] in titles  
<br/>undated = next(f for f in result\["raw_findings"\] if f\["title"\] == SAMPLE_UNDATED_FINDING\["title"\])  
assert undated\["freshness_penalized"\] == True  
<br/>print("Freshness validation test passed.")  
<br/>if \_\_name\_\_== "\__main_\_":  
test_freshness()

**SESSION 5 CHECKPOINT:**

- python tests/test_freshness.py prints "Freshness validation test passed."
- Old finding is dropped, recent and undated are kept
- freshness_penalized flag is set correctly on undated findings
- findings_dropped_freshness count is correct

### SESSION 6 - Entity Extraction Node

**Time estimate: 2 hours**  
**Goal: GPT-4o mini extracts structured EntityData from each finding. This is the first LLM node.**

First, create the prompt file at agent/prompts/entity_extraction_v3.txt:

You are an entity extraction system for Indian startup news.  
<br/>Extract structured information from the article title and summary provided. Return ONLY valid JSON. No explanation. No markdown. No backticks.  
<br/>Rules:  
\- company_name: The primary Indian startup or company name. Null if none.  
\- company_name_normalized: lowercase, no punctuation, no extra spaces. Example: "CRED." → "cred"  
\- founder_name: Individual person founding or leading. Null if none mentioned.  
\- investor_names: List of investors mentioned. Empty list if none.  
\- investor_names_normalized: Same list, each name lowercased with no punctuation.  
\- funding_amount_usd: Integer in USD. Convert crore to USD (1 crore = ~120,000 USD). Null if not mentioned.  
\- funding_stage: One of exactly: seed, pre_seed, series_a, series_b, series_c, grant, accelerator, unknown. Null if not a funding article.  
\- sector: One of exactly: AI, fintech, healthtech, b2b_saas, climate, edtech, logistics, consumer, other. Pick the closest match.  
\- location: City or country if explicitly mentioned. Null if not mentioned.  
\- announced_date: Extract the announcement date from the article text in YYYY-MM-DD format. If only month and year mentioned, use the 1st of that month. Null if no date found anywhere in the text.  
\- category: MUST be exactly one of: funding, hiring, founder_move, accelerator, shutdown, pivot, ecosystem_trend. Choose the best match. This field is REQUIRED and cannot be null.  
<br/>Return this exact JSON structure:  
{  
"company_name": null,  
"company_name_normalized": null,  
"founder_name": null,  
"investor_names": \[\],  
"investor_names_normalized": \[\],  
"funding_amount_usd": null,  
"funding_stage": null,  
"sector": null,  
"location": null,  
"announced_date": null,  
"category": "funding"  
}

**Prompt to paste into Cursor:**

I am building a LangGraph agent called Signal. Write the Entity Extraction node.  
<br/>Here is RawFinding TypedDict (paste it).  
Here is EntityData TypedDict (paste it).  
Here is ScoredFinding TypedDict (paste it).  
Here is ALLOWED_CATEGORIES (paste it).  
Here is SignalState TypedDict (paste it).  
<br/>Write a single function \`entity_extraction\` in \`agent/nodes/entity_extraction.py\`.  
<br/>Signature: def entity_extraction(state: SignalState) -> dict:  
<br/>This function processes each finding in state\["raw_findings"\] and calls GPT-4o mini to extract entities.  
<br/>Steps:  
1\. Load the prompt from agent/prompts/entity_extraction_v3.txt as a string  
2\. Initialize the OpenAI client: client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))  
3\. For each finding in state\["raw_findings"\]:  
a. Build user message: f"Title: {finding\['title'\]}\\n\\nSummary: {finding\['summary'\]}"  
b. Call GPT-4o mini:  
response = client.chat.completions.create(  
model="gpt-4o-mini",  
messages=\[{"role": "system", "content": prompt}, {"role": "user", "content": user_msg}\],  
temperature=0,  
max_tokens=400  
)  
c. Parse response.choices\[0\].message.content as JSON → this is the EntityData dict  
d. Validate: if category is not in ALLOWED_CATEGORIES, set it to "funding" (safe fallback)  
e. Calculate confidence_score:  
\- Start with SOURCE_TRUST.get(finding\["source_name"\], 0.60) → this is source_trust_score  
\- If finding.get("freshness_penalized") == True → subtract 0.10  
\- confidence_score = max(0.0, source_trust_score - penalty)  
f. Build a ScoredFinding dict by combining finding fields + entities + scores:  
\- Copy all fields from finding  
\- Add: entities (the parsed EntityData dict)  
\- Add: category (from extracted entities)  
\- Add: source_trust_score (float from SOURCE_TRUST)  
\- Add: freshness_penalty_applied (bool - True if freshness_penalized was True)  
\- Add: confidence_score (float calculated above)  
\- Add: is_duplicate = False  
\- Add: duplicate_reason = None  
g. On JSON parse error for this finding: print the error and skip this finding  
4\. Count tokens used: sum response.usage.total_tokens for all calls  
5\. Return:  
\- scored_findings: list of ScoredFinding dicts  
\- tokens_used: total token count  
\- estimated_cost_usd: tokens_used \* 0.000000150  
<br/>Imports: os, json, from openai import OpenAI, from dotenv import load_dotenv, from agent.state import SignalState, ScoredFinding, ALLOWED_CATEGORIES, SOURCE_TRUST  
<br/>Process findings one at a time in a simple for loop. No async. No batching.

Test:

\# tests/test_entity_extraction.py  
from agent.nodes.entity_extraction import entity_extraction  
from agent.state import ALLOWED_CATEGORIES  
from tests.fixtures.sample_findings import SAMPLE_FUNDING_FINDING  
<br/>def test_entity_extraction():  
state = {  
"raw_findings": \[{\*\*SAMPLE_FUNDING_FINDING, "freshness_penalized": False}\]  
}  
<br/>result = entity_extraction(state)  
<br/>assert "scored_findings" in result  
assert len(result\["scored_findings"\]) == 1  
<br/>finding = result\["scored_findings"\]\[0\]  
assert finding\["category"\] in ALLOWED_CATEGORIES  
assert finding\["entities"\]\["funding_amount_usd"\] is not None  
assert finding\["confidence_score"\] > 0  
assert finding\["source_trust_score"\] > 0  
assert finding\["is_duplicate"\] == False  
<br/>print(f"Extracted: {finding\['entities'\]}")  
print(f"Category: {finding\['category'\]}")  
print(f"Confidence: {finding\['confidence_score'\]}")  
print(f"Tokens used: {result\['tokens_used'\]}")  
print("Entity extraction test passed.")  
<br/>if \_\_name\_\_ == "\__main_\_":  
test_entity_extraction()

This makes a real GPT-4o mini API call. Check LangSmith - you should see the trace appear at smith.langchain.com.

**SESSION 6 CHECKPOINT:**

- python tests/test_entity_extraction.py passes
- category is always from ALLOWED_CATEGORIES
- entities dict has all EntityData fields
- source_trust_score and freshness_penalty_applied are populated
- LangSmith trace appears at smith.langchain.com

### SESSION 7 - Scope Filter Node

**Time estimate: 45 minutes**  
**Goal: Out-of-scope findings are dropped before trust scoring. Pure Python, no LLM.**

**Prompt to paste into Cursor:**

I am building a LangGraph agent called Signal. Write the Scope Filter node.  
<br/>Here is ScoredFinding TypedDict (paste it).  
Here is SignalState TypedDict (paste it).  
<br/>Write a single function \`scope_filter\` in \`agent/nodes/scope_filter.py\`.  
<br/>Signature: def scope_filter(state: SignalState) -> dict:  
<br/>This node enforces three domain boundaries. Rule: DROP only if EXPLICITLY out of scope. NEVER drop because a field is null.  
<br/>Logic:  
1\. Get findings from state\["scored_findings"\]  
2\. For each finding, apply three checks in order:  
<br/>Check 1 - Geography:  
NON_INDIA_LOCATIONS = \["san francisco", "new york", "london", "beijing", "shanghai", "singapore", "tokyo", "berlin", "paris", "dubai"\]  
location = finding\["entities"\].get("location", None)  
If location is not None:  
location_lower = location.lower()  
if any(non_india in location_lower for non_india in NON_INDIA_LOCATIONS):  
DROP with reason "scope_filter:non_indian_location"  
If location is None: KEEP  
<br/>Check 2 - Funding amount:  
amount = finding\["entities"\].get("funding_amount_usd", None)  
If amount is not None:  
if amount &lt; 500000 or amount &gt; 50000000:  
DROP with reason "scope_filter:funding_out_of_range"  
If amount is None: KEEP  
<br/>Check 3 - Stage:  
OUT_OF_SCOPE_STAGES = {"series_c", "series_d", "series_e", "ipo", "private_equity"}  
stage = finding\["entities"\].get("funding_stage", None)  
If stage is not None:  
if stage.lower() in OUT_OF_SCOPE_STAGES:  
DROP with reason "scope_filter:stage_out_of_range"  
If stage is None: KEEP  
<br/>3\. Print summary: f"Scope filter: {kept} kept, {dropped} dropped"  
4\. Return:  
\- scored_findings: list of kept findings only  
\- findings_dropped_scope: count of dropped findings  
<br/>No LLM. No API calls. Do not modify the findings themselves - only filter the list.

Test:

\# tests/test_scope_filter.py  
from agent.nodes.scope_filter import scope_filter  
from tests.fixtures.sample_findings import SAMPLE_OUT_OF_SCOPE_FINDING, SAMPLE_SCORED_FUNDING_FINDING  
<br/>def make_finding(location=None, amount=None, stage=None):  
return {  
\*\*SAMPLE_SCORED_FUNDING_FINDING,  
"entities": {  
\*\*SAMPLE_SCORED_FUNDING_FINDING\["entities"\],  
"location": location,  
"funding_amount_usd": amount,  
"funding_stage": stage,  
}  
}  
<br/>def test_scope_filter():  
state = {  
"scored_findings": \[  
SAMPLE_OUT_OF_SCOPE_FINDING, # DROP - US location  
make_finding(location="Bengaluru", amount=5000000), # KEEP  
make_finding(location=None, amount=5000000), # KEEP - null location  
make_finding(location="Mumbai", amount=200000000), # DROP - too large  
make_finding(location="Delhi", stage="series_c"), # DROP - wrong stage  
make_finding(location=None, amount=None, stage=None), # KEEP - all null  
\]  
}  
<br/>result = scope_filter(state)  
assert result\["findings_dropped_scope"\] == 3  
assert len(result\["scored_findings"\]) == 3  
print("Scope filter test passed.")  
<br/>if \_\_name\_\_ == "\__main_\_":  
test_scope_filter()

**SESSION 7 CHECKPOINT:**

- python tests/test_scope_filter.py prints "Scope filter test passed."
- 3 findings dropped, 3 kept
- Null fields are never a reason to drop

### SESSION 8 - Source Trust Scoring + Hybrid Dedup

**Time estimate: 1.5 hours**  
**Goal: Findings are confidence-scored and deduplicated. Two deterministic nodes.**

**Prompt for Source Trust Scoring (\`agent/nodes/source_trust_scoring.py\`):**

I am building a LangGraph agent called Signal. Write the Source Trust Scoring node.  
<br/>Here is ScoredFinding TypedDict (paste it).  
Here is SOURCE_TRUST constant (paste it).  
Here is SignalState TypedDict (paste it).  
<br/>Write a single function \`source_trust_scoring\` in \`agent/nodes/source_trust_scoring.py\`.  
<br/>Signature: def source_trust_scoring(state: SignalState) -> dict:  
<br/>This node has already calculated confidence_score during entity extraction.  
This node's job is to SORT the scored_findings by confidence_score descending so  
highest-confidence findings go to synthesis first.  
<br/>Steps:  
1\. Get findings from state\["scored_findings"\]  
2\. Sort by confidence_score descending  
3\. Return {"scored_findings": sorted_list}  
<br/>That is all this node does. Scoring already happened in entity extraction.  
No LLM. No API calls. One line of sort logic.

**Prompt for Hybrid Dedup (\`agent/nodes/hybrid_dedup.py\`):**

I am building a LangGraph agent called Signal. Write the Hybrid Dedup node.  
<br/>Here is ScoredFinding TypedDict (paste it).  
Here is SignalState TypedDict (paste it).  
<br/>Write a single function \`hybrid_dedup\` in \`agent/nodes/hybrid_dedup.py\`.  
<br/>Signature: def hybrid_dedup(state: SignalState) -> dict:  
<br/>Phase 1 dedup only - three checks, no embeddings yet. (Embeddings get added in Week 2, Session 12.5.)  
<br/>The "seen" set is built from state\["semantic_memory"\].get("seen_urls", \[\]) and state\["semantic_memory"\].get("seen_titles", \[\]) and state\["semantic_memory"\].get("seen_company_dates", \[\]).  
<br/>For each finding in state\["scored_findings"\]:  
<br/>Pre-filter check (run first):  
company = finding\["entities"\].get("company_name_normalized", "")  
date = finding\["entities"\].get("announced_date", "")  
if company and date:  
key = company + "|" + date  
if key in seen_company_dates → mark as duplicate, reason = "pre_filter"  
<br/>URL check (if not already marked duplicate):  
if finding\["source_url"\] in seen_urls → mark as duplicate, reason = "url_match"  
<br/>Title check (if not already marked duplicate):  
normalized_title = finding\["title"\].lower().strip()  
if normalized_title in seen_titles → mark as duplicate, reason = "title_match"  
<br/>If not a duplicate:  
Add source_url to seen_urls  
Add normalized title to seen_titles  
If company and date: add key to seen_company_dates  
Add to new_findings list  
<br/>Set finding\["is_duplicate"\] = True/False and finding\["duplicate_reason"\] accordingly.  
<br/>Return:  
\- new_findings: list of non-duplicate findings only  
\- findings_dropped_dedup: count of duplicates found  
\- semantic_memory: updated dict with seen_urls, seen_titles, seen_company_dates lists added  
<br/>No LLM. No embeddings. No external calls.

**SESSION 8 CHECKPOINT:**

- Both node files exist with no syntax errors
- Source trust scoring sorts by confidence_score descending
- Dedup correctly flags URL matches, title matches, and pre-filter matches
- new_findings contains only non-duplicate items
- findings_dropped_dedup count is accurate

### SESSION 9 - Synthesis Node

**Time estimate: 1.5 hours**  
**Goal: GPT-4o writes a structured weekly briefing from the deduplicated findings.**

**Prompt to paste into Cursor:**

I am building a LangGraph agent called Signal. Write the Synthesis node.  
<br/>Here is ScoredFinding TypedDict (paste it).  
Here is BriefingItem TypedDict (paste it).  
Here is SignalState TypedDict (paste it).  
<br/>Write a single function \`synthesis\` in \`agent/nodes/synthesis.py\`.  
<br/>Signature: def synthesis(state: SignalState) -> dict:  
<br/>This node takes state\["new_findings"\] and produces a formatted weekly briefing.  
<br/>Steps:  
1\. Get findings from state\["new_findings"\]  
2\. If len(findings) == 0: return {"briefing_draft": "No new findings this week.", "briefing_items": \[\], "briefing_final": "No new findings this week."}  
3\. Build a context string from findings - for each finding:  
f"\[{finding\['category'\].upper()}\] {finding\['title'\]}\\nSource: {finding\['source_name'\]} (confidence: {finding\['confidence_score'\]:.2f})\\n{finding\['summary'\]}\\n"  
4\. Build system prompt:  
"You are Signal, an Indian startup intelligence agent. Write a structured weekly briefing from the findings provided. Format the briefing as follows:  
<br/>\## Signal Weekly Briefing  
<br/>\### Executive Summary  
2-3 sentences summarizing the most important themes this week.  
<br/>\### Funding Highlights  
List each funding finding with company, amount, stage, investors.  
<br/>\### Ecosystem Moves  
List founder moves, accelerator announcements, hiring signals.  
<br/>\### Trends to Watch  
1-2 patterns emerging across multiple findings.  
<br/>Prioritize findings with higher confidence scores. Write clearly for a founder audience. Do not invent information not present in the findings."  
<br/>5\. Call GPT-4o:  
response = client.chat.completions.create(  
model="gpt-4o",  
messages=\[  
{"role": "system", "content": system_prompt},  
{"role": "user", "content": context_string}  
\],  
temperature=0.3,  
max_tokens=1500  
)  
<br/>6\. briefing_text = response.choices\[0\].message.content  
<br/>7\. Build briefing_items list - one BriefingItem per finding in new_findings:  
{"id": str(uuid4()), "title": f\["title"\], "summary": f\["summary"\],  
"source_url": f\["source_url"\], "source_name": f\["source_name"\],  
"category": f\["category"\], "confidence_score": f\["confidence_score"\],  
"entities": f\["entities"\]}  
<br/>8\. Add tokens to running total:  
tokens = state.get("tokens_used", 0) + response.usage.total_tokens  
cost = state.get("estimated_cost_usd", 0.0) + (response.usage.total_tokens \* 0.000005)  
<br/>9\. Return:  
\- briefing_draft: briefing_text  
\- briefing_final: briefing_text  
\- briefing_items: the list  
\- tokens_used: tokens  
\- estimated_cost_usd: cost  
<br/>Imports: os, json, from uuid import uuid4, from openai import OpenAI, from dotenv import load_dotenv, from agent.state import SignalState, BriefingItem

**SESSION 9 CHECKPOINT:**

- Synthesis node exists with no syntax errors
- Briefing output is readable markdown
- briefing_items list is populated
- GPT-4o trace appears in LangSmith

### SESSION 9.5 - Phase 1 Memory Writer + Metrics Writer \[FIX - Gaps 8 and 9\]

**Time estimate: 1 hour**  
**Goal: Minimal Phase-1-appropriate versions of Episodic Memory Writer and Run Metrics Writer exist as real graph nodes before the graph is wired in Session 10.**

**What changed from v1:** The PRD's Phase 1 build order explicitly lists "Episodic Memory Writer (InMemoryStore)" and "Run Metrics Writer (log to console in Phase 1)" as steps 11 and 12 of the Phase 1 build, before output. v1 of this spec pushed both of these into Week 2 (Sessions 13 and 14) as their full Postgres-backed versions, which meant the Phase 1 graph had no memory node and no metrics node at all - just a print() in the run script. This session builds the lightweight Phase 1 versions now. Session 13 and 14 in Week 2 will upgrade these same files to use PostgresStore and Supabase instead of rewriting them from scratch.

**Prompt for Episodic Memory Writer (Phase 1 version):**

I am building a LangGraph agent called Signal. Write the Phase 1 version of the Episodic Memory Writer node.  
<br/>Here is SignalState TypedDict (paste it).  
<br/>Write a single function \`episodic_memory_writer\` in \`agent/nodes/episodic_memory_writer.py\`.  
<br/>Signature: def episodic_memory_writer(state: SignalState) -> dict:  
<br/>In Phase 1 there is no database and no LangGraph Store yet - this writes to an in-memory Python list that simulates episodic memory for this run only. (Phase 2, Session 13, replaces this with a real LangGraph Store write under namespace ("user", user_id, "episodic") backed by Postgres. The function signature will not change - only the internals.)  
<br/>This node MUST run before any delivery step in the graph, even though Phase 1 has no delivery node yet. This ordering rule does not change in later phases: episodic memory write always happens before delivery, so that if delivery fails the run is never lost.  
<br/>Steps:  
1\. Get state\["new_findings"\] and state\["briefing_final"\]  
2\. Build an episode record:  
{  
"run_id": state.get("run_id", ""),  
"thread_id": state.get("thread_id", ""),  
"timestamp": current UTC ISO timestamp,  
"item_titles": \[f\["title"\] for f in new_findings\],  
"source_urls": \[f\["source_url"\] for f in new_findings\],  
"company_names_normalized": \[f\["entities"\].get("company_name_normalized") for f in new_findings if f\["entities"\].get("company_name_normalized")\],  
"briefing_summary": state.get("briefing_final", "")\[:200\]  
}  
3\. Append this record to a module-level list called EPISODIC_MEMORY_STORE (a plain Python list at module scope, initialized as empty list)  
4\. Print: f"Episodic memory written: {len(item_titles)} items recorded for run {run_id}"  
5\. Return {} (this node does not modify SignalState fields, it only has a side effect)  
<br/>Imports: from datetime import datetime, timezone, from agent.state import SignalState  
<br/>No database. No LangGraph Store yet. Just an in-memory list and a print statement.

**Prompt for Run Metrics Writer (Phase 1 version):**

I am building a LangGraph agent called Signal. Write the Phase 1 version of the Run Metrics Writer node.  
<br/>Here is SignalState TypedDict (paste it).  
<br/>Write a single function \`run_metrics_writer\` in \`agent/nodes/run_metrics_writer.py\`.  
<br/>Signature: def run_metrics_writer(state: SignalState) -> dict:  
<br/>In Phase 1 this logs metrics to console only. (Phase 2, Session 14, upgrades this same function to write a row into the agent_run_metrics Supabase table instead of printing - the signature will not change.)  
<br/>Steps:  
1\. Build a metrics dict from state:  
{  
"run_id": state.get("run_id", ""),  
"graph_version": state.get("graph_version", "unknown"),  
"sources_queried": state.get("sources_queried", \[\]),  
"findings_retrieved": state.get("findings_retrieved", 0),  
"findings_dropped_freshness": state.get("findings_dropped_freshness", 0),  
"findings_dropped_scope": state.get("findings_dropped_scope", 0),  
"findings_dropped_dedup": state.get("findings_dropped_dedup", 0),  
"findings_in_briefing": len(state.get("new_findings", \[\])),  
"tokens_used": state.get("tokens_used", 0),  
"estimated_cost_usd": state.get("estimated_cost_usd", 0.0),  
"source_health": state.get("source_failures", {})  
}  
2\. Print a clearly formatted block to console showing every field above, one per line  
3\. Print a warning line for any source where source_failures\[source\] is True: f"WARNING: {source} failed this run"  
4\. Return {} (side-effect only node, does not modify SignalState fields)  
<br/>Imports: from agent.state import SignalState  
<br/>No database write in Phase 1. Console output only. Note that source_health here is the same data as state\["source_failures"\] - Phase 2 will persist it to the agent_run_metrics.source_health column under that same field name.

Test both:

\# tests/test_phase1_memory_and_metrics.py  
from agent.nodes.episodic_memory_writer import episodic_memory_writer, EPISODIC_MEMORY_STORE  
from agent.nodes.run_metrics_writer import run_metrics_writer  
<br/>def test_episodic_writer():  
state = {  
"run_id": "test_run_001",  
"thread_id": "thread_001",  
"new_findings": \[{  
"title": "Test funding round",  
"source_url": "<http://test.com>",  
"entities": {"company_name_normalized": "testco"}  
}\],  
"briefing_final": "Test briefing content"  
}  
result = episodic_memory_writer(state)  
assert result == {}  
assert len(EPISODIC_MEMORY_STORE) == 1  
assert EPISODIC_MEMORY_STORE\[0\]\["run_id"\] == "test_run_001"  
print("Episodic memory writer test passed.")  
<br/>def test_metrics_writer():  
state = {  
"run_id": "test_run_001",  
"graph_version": "1.0",  
"sources_queried": \["tavily", "yc"\],  
"findings_retrieved": 20,  
"findings_dropped_freshness": 3,  
"findings_dropped_scope": 2,  
"findings_dropped_dedup": 1,  
"new_findings": \[{}, {}\],  
"tokens_used": 5000,  
"estimated_cost_usd": 0.05,  
"source_failures": {"tavily": False, "yc": True, "hn": False, "rss": False}  
}  
result = run_metrics_writer(state)  
assert result == {}  
print("Run metrics writer test passed.")  
<br/>if \_\_name\_\_== "\__main_\_":  
test_episodic_writer()  
test_metrics_writer()

**SESSION 9.5 CHECKPOINT:**

- Both node files exist with no syntax errors
- python tests/test_phase1_memory_and_metrics.py prints both pass messages
- Episodic memory writer appends to an in-memory list (visible by checking EPISODIC_MEMORY_STORE length grows on repeated calls)
- Run metrics writer prints graph_version and source_health clearly to console - confirm both are visible in the printed output
- You understand that these are placeholders upgraded in Week 2 Sessions 13 and 14, not final implementations

### SESSION 10 - Wire the Graph + First Full Run

**Time estimate: 2-3 hours**  
**Goal: All nodes wired into a LangGraph StateGraph. First real end-to-end run. This is the milestone.**

**What changed from v1:** The graph now includes the Reducer node (Session 4.5) between the research nodes and Freshness Validation, and includes Episodic Memory Writer + Run Metrics Writer (Session 9.5) after Synthesis. The ordering note about memory-before-delivery is now explicit in the prompt itself, not left implicit.

**Prompt to paste into Cursor:**

I am building a LangGraph agent called Signal. Wire all nodes into a LangGraph StateGraph.  
<br/>Here is SignalState TypedDict (paste the full thing).  
<br/>Write \`agent/graph.py\`. This file creates and compiles the LangGraph graph.  
<br/>Import these functions:  
from agent.state import SignalState  
from agent.nodes.config_loader import config_loader  
from agent.nodes.search_planner import search_planner  
from agent.nodes.tavily_search import tavily_search  
from agent.nodes.yc_api import yc_api_node  
from agent.nodes.hn_algolia import hn_algolia_node  
from agent.nodes.google_news_rss import google_news_rss_node  
from agent.nodes.reducer import reducer  
from agent.nodes.freshness_validation import freshness_validation  
from agent.nodes.entity_extraction import entity_extraction  
from agent.nodes.scope_filter import scope_filter  
from agent.nodes.source_trust_scoring import source_trust_scoring  
from agent.nodes.hybrid_dedup import hybrid_dedup  
from agent.nodes.synthesis import synthesis  
from agent.nodes.episodic_memory_writer import episodic_memory_writer  
from agent.nodes.run_metrics_writer import run_metrics_writer  
<br/>Also import:  
from langgraph.graph import StateGraph, START, END  
from langgraph.checkpoint.memory import MemorySaver  
<br/>Build the graph with this exact node order:  
<br/>1\. config_loader  
2\. search_planner  
3\. tavily_search ← parallel research, wired sequentially in Phase 1  
4\. yc_api_node ← parallel research, wired sequentially in Phase 1  
5\. hn_algolia_node ← parallel research, wired sequentially in Phase 1  
6\. google_news_rss_node ← parallel research, wired sequentially in Phase 1  
7\. reducer ← explicit merge checkpoint, prepares for Send API in Phase 2  
8\. freshness_validation  
9\. entity_extraction  
10\. scope_filter  
11\. source_trust_scoring  
12\. hybrid_dedup  
13\. synthesis  
14\. episodic_memory_writer ← CRITICAL: must run before any delivery node. Phase 1 has no delivery node yet, but this ordering rule is permanent - when Gmail delivery is added in Phase 2, it goes AFTER this node, never before.  
15\. run_metrics_writer  
<br/>For the parallel research nodes (3, 4, 5, 6):  
In Phase 1, wire them sequentially for simplicity. We use Send API in Phase 2 for true parallel fan-out into the Reducer.  
<br/>Add edges in this exact order:  
START → config_loader  
config_loader → search_planner  
search_planner → tavily_search  
tavily_search → yc_api_node  
yc_api_node → hn_algolia_node  
hn_algolia_node → google_news_rss_node  
google_news_rss_node → reducer  
reducer → freshness_validation  
freshness_validation → entity_extraction  
entity_extraction → scope_filter  
scope_filter → source_trust_scoring  
source_trust_scoring → hybrid_dedup  
hybrid_dedup → synthesis  
synthesis → episodic_memory_writer  
episodic_memory_writer → run_metrics_writer  
run_metrics_writer → END  
<br/>Create the graph like this:  
builder = StateGraph(SignalState)  
\# add all 15 nodes with builder.add_node("name", function)  
\# add all edges with builder.add_edge(from, to)  
<br/>checkpointer = MemorySaver()  
graph = builder.compile(checkpointer=checkpointer)  
<br/>Expose: graph (the compiled graph object)  
<br/>Also write a function \`run_graph()\` that:  
1\. Creates initial state with every SignalState field set to its appropriate empty default:  
{"run_id": str(uuid4()), "raw_findings": \[\], "scored_findings": \[\], "new_findings": \[\], "briefing_items": \[\], "sources_queried": \[\], "findings_retrieved": 0, "findings_dropped_freshness": 0, "findings_dropped_dedup": 0, "findings_dropped_scope": 0, "tokens_used": 0, "estimated_cost_usd": 0.0, "run_duration_seconds": 0.0, "run_config_snapshot": {}, "error": None, "source_failures": {}, "semantic_memory": {}, "procedural_memory": {}, "query_plan": {}, "user_config": {}, "user_id": "", "thread_id": "", "run_type": "manual", "graph_version": os.getenv("GRAPH_VERSION", "1.0"), "hitl_decision": None, "hitl_edits": None, "delivery_status": None, "briefing_draft": "", "briefing_final": ""}  
2\. Calls graph.invoke(initial_state, config={"configurable": {"thread_id": "run_001"}})  
3\. Returns the final state  
<br/>Imports: os, from uuid import uuid4, from langgraph.graph import StateGraph START END, from langgraph.checkpoint.memory import MemorySaver

Then create the run script scripts/run_agent.py:

import time  
from dotenv import load_dotenv  
load_dotenv()  
<br/>from agent.graph import run_graph  
<br/>if \_\_name\_\_ == "\__main_\_":  
print("Starting Signal agent run...")  
start = time.time()  
<br/>final_state = run_graph()  
<br/>duration = time.time() - start  
<br/>print("\\n" + "="\*60)  
print("SIGNAL WEEKLY BRIEFING")  
print("="\*60)  
print(final_state.get("briefing_final", "No briefing generated"))  
print("="\*60)  
print(f"\\nRun complete in {duration:.1f}s")  
print(f"Graph version: {final_state.get('graph_version', 'unknown')}")  
print(f"Findings retrieved: {final_state.get('findings_retrieved', 0)}")  
print(f"Dropped (freshness): {final_state.get('findings_dropped_freshness', 0)}")  
print(f"Dropped (scope): {final_state.get('findings_dropped_scope', 0)}")  
print(f"Dropped (dedup): {final_state.get('findings_dropped_dedup', 0)}")  
print(f"In briefing: {len(final_state.get('new_findings', \[\]))}")  
print(f"Tokens used: {final_state.get('tokens_used', 0)}")  
print(f"Estimated cost: \${final_state.get('estimated_cost_usd', 0.0):.4f}")  
print(f"Source failures: {final_state.get('source_failures', {})}")

Run:

python scripts/run_agent.py

Note: the Episodic Memory Writer and Run Metrics Writer nodes (Session 9.5) already print their own detailed output as part of the graph run - the summary above in run_agent.py is a secondary confirmation, not a replacement for those node-level prints. You should see three blocks of output: the Reducer's count, the Memory/Metrics writers' detailed prints, and finally this summary block.

**SESSION 10 CHECKPOINT - Phase 1 Definition of Done:**

- python scripts/run_agent.py runs without crashing
- A readable briefing appears in the terminal
- At least 5 findings in the briefing
- At least 2 distinct source names
- findings_dropped_freshness > 0 (some stale content exists)
- All category values in findings are from ALLOWED_CATEGORIES
- Reducer's print statement appears showing total merged count
- Episodic Memory Writer's print statement appears, confirming items recorded
- Run Metrics Writer's print statement appears, showing graph_version and source_health
- Metrics printed to terminal are non-zero
- LangSmith shows a complete run trace with all 15 node spans visible at smith.langchain.com
- No unhandled exceptions

**Phase 1 is complete when this checkpoint passes.**

## Week 2 - Phases 2 and 3

Phase 2 and Phase 3 sessions follow the same pattern: one session per node or feature, checkpoint before moving on. These sessions are written at the start of Week 2, informed by what was actually built in Week 1.

The sessions below are defined at the feature level. Each one gets a full node spec written fresh at the start of that session, exactly as Week 1 sessions were written.

### WEEK 2 OVERVIEW

**What changed from v1:** Added Session 12.5 for the embedding dedup upgrade (Gap 4 - this was validated in Spike 3 but had no dedicated session in v1). Session 13's checkpoint now explicitly upgrades the Phase 1 stub from Session 9.5 rather than building from scratch. Session 14's checkpoint now explicitly requires graph_version and source_health persistence (Gaps 2 and 3).

| **Day** | **Session**  | **Feature**                                                                                   |
| ------- | ------------ | --------------------------------------------------------------------------------------------- |
| Day 8   | Session 11   | Supabase setup + schema migration                                                             |
| Day 8   | Session 12   | PostgresSaver + PostgresStore wiring                                                          |
| Day 9   | Session 12.5 | **\[NEW\]** Embedding dedup upgrade (pgvector + text-embedding-3-small)                       |
| Day 9   | Session 13   | Episodic Memory Writer - upgrade Phase 1 stub to PostgresStore                                |
| Day 9   | Session 14   | Run Metrics Writer - upgrade Phase 1 stub to write to DB, incl. graph_version + source_health |
| Day 10  | Session 15   | FastAPI backend - core endpoints                                                              |
| Day 10  | Session 16   | HITL interrupt() wiring                                                                       |
| Day 11  | Session 17   | Gmail delivery via smtplib                                                                    |
| Day 11  | Session 18   | Frontend - Dashboard + HITL Review Screen                                                     |
| Day 12  | Session 19   | Frontend - Briefing Detail + Feedback buttons                                                 |
| Day 12  | Session 20   | Frontend - Run Metrics screen                                                                 |
| Day 13  | Session 21   | Procedural Memory Updater (deterministic)                                                     |
| Day 13  | Session 22   | Memory Inspector UI screen                                                                    |
| Day 14  | Session 23   | APScheduler + deployment to Northflank                                                        |
| Day 14  | Session 24   | Frontend deployment to Vercel + end-to-end test                                               |

### SESSION 11 - Supabase Setup

**Checkpoint before proceeding:** Supabase project exists, pgvector enabled, all tables created, connection string works from Python.

Key steps:

- Create new Supabase project at supabase.com
- Enable pgvector: in SQL Editor run CREATE EXTENSION IF NOT EXISTS vector;
- Run the full schema SQL from PRD v1.2 Section 18 in the SQL Editor - confirm agent_run_metrics includes a source_health jsonb column and briefing_runs includes a graph_version text column (both added per Gaps 2 and 3 - if your schema SQL predates this fix, add these two columns now with ALTER TABLE)
- Add DATABASE_URL to .env
- Test connection with a simple psycopg2 or supabase-py query

### SESSION 12 - PostgresSaver + PostgresStore

**Checkpoint before proceeding:** Graph runs with PostgresSaver. State persists across Python restarts. LangGraph Store reads/writes work.

This session replaces MemorySaver with PostgresSaver and adds the Store for episodic, semantic, and procedural memory. The graph structure does not change - only the persistence layer.

### SESSION 12.5 - Embedding Dedup Upgrade \[FIX - Gap 4\]

**Time estimate: 1.5 hours**  
**Goal: Hybrid Dedup gains the third layer the PRD always specified - embedding cosine similarity - using exactly the threshold and model validated in Spike 3.**

**What changed from v1:** v1 mentioned embeddings would be "added in Phase 2" inside the Hybrid Dedup node's own docstring comment, but never gave it an actual session. This session exists specifically to close that gap. Spike 3 already validated the 0.85 threshold and the company-name-plus-date pre-filter - this session implements exactly that, nothing more.

**Checkpoint before proceeding:** A test pair of near-duplicate articles (same company, same round, different publications, different URLs, similar but not identical titles) is correctly flagged as a duplicate via embedding similarity even though it passes the URL and title checks. A test pair of genuinely different articles about different companies is correctly NOT flagged.

Key build steps for this session:

1\. Add text-embedding-3-small call wrapped around title + first 300 characters of summary, per Spike 3's validated input shape

2\. Store embeddings in the briefing_items.embedding pgvector column

3\. Upgrade hybrid_dedup.py: after the existing pre-filter, URL, and title checks all pass (finding is NOT yet flagged duplicate), compute its embedding and compare cosine similarity against embeddings of items already in episodic memory for this user

4\. Threshold: similarity > 0.85 → hard duplicate, exclude from synthesis, duplicate_reason = "embedding_similarity"

5\. Near-duplicate zone 0.75-0.85 → keep, but add a note field "related_to_previous_coverage": True on the finding (do not drop)

6\. This upgrade modifies the existing hybrid_dedup function signature minimally - it should still return the same dict shape, just with embedding-based duplicates now also counted in findings_dropped_dedup

### SESSION 13 - Episodic Memory Writer Node (Postgres Upgrade)

**Checkpoint before proceeding:** After a run, episodic memory in LangGraph Store contains the run's findings. Second run does not re-report items from first run.

This session upgrades the Phase 1 stub built in Session 9.5 - same function name and signature, internals now write to LangGraph Store under namespace ("user", user_id, "episodic") backed by PostgresStore, instead of appending to the in-memory EPISODIC_MEMORY_STORE list. It must run BEFORE the Delivery node - enforced by graph edge order, exactly as it was already positioned in the Phase 1 graph from Session 10.

### SESSION 14 - Run Metrics Writer Node (Postgres Upgrade) \[FIX - Gaps 2 and 3\]

**Checkpoint before proceeding:** agent_run_metrics table has a row after every run, and that row includes graph_version and source_health populated correctly - not just the findings counts.

This session upgrades the Phase 1 stub built in Session 9.5. Same function name and signature, internals now perform an actual INSERT into the agent_run_metrics table instead of printing to console.

Explicitly confirm in this session:

- graph_version from state is written into both agent_run_metrics.graph_version and briefing_runs.graph_version (the column added in Session 11) - when reviewing historical runs later, "which graph version produced this?" must be answerable directly from the database, not inferred
- source_failures from state is written into agent_run_metrics.source_health as a JSONB object, e.g. {"tavily": true, "yc": false, "hn": false, "rss": false} - this is the same dict that's been flowing through state since Session 2, just persisted now instead of only printed
- findings_dropped_freshness and findings_dropped_scope are both populated as separate columns, not combined into one number

### SESSION 15 - FastAPI Backend

**Checkpoint before proceeding:** All endpoints from PRD Section 19 return 200. /agent/run triggers a real graph run. /briefings returns past runs from DB.

Create api/main.py. Wire Supabase Auth JWT middleware. This session is the longest in Week 2.

### SESSION 16 - HITL interrupt()

**Checkpoint before proceeding:** Graph pauses at the interrupt point. /briefings/{id}/approve resumes it. /briefings/{id}/reject discards it. Episodic memory is confirmed written before the interrupt fires - verify this explicitly by checking the database after a reject: the episode should still be present even though the briefing was discarded.

LangGraph's interrupt() requires PostgresSaver to be active - this is why Session 12 must complete first.

### SESSION 17 - Gmail Delivery

**Checkpoint before proceeding:** An approved briefing arrives in the delivery email inbox. If Gmail fails, the run is already in episodic memory (verify this by temporarily using an invalid App Password, confirming the run still appears in episodic memory and in briefing_runs despite delivery failing).

Use smtplib with a Gmail App Password. Set up a Gmail App Password at myaccount.google.com → Security → 2FA → App Passwords. Confirm in the graph: episodic_memory_writer → delivery is the edge order, never the reverse.

### SESSION 18 - Frontend: Dashboard + HITL

**Checkpoint before proceeding:** Dashboard shows agent status and past briefings. HITL Review Screen shows the draft and Approve/Reject buttons work end-to-end.

HTML/JS only. No framework. Keep it clean and simple.

### SESSION 19 - Frontend: Briefing Detail + Feedback

**Checkpoint before proceeding:** Each briefing item shows title, summary, source, category, confidence. Thumbs up/down buttons write to briefing_items.feedback via POST /items/{id}/feedback.

### SESSION 20 - Frontend: Run Metrics Screen

**Checkpoint before proceeding:** Metrics screen shows last 5 runs with per-source counts, freshness drop rate, scope drop rate, dedup rate, token cost, runtime, graph version, and source health status (which source failed, if any).

### SESSION 21 - Procedural Memory Updater

**Checkpoint before proceeding:** After 5 feedback signals, procedural memory JSON updates. Next run's Search Planner reflects the updated preferences. No LLM involved.

### SESSION 22 - Memory Inspector Screen

**Checkpoint before proceeding:** Three-tab UI shows current semantic, episodic, and procedural memory state. Read-only. Procedural tab shows last updated timestamp.

### SESSION 23 - APScheduler + Northflank Deploy

**Checkpoint before proceeding:** Agent runs on schedule (weekly). Northflank service is live with no cold-start spin-down. /agent/status returns correct status from a public URL at any time of day.

Northflank setup:

- Create account at northflank.com
- New project → New service → Deployment → connect GitHub repo
- Set all .env variables as environment variables in Northflank
- Service runs uvicorn api.main:app --host 0.0.0.0 --port 8080
- Confirm the service does NOT spin down after inactivity - this is the entire reason Northflank was chosen over Render

### SESSION 24 - Vercel Deploy + End-to-End Test

**Checkpoint before proceeding:** Full system works end-to-end from public URLs. A recruiter can open the URL, trigger a run, review in HITL, approve it, and see it delivered to email, at any hour without a cold-start delay.

Frontend deploy to Vercel - update API base URL to point to Northflank backend URL.

Final end-to-end test:

- Trigger manual run from Dashboard
- Wait for HITL pause
- Review draft briefing
- Approve
- Confirm delivery email arrives
- Check Run Metrics screen shows the run including graph_version and source_health
- Check Memory Inspector shows episodic memory updated
- Confirm a near-duplicate story from a second publication is correctly flagged by embedding dedup, not just URL/title matching

## Master Checkpoint - Project Complete

- Full run completes end-to-end without errors
- Briefing has ≥5 deduplicated items from ≥2 sources
- Reducer node is present in the graph and visible as its own span in LangSmith
- All research nodes retry on transient failure before giving up
- YC batch codes are computed dynamically every run, never hardcoded
- Embedding-based dedup catches cross-publication duplicates that URL/title matching misses
- HITL works - graph pauses and resumes
- Episodic memory is confirmed to persist even when Gmail delivery fails
- Gmail delivery works
- Feedback buttons write to DB
- Procedural memory updates after ≥5 feedback signals
- All 8 UI screens are accessible from public URL
- LangSmith shows complete traces for every run
- Northflank service stays alive between runs (no cold starts)
- agent_run_metrics table has data for every run, including graph_version and source_health
- briefing_runs table records graph_version for every run
- README explains the project clearly for a recruiter

_Signal Build Spec v2 - start Session 0 when ready._