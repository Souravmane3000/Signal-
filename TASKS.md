\# Signal - TASKS.md  

\## Agent Task Queue  
<br/>\*\*Version:\*\* 3.0 | \*\*Status:\*\* Ready for execution | \*\*Total tasks:\*\* 40 (33 agent + 7 human)  
\*\*Execution model:\*\* Agent-first. Tier 1 = agent executes autonomously. Tier 2 = agent executes, human validates before DONE. Tier 3 = human executes only, never agent.  
<br/>\---  
<br/>\## How Agents Use This File  
<br/>1\. Read \`CURRENT_PHASE.md\` first - every session, no exceptions  

2\. Identify current slice and all TODO tasks within it  
3\. Check dependencies - do not start a task until all listed dependencies are DONE  
4\. Execute Tier 1 tasks in batch within the current slice  
5\. On Tier 2 tasks: build, then output validation checklist and STOP. Mark PENDING VALIDATION. Do not mark DONE until human confirms  
6\. On Stop Conditions: halt immediately, output the condition hit, escalate to human. Do not attempt workaround  
7\. Mark task DONE only when all acceptance criteria pass and Global DOD contract is satisfied  
8\. When all tasks in a slice are DONE, verify slice exit criteria, update \`CURRENT_PHASE.md\`, notify human  
9\. Read \`BUILD_SPEC.md\` section referenced in each task for exact implementation detail  
10\. Read \`DECISIONS.md\` before making any architectural choice not covered by a task spec - DECISIONS.md overrides everything  
<br/>\---  
<br/>\## Global Definition of Done  
<br/>\*\*A task is DONE only when ALL of the following are true:\*\*  
<br/>\- ✓ All acceptance criteria pass  
\- ✓ All files in scope exist, are importable, and contain no syntax errors  
\- ✓ Stop conditions were not hit (if they were, task is BLOCKED not DONE)  
\- ✓ Required tests pass (run \`pytest tests/\` on any test files in scope)  
\- ✓ EVAL.md evaluation gates pass where cited (Tier 2 tasks only - human confirms)  
\- ✓ Dependency graph satisfied - all listed dependencies confirmed DONE  
\- ✓ \`CURRENT_PHASE.md\` updated to reflect task status  
\- ✓ Git working tree clean - \`git add . && git commit -m "feat: \[task-id\] \[description\]"\`  
\- ✓ Reviewer Agent (Bugbot) approval received (Tier 2 tasks only)  
\- ✓ Human completion confirmed (Tier 3 tasks only)  
<br/>\*\*Tier 2 tasks additionally require:\*\*  
\- Builder Agent outputs explicit validation checklist and marks task PENDING VALIDATION  
\- Reviewer Agent (Bugbot) runs static analysis and flags issues before human review  
\- Human confirms EVAL.md threshold met against \`/validation\` dataset  
\- Human explicitly marks DONE - agent cannot self-approve Tier 2  
<br/>\---  
<br/>\## CURRENT_PHASE.md Update Rule  
<br/>\*\*This rule applies between every slice transition. It is not a separate task - it is a mandatory gate.\*\*  
<br/>Before the Builder Agent begins any slice, the human must:  
1\. Update \`CURRENT_PHASE.md\` with the new slice number, active tasks, files in scope, and exit criteria  
2\. Confirm update to Builder Agent before it begins  
3\. Builder Agent must read updated \`CURRENT_PHASE.md\` as its first action each session  
<br/>The Builder Agent must not begin a new slice without a human-confirmed \`CURRENT_PHASE.md\` update. If \`CURRENT_PHASE.md\` still reflects the previous slice, stop and request update.  
<br/>\---  
<br/>\## Status Legend  
<br/>| Status | Meaning |  
|---|---|  
| \`TODO\` | Not started |  
| \`IN PROGRESS\` | Agent currently executing |  
| \`BLOCKED\` | Dependency not DONE or stop condition hit |  
| \`PENDING VALIDATION\` | Tier 2 - built, waiting for human validation gate |  
| \`DONE\` | All Global DOD criteria confirmed |  
<br/>\---  
<br/>\## Human Prerequisite Tasks  
<br/>Complete all H-00x tasks before any agent slice begins. Tier 3 - human only.  
<br/>\---  
<br/>\### H-001 - Collect Validation Datasets  
\*\*Tier:\*\* 3 | \*\*Owner:\*\* Human | \*\*Phase:\*\* Pre-build | \*\*Status:\*\* TODO  
\*\*Blocks:\*\* SIG-011, SIG-014, SIG-017 (Tier 2 validation gates)  
<br/>Collect and save the following fixed datasets to \`/validation/\`. These datasets are frozen at collection - never modified during build. All EVAL.md Tier 2 gates run against these exact files.  
<br/>| Dataset | File | Contents |  
|---|---|---|  
| A | \`/validation/entity_extraction_gold.json\` | 20 raw findings with hand-labeled EntityData ground truth |  
| B | \`/validation/dedup_duplicates.json\` | 20 confirmed duplicate pairs (same event, different source) |  
| C | \`/validation/dedup_false_positives.json\` | 20 confirmed distinct stories (must NOT be flagged as duplicate) |  
| D | \`/validation/scope_filter_gold.json\` | 20 findings: 10 in-scope Indian startups, 10 out-of-scope |  
| E | \`/validation/synthesis_gold.json\` | 5 sets of scored findings with acceptable briefing examples |  
| F | \`/validation/freshness_gold.json\` | 20 findings: 10 fresh, 5 stale, 5 undated |  
<br/>\*\*Done when:\*\* All 6 files exist in \`/validation/\` and are non-empty JSON arrays.  
<br/>\---  
<br/>\### H-002 - API Keys, .env Setup, LangSmith Verification  
\*\*Tier:\*\* 3 | \*\*Owner:\*\* Human | \*\*Phase:\*\* Pre-build | \*\*Status:\*\* TODO  
\*\*Blocks:\*\* SIG-001A  
<br/>1\. Create \`.env\` with all keys from BUILD_SPEC.md Section 1.2  
2\. Create \`.env.example\` with same keys, empty values  
3\. Obtain API keys: OpenAI, Tavily, LangChain (LangSmith)  
4\. Run \`scripts/test_langsmith.py\` - confirm connection prints project list  
5\. Confirm \`GRAPH_VERSION=1.0\` is set in \`.env\`  
<br/>\*\*Done when:\*\* LangSmith script runs without error and prints project list. All keys present in \`.env\`.  
<br/>\---  
<br/>\### H-003 - Repository Init, Venv, Requirements Install  
\*\*Tier:\*\* 3 | \*\*Owner:\*\* Human | \*\*Phase:\*\* Pre-build | \*\*Status:\*\* TODO  
\*\*Blocks:\*\* SIG-001A  
<br/>1\. \`git init\` in project root  
2\. Create \`.gitignore\` per BUILD_SPEC.md Section 1.2  
3\. \`python -m venv venv && source venv/bin/activate\`  
4\. \`pip install -r requirements.txt\` (Phase 1 requirements only)  
5\. \`git add . && git commit -m "chore: initial project scaffold"\`  
<br/>\*\*Done when:\*\* \`pip list\` shows all Phase 1 packages. First commit exists.  
<br/>\---  
<br/>\### H-004 - Supabase Project Creation  
\*\*Tier:\*\* 3 | \*\*Owner:\*\* Human | \*\*Phase:\*\* Pre-Phase 2 | \*\*Status:\*\* TODO  
\*\*Blocks:\*\* SIG-P2-001  
<br/>1\. Create Supabase project at supabase.com  
2\. Enable pgvector: \`create extension if not exists vector\`  
3\. Copy \`SUPABASE_URL\`, \`SUPABASE_ANON_KEY\`, \`SUPABASE_SERVICE_KEY\` into \`.env\`  
4\. Copy \`DATABASE_URL\` (Postgres connection string) into \`.env\` for PostgresSaver  
<br/>\*\*Done when:\*\* Supabase project live, pgvector enabled, all 4 keys in \`.env\`.  
<br/>\---  
<br/>\### H-005 - Gmail App Password Setup  
\*\*Tier:\*\* 3 | \*\*Owner:\*\* Human | \*\*Phase:\*\* Pre-Phase 2 | \*\*Status:\*\* TODO  
\*\*Blocks:\*\* SIG-020A  
<br/>1\. Enable 2FA on Gmail account used for delivery  
2\. Generate App Password: myaccount.google.com → Security → App Passwords  
3\. Add \`GMAIL_ADDRESS\` and \`GMAIL_APP_PASSWORD\` to \`.env\`  
4\. Verify via \`smtplib\` test script - confirm connection  
<br/>\*\*Done when:\*\* Both vars in \`.env\`. Test send confirms SMTP connection works.  
<br/>\---  
<br/>\### H-006 - Northflank Account + Project Setup  
\*\*Tier:\*\* 3 | \*\*Owner:\*\* Human | \*\*Phase:\*\* Pre-Phase 2 | \*\*Status:\*\* TODO  
\*\*Blocks:\*\* SIG-023-deploy  
<br/>1\. Create Northflank account at northflank.com  
2\. Create new project named \`signal\`  
3\. Note project ID and service credentials for deployment task  
<br/>\*\*Done when:\*\* Northflank project exists. Credentials noted. Do not deploy yet.  
<br/>\---  
<br/>\### H-007 - Create CURRENT_PHASE.md  
\*\*Tier:\*\* 3 | \*\*Owner:\*\* Human | \*\*Phase:\*\* Pre-build | \*\*Status:\*\* TODO  
\*\*Blocks:\*\* All agent slices  
<br/>Create \`/CURRENT_PHASE.md\` in project root before any agent session begins. Primary context source for every Builder Agent session (CURSOR_RULES.md Section 9).  
<br/>Required content structure:

# **CURRENT_PHASE.md**

## **Active Slice**

Slice X - \[Slice Name\]

## **Active Tasks**

- TASK-ID: \[name\] - TODO / IN PROGRESS / PENDING VALIDATION

## **Blocked Tasks**

- TASK-ID: \[reason\]

## **Files In Scope This Slice**

- path/to/file.py

## **Slice Exit Criteria**

- \[criterion 1\]
- \[criterion 2\]

## **Last Updated**

YYYY-MM-DD

\*\*Done when:\*\* File exists in project root with Slice 1 content filled in.  
<br/>\---  
<br/>\## Vertical Slice 1 - Foundation  
<br/>\*\*Phase:\*\* 1 | \*\*Owner:\*\* Builder Agent  
\*\*Goal:\*\* Project scaffold, state schema, skeleton graph, test fixtures - all importable with zero errors.  
<br/>\> \*\*Before starting:\*\* Human must update \`CURRENT_PHASE.md\` to Slice 1 and confirm to Builder Agent.  
<br/>\*\*Slice exit criteria:\*\*  
\- \`from agent.state import SignalState, ALLOWED_CATEGORIES, SOURCE_TRUST, ErrorCode\` - no error  
\- \`from tests.fixtures.sample_findings import ALL_SAMPLE_RAW_FINDINGS\` - no error, returns list of 4  
\- \`from agent.graph import graph\` - no error, graph compiles  
\- \`graph.invoke({...initial_state...}, config={"configurable": {"thread_id": "test"}})\` exits cleanly  
\- All 5 fixture assertions in BUILD_SPEC.md Section 3.2 pass  
<br/>\---  
<br/>\### SIG-001A - Repository Foundation  
\*\*Tier:\*\* 1 | \*\*Owner:\*\* Builder Agent | \*\*Phase:\*\* 1 | \*\*Status:\*\* TODO  
\*\*Depends on:\*\* H-002, H-003  
\*\*Spec ref:\*\* BUILD_SPEC.md Section 1.1  
<br/>\*\*Files in Scope:\*\*  
\- Full directory tree per BUILD_SPEC.md Section 1.1  
\- All \`\__init_\_.py\` files in \`agent/\`, \`agent/nodes/\`, \`agent/prompts/\`, \`tests/\`, \`tests/fixtures/\`  
\- \`.env.example\`  
\- \`.gitignore\`  
\- \`requirements.txt\`  
<br/>\*\*Acceptance criteria:\*\*  
\- Directory tree matches BUILD_SPEC.md Section 1.1 exactly  
\- All \`\__init_\_.py\` files present and empty  
\- \`requirements.txt\` contains all Phase 1 packages  
\- \`.env\` is gitignored, \`.env.example\` is committed  
\- \`tree signal/\` output matches expected structure  
<br/>\*\*Stop conditions - escalate to human immediately if:\*\*  
\- \`.env\` file does not exist or is missing any key from BUILD*SPEC.md Section 1.2  
\- \`pip install -r requirements.txt\` fails on any package  
\- Git is not initialized in project root  
<br/>\---  
<br/>\### SIG-001B - State Schema  
\*\*Tier:\*\* 1 | \*\*Owner:\*\* Builder Agent | \*\*Phase:\*\* 1 | \*\*Status:\*\* TODO  
\*\*Depends on:\*\* SIG-001A  
\*\*Spec ref:\*\* BUILD_SPEC.md Section 2  
<br/>\*\*Files in Scope:\*\*  
\- \`agent/state.py\`  
<br/>\*\*Acceptance criteria:\*\*  
\- \`from agent.state import SignalState, RawFinding, EntityData, ScoredFinding, BriefingItem, ALLOWED_CATEGORIES, SOURCE_TRUST, ErrorCode\` - no error  
\- \`raw_findings\` field uses \`Annotated\[list\[RawFinding\], operator.add\]\` - verify by reading the field definition  
\- \`error\` field is \`Optional\[dict\]\`, not \`Optional\[str\]\`  
\- \`source_failures\` and \`graph_version\` both present in \`SignalState\`  
\- \`ScoredFinding\` has \`source_trust_score\` AND \`freshness_penalty_applied\` as separate fields  
\- \`ALLOWED_CATEGORIES\` has exactly 7 values  
\- \`SOURCE_TRUST\` dict has exactly 9 source keys  
<br/>\*\*Stop conditions - escalate to human immediately if:\*\*  
\- \`operator\` import fails  
\- \`typing\` imports (\`Annotated\`, \`TypedDict\`, \`Optional\`) unavailable in Python version  
\- Any circular import detected on \`from agent.state import ...\`  
<br/>\---  
<br/>\### SIG-001C - LangGraph Skeleton  
\*\*Tier:\*\* 1 | \*\*Owner:\*\* Builder Agent | \*\*Phase:\*\* 1 | \*\*Status:\*\* TODO  
\*\*Depends on:\*\* SIG-001B  
\*\*Spec ref:\*\* BUILD_SPEC.md Section 16.1 (structure only - no nodes wired yet)  
<br/>\*\*Files in Scope:\*\*  
\- \`agent/graph.py\`  
<br/>\*\*Acceptance criteria:\*\*  
\- \`from agent.graph import graph\` - no error  
\- \`StateGraph(SignalState)\` compiles with \`MemorySaver\` checkpointer  
\- \`graph.invoke(initial_state, config={"configurable": {"thread_id": "test"}})\` runs without error  
\- Graph is START → END with no intermediate nodes (placeholder - all nodes wired in SIG-010B)  
<br/>\*\*Stop conditions - escalate to human immediately if:\*\*  
\- \`from langgraph.graph import StateGraph, START, END\` fails  
\- \`from langgraph.checkpoint.memory import MemorySaver\` fails  
\- \`graph.compile()\` raises any error  
\- LangGraph version in \`requirements.txt\` incompatible with import  
<br/>\---  
<br/>\### SIG-001D - Test Fixtures  
\*\*Tier:\*\* 1 | \*\*Owner:\*\* Builder Agent | \*\*Phase:\*\* 1 | \*\*Status:\*\* TODO  
\*\*Depends on:\*\* SIG-001B  
\*\*Spec ref:\*\* BUILD_SPEC.md Section 3  
<br/>\*\*Files in Scope:\*\*  
\- \`tests/fixtures/sample_findings.py\`  
<br/>\*\*Acceptance criteria:\*\*  
\- All 8 fixtures defined: \`SAMPLE_FUNDING_FINDING\`, \`SAMPLE_HIRING_FINDING\`, \`SAMPLE_SHUTDOWN_FINDING\`, \`SAMPLE_ACCELERATOR_FINDING\`, \`SAMPLE_OLD_FINDING\`, \`SAMPLE_UNDATED_FINDING\`, \`SAMPLE_OUT_OF_SCOPE_FINDING\`, \`SAMPLE_SCORED_FUNDING_FINDING\`  
\- \`ALL_SAMPLE_RAW_FINDINGS\` is a list of exactly 4 items  
\- \`SAMPLE_UNDATED_FINDING\["published_date"\] is None\`  
\- \`SAMPLE_OLD_FINDING\["published_date"\] == "2024-11-01"\`  
\- \`SAMPLE_OUT_OF_SCOPE_FINDING\["entities"\]\["location"\] == "San Francisco"\`  
\- \`SAMPLE_SCORED_FUNDING_FINDING\["entities"\]\["location"\] == "Bengaluru"\`  
\- All 5 assertions in BUILD_SPEC.md Section 3.2 pass without error  
\- No pytest decorators, no classes, no functions - plain dict literals only  
<br/>\*\*Stop conditions - escalate to human immediately if:\*\*  
\- \`from agent.state import RawFinding, ScoredFinding, EntityData\` fails (SIG-001B not done)  
\- Any fixture dict missing a required TypedDict field  
<br/>\---  
<br/>\## Vertical Slice 2 - Research Pipeline  
<br/>\*\*Phase:\*\* 1 | \*\*Owner:\*\* Builder Agent  
\*\*Goal:\*\* All 4 research nodes return real findings. Combined output ≥5 findings from ≥2 distinct sources.  
<br/>\> \*\*Before starting:\*\* Human must update \`CURRENT_PHASE.md\` to Slice 2 and confirm to Builder Agent.  
<br/>\*\*Slice exit criteria:\*\*  
\- All 4 source nodes individually testable without crashing  
\- Combined \`raw_findings\` across all 4 nodes ≥5 items  
\- ≥2 distinct \`source_name\` values in combined output  
\- \`source_failures\` dict returned by every node  
\- Retry logic present in all 4 node files (confirm by reading \`\_retry\` calls)  
\- No node raises unhandled exception on API timeout or empty result  
<br/>\---  
<br/>\### SIG-002 - Config Loader Node  
\*\*Tier:\*\* 1 | \*\*Owner:\*\* Builder Agent | \*\*Phase:\*\* 1 | \*\*Status:\*\* TODO  
\*\*Depends on:\*\* SIG-001B  
\*\*Spec ref:\*\* BUILD_SPEC.md Section 4  
<br/>\*\*Files in Scope:\*\*  
\- \`agent/nodes/config_loader.py\`  
<br/>\*\*Acceptance criteria:\*\*  
\- \`user_id == "user_001"\`  
\- \`thread_id\` starts with \`"run*"\`  
\- \`source_failures == {"tavily": False, "yc": False, "hn": False, "rss": False}\`  
\- \`graph_version\` reads from \`.env\`, returns \`"1.0"\`  
\- \`procedural_memory\` is a dict with \`high_signal_categories\` key  
\- \`semantic_memory == {}\`  
\- No logging, no try/except, no DB calls in Phase 1  
<br/>\*\*Stop conditions - escalate to human immediately if:\*\*  
\- \`GRAPH_VERSION\` key missing from \`.env\`  
\- \`python-dotenv\` not installed  
\- \`from agent.state import SignalState\` fails  
<br/>\---  
<br/>\### SIG-003 - Search Planner Node  
\*\*Tier:\*\* 1 | \*\*Owner:\*\* Builder Agent | \*\*Phase:\*\* 1 | \*\*Status:\*\* TODO  
\*\*Depends on:\*\* SIG-002  
\*\*Spec ref:\*\* BUILD_SPEC.md Section 5  
<br/>\*\*Files in Scope:\*\*  
\- \`agent/nodes/search_planner.py\`  
<br/>\*\*Acceptance criteria:\*\*  
\- \`query_plan\` has exactly 4 keys: \`"tavily"\`, \`"yc"\`, \`"hn"\`, \`"rss"\`  
\- Tavily queries list has ≥5 entries  
\- YC queries list has exactly 2 entries, both starting with \`"batch="\`  
\- Batch codes computed from \`datetime.now()\` - not hardcoded strings  
\- \`sources_queried == \["tavily", "yc", "hn", "rss"\]\`  
\- No LLM call, no API call - pure deterministic Python only  
<br/>\*\*Stop conditions - escalate to human immediately if:\*\*  
\- \`state\["procedural_memory"\]\` is missing or not a dict (SIG-002 did not return correctly)  
\- \`datetime\` import fails  
\- YC batch computation returns empty list  
<br/>\---  
<br/>\### SIG-004 - Tavily Search Node  
\*\*Tier:\*\* 1 | \*\*Owner:\*\* Builder Agent | \*\*Phase:\*\* 1 | \*\*Status:\*\* TODO  
\*\*Depends on:\*\* SIG-003  
\*\*Spec ref:\*\* BUILD_SPEC.md Section 6.2  
<br/>\*\*Files in Scope:\*\*  
\- \`agent/nodes/tavily_search.py\`  
<br/>\*\*Acceptance criteria:\*\*  
\- \`INCLUDE_DOMAINS\` list applied on every Tavily call - confirmed by reading code  
\- \`\_retry\` called with \`max_attempts=3, backoff=\[5, 15\]\`  
\- Returns \`{"raw_findings": \[...\], "source_failures": {...}}\`  
\- \`source_failures\["tavily"\]\` is \`True\` only if ALL queries fail after all retries  
\- Node does not crash on Tavily timeout - exception caught, query skipped, run continues  
\- Each finding has all 5 \`RawFinding\` fields populated  
\- \`source_name\` resolved via \`\_domain_to_source()\` helper  
<br/>\*\*Stop conditions - escalate to human immediately if:\*\*  
\- \`TAVILY_API_KEY\` missing from \`.env\` or returns 401  
\- \`from tavily import TavilyClient\` fails - package not installed  
\- \`state\["query_plan"\]\["tavily"\]\` key missing (SIG-003 not done)  
\- \`include_domains\` is not passed to \`client.search()\` - this is a hard architectural rule  
<br/>\---  
<br/>\### SIG-005 - YC API Node  
\*\*Tier:\*\* 1 | \*\*Owner:\*\* Builder Agent | \*\*Phase:\*\* 1 | \*\*Status:\*\* TODO  
\*\*Depends on:\*\* SIG-003  
\*\*Spec ref:\*\* BUILD_SPEC.md Section 6.3  
<br/>\*\*Files in Scope:\*\*  
\- \`agent/nodes/yc_api.py\`  
<br/>\*\*Acceptance criteria:\*\*  
\- Batch code extracted dynamically from \`query_plan\["yc"\]\` - never hardcoded  
\- URL format: \`<https://api.ycombinator.com/v0.1/companies?batch={code}&country=India\`>  
\- \`\_retry\` called with \`max_attempts=3, backoff=\[5, 15\]\`  
\- Returns \`{"raw_findings": \[...\], "source_failures": {...}}\`  
\- \`source_name == "yc"\` on all findings from this node  
<br/>\*\*Stop conditions - escalate to human immediately if:\*\*  
\- \`state\["query_plan"\]\["yc"\]\` key missing or empty list  
\- \`httpx\` not installed  
\- YC API returns non-JSON response and all 3 retries exhausted  
<br/>\---  
<br/>\### SIG-006 - HN Algolia Node  
\*\*Tier:\*\* 1 | \*\*Owner:\*\* Builder Agent | \*\*Phase:\*\* 1 | \*\*Status:\*\* TODO  
\*\*Depends on:\*\* SIG-003  
\*\*Spec ref:\*\* BUILD_SPEC.md Section 6.4  
<br/>\*\*Files in Scope:\*\*  
\- \`agent/nodes/hn_algolia.py\`  
<br/>\*\*Acceptance criteria:\*\*  
\- Query URL encoded with \`urllib.parse.quote\`  
\- Findings with no title skipped silently  
\- \`\_retry\` called with \`max_attempts=3, backoff=\[5, 15\]\`  
\- Returns \`{"raw_findings": \[...\], "source_failures": {...}}\`  
\- \`source_name == "hn"\` on all findings  
<br/>\*\*Stop conditions - escalate to human immediately if:\*\*  
\- \`state\["query_plan"\]\["hn"\]\` key missing  
\- \`httpx\` not installed  
\- \`urllib.parse.quote\` import fails  
<br/>\---  
<br/>\### SIG-007 - Google News RSS Node  
\*\*Tier:\*\* 1 | \*\*Owner:\*\* Builder Agent | \*\*Phase:\*\* 1 | \*\*Status:\*\* TODO  
\*\*Depends on:\*\* SIG-003  
\*\*Spec ref:\*\* BUILD_SPEC.md Section 6.5  
<br/>\*\*Files in Scope:\*\*  
\- \`agent/nodes/google_news_rss.py\`  
<br/>\*\*Acceptance criteria:\*\*  
\- \`feedparser.parse\` called on both feed URLs from \`query_plan\["rss"\]\`  
\- \`\_retry\` called with \`max_attempts=2, backoff=\[5\]\`  
\- Max 10 entries per feed processed  
\- Returns \`{"raw_findings": \[...\], "source_failures": {...}}\`  
\- \`source_name == "google_news"\` on all findings  
<br/>\*\*Stop conditions - escalate to human immediately if:\*\*  
\- \`feedparser\` not installed  
\- \`state\["query_plan"\]\["rss"\]\` key missing or empty list  
\- Both feeds return no entries after all retries - log and continue (do not stop run), but flag \`source_failures\["rss"\] = True\`  
<br/>\---  
<br/>\### SIG-008 - Reducer Node  
\*\*Tier:\*\* 1 | \*\*Owner:\*\* Builder Agent | \*\*Phase:\*\* 1 | \*\*Status:\*\* TODO  
\*\*Depends on:\*\* SIG-004, SIG-005, SIG-006, SIG-007  
\*\*Spec ref:\*\* BUILD_SPEC.md Section 7  
<br/>\*\*Files in Scope:\*\*  
\- \`agent/nodes/reducer.py\`  
<br/>\*\*Acceptance criteria:\*\*  
\- Returns \`raw_findings\` unchanged - no transformation, no filtering, no dedup  
\- \`len(output\["raw_findings"\]) == len(input\["raw_findings"\])\`  
\- Print statement \`f"Reducer: {N} total findings merged from all research nodes"\` visible in output  
\- Node is confirmed pass-through by reading the code - single print + return only  
<br/>\*\*Stop conditions - escalate to human immediately if:\*\*  
\- \`state\["raw_findings"\]\` is not a list (Annotated reducer not working - state schema error in SIG-001B)  
\- Output list shorter than input list (transformation occurred - not allowed in this node)  
<br/>\---  
<br/>\## Vertical Slice 3 - Processing Pipeline + Phase 1 Complete  
<br/>\*\*Phase:\*\* 1 | \*\*Owner:\*\* Builder Agent (Tier 1) / Builder Agent + Reviewer Agent (Tier 2)  
\*\*Goal:\*\* Full 15-node pipeline wired and running end-to-end. Phase 1 Definition of Done passes.  
<br/>\> \*\*Before starting:\*\* Human must update \`CURRENT_PHASE.md\` to Slice 3 and confirm to Builder Agent.  
<br/>\*\*Slice exit criteria (Phase 1 Definition of Done - BUILD_SPEC.md Section 16.4):\*\*  
\- \`python scripts/run_agent.py\` completes end-to-end with no unhandled exceptions  
\- Briefing is readable markdown with all 4 sections  
\- ≥5 deduplicated items in \`new_findings\`  
\- ≥2 distinct \`source_name\` values in \`new_findings\`  
\- \`findings_dropped_freshness > 0\`  
\- All \`category\` values are in \`ALLOWED_CATEGORIES\`  
\- Reducer print visible in run output  
\- Episodic memory writer print visible confirming items recorded  
\- Run metrics writer print visible showing \`graph_version\` and per-source health  
\- LangSmith shows complete trace with all 15 node spans  
\- \`estimated_cost_usd\` non-zero and < \$0.50  
\- All criteria in \`GOLDEN_RUN_SPEC.md\` satisfied  
<br/>\---  
<br/>\### SIG-009 - Freshness Validation Node  
\*\*Tier:\*\* 1 | \*\*Owner:\*\* Builder Agent | \*\*Phase:\*\* 1 | \*\*Status:\*\* TODO  
\*\*Depends on:\*\* SIG-008, SIG-001D  
\*\*Spec ref:\*\* BUILD_SPEC.md Section 8  
<br/>\*\*Files in Scope:\*\*  
\- \`agent/nodes/freshness_validation.py\`  
<br/>\*\*Acceptance criteria:\*\*  
\- \`FRESHNESS_WINDOW_DAYS = 30\` constant defined  
\- Three date format strings attempted in order per BUILD_SPEC.md Section 8.1  
\- \`SAMPLE_OLD_FINDING\` (date \`"2024-11-01"\`) → dropped  
\- \`SAMPLE_UNDATED_FINDING\` (date \`None\`) → kept with \`freshness_penalized: True\`  
\- \`SAMPLE_FUNDING_FINDING\` (recent date) → kept with \`freshness_penalized: False\`  
\- Returns \`findings_retrieved\` = total input count before filtering  
\- Returns \`findings_dropped_freshness\` = confirmed stale count only  
\- No LLM, no API calls  
<br/>\*\*Stop conditions - escalate to human immediately if:\*\*  
\- \`state\["raw_findings"\]\` is empty list (all research nodes failed - check SIG-004 through SIG-007)  
\- All findings dropped (100% drop rate - likely date parsing bug, not expected data condition)  
<br/>\---  
<br/>\### SIG-011 - Entity Extraction Node  
\*\*Tier:\*\* 2 | \*\*Owner:\*\* Builder Agent + Reviewer Agent | \*\*Phase:\*\* 1 | \*\*Status:\*\* TODO  
\*\*Depends on:\*\* SIG-009, SIG-001D, H-001 (Dataset A required for validation gate)  
\*\*Spec ref:\*\* BUILD_SPEC.md Section 9  
\*\*Eval ref:\*\* EVAL.md Section 5 (Entity Extraction - threshold: ≥90% accuracy on Dataset A)  
<br/>\*\*Files in Scope:\*\*  
\- \`agent/nodes/entity_extraction.py\`  
\- \`agent/prompts/entity_extraction_v3.txt\`  
<br/>\*\*Acceptance criteria (Builder Agent builds - then STOP for validation):\*\*  
\- Prompt v3 text saved to \`agent/prompts/entity_extraction_v3.txt\` exactly as specified in BUILD_SPEC.md Section 9.1 - do not alter prompt wording  
\- Model: \`gpt-4o-mini\`, \`temperature=0\`, \`max_tokens=400\`  
\- Invalid \`category\` value → fallback to \`"funding"\`, log violation - do not raise  
\- \`confidence_score = max(0.0, source_trust_score - (0.10 if freshness_penalty_applied else 0.0))\`  
\- \`is_duplicate = False\`, \`duplicate_reason = None\` on all output findings  
\- JSON parse error → print error, skip finding, continue run - do not abort  
\- LangSmith trace visible for this node  
\- Reviewer Agent (Bugbot) flags any issues before human review  
<br/>\*\*Human validation gate (PENDING VALIDATION - human confirms):\*\*  
\- Run against Dataset A (\`/validation/entity_extraction_gold.json\`)  
\- Field-level accuracy ≥ 90% per EVAL.md Section 5 (DEC-006, DEC-010)  
\- \`announced_date\` populated correctly on ≥80% of funding articles  
\- \`category\` is always a valid member of \`ALLOWED_CATEGORIES\` across all 20 samples  
\- Mark DONE only after human confirms threshold met against Dataset A  
<br/>\*\*Stop conditions - escalate to human immediately if:\*\*  
\- \`OPENAI_API_KEY\` missing or returns 401  
\- \`from openai import OpenAI\` fails  
\- Prompt file \`entity_extraction_v3.txt\` does not exist  
\- JSON parse failure rate > 50% of findings (prompt or API issue - do not continue)  
\- \`gpt-4o-mini\` model name returns 404 (model deprecated - escalate immediately)  
<br/>\---  
<br/>\### SIG-012 - Scope Filter Node  
\*\*Tier:\*\* 1 | \*\*Owner:\*\* Builder Agent | \*\*Phase:\*\* 1 | \*\*Status:\*\* TODO  
\*\*Depends on:\*\* SIG-011  
\*\*Spec ref:\*\* BUILD_SPEC.md Section 10  
<br/>\*\*Files in Scope:\*\*  
\- \`agent/nodes/scope_filter.py\`  
<br/>\*\*Acceptance criteria:\*\*  
\- \`NON_INDIA_LOCATIONS\` list applied case-insensitively on \`entities.location\`  
\- Amount filter: drop if \`&lt; 500_000\` OR \`&gt; 50_000_000\` USD - only when \`funding_amount_usd\` is not None  
\- Stage filter: \`OUT_OF_SCOPE_STAGES\` set applied  
\- Null fields → never drop (explicit out-of-scope evidence required to drop)  
\- 6-finding test from BUILD_SPEC.md Section 10.2: exactly 3 kept, 3 dropped  
\- Returns \`findings_dropped_scope\` count  
\- No LLM, no API calls  
<br/>\*\*Stop conditions - escalate to human immediately if:\*\*  
\- \`state\["scored_findings"\]\` is empty list (SIG-011 produced zero output - check entity extraction)  
\- All findings dropped (100% drop rate - scope filter logic error, not expected)  
<br/>\---  
<br/>\### SIG-013 - Source Trust Scoring Node  
\*\*Tier:\*\* 1 | \*\*Owner:\*\* Builder Agent | \*\*Phase:\*\* 1 | \*\*Status:\*\* TODO  
\*\*Depends on:\*\* SIG-012  
\*\*Spec ref:\*\* BUILD_SPEC.md Section 11  
<br/>\*\*Files in Scope:\*\*  
\- \`agent/nodes/source_trust_scoring.py\`  
<br/>\*\*Acceptance criteria:\*\*  
\- Output list sorted by \`confidence_score\` descending  
\- \`len(output\["scored_findings"\]) == len(input\["scored_findings"\])\` - no findings added or removed  
\- Single sort operation, no other logic - confirmed by reading code  
<br/>\*\*Stop conditions - escalate to human immediately if:\*\*  
\- \`confidence_score\` field missing from any finding (SIG-011 schema error)  
\- Output list is shorter than input list (filtering occurred - not allowed in this node)  
<br/>\---  
<br/>\### SIG-014 - Hybrid Dedup Node (Phase 1)  
\*\*Tier:\*\* 2 | \*\*Owner:\*\* Builder Agent + Reviewer Agent | \*\*Phase:\*\* 1 | \*\*Status:\*\* TODO  
\*\*Depends on:\*\* SIG-013, SIG-001D, H-001 (Datasets B and C required for validation gate)  
\*\*Spec ref:\*\* BUILD_SPEC.md Section 12.1  
\*\*Eval ref:\*\* EVAL.md Section 6 (Dedup - thresholds: recall ≥85% on Dataset B, 0 false positives on Dataset C)  
<br/>\*\*Files in Scope:\*\*  
\- \`agent/nodes/hybrid_dedup.py\`  
<br/>\*\*Acceptance criteria (Builder Agent builds - then STOP for validation):\*\*  
\- Stage 0: \`company_name_normalized + "|" + announced_date\` pre-filter key - only when both fields are non-empty  
\- Stage 1: URL exact match against \`seen_urls\`  
\- Stage 2: Normalized title exact match against \`seen_titles\`  
\- Stages run in order 0 → 1 → 2, first match wins (DEC-002 - cheap checks first)  
\- \`new_findings\` contains only non-duplicates  
\- \`is_duplicate = True\` + \`duplicate_reason\` set on all dropped findings  
\- \`semantic_memory\` returned with all three seen sets updated as lists  
\- Returns \`findings_dropped_dedup\` count  
\- Reviewer Agent (Bugbot) confirms stage ordering before human review  
<br/>\*\*Human validation gate (PENDING VALIDATION - human confirms):\*\*  
\- Run against Dataset B (\`/validation/dedup_duplicates.json\`) per EVAL.md Section 6 - recall ≥85% (catches ≥17/20 confirmed duplicates)  
\- Run against Dataset C (\`/validation/dedup_false_positives.json\`) per EVAL.md Section 6 - 0 false positives (0/20 incorrectly flagged)  
\- Mark DONE only after human confirms both thresholds met against Datasets B and C  
<br/>\*\*Stop conditions - escalate to human immediately if:\*\*  
\- \`state\["semantic_memory"\]\` is not a dict  
\- \`state\["scored_findings"\]\` is empty (SIG-013 produced no output)  
\- Stage ordering is wrong - Stage 1 runs before Stage 0 (violates DEC-002)  
<br/>\---  
<br/>\### SIG-017 - Synthesis Node  
\*\*Tier:\*\* 2 | \*\*Owner:\*\* Builder Agent + Reviewer Agent | \*\*Phase:\*\* 1 | \*\*Status:\*\* TODO  
\*\*Depends on:\*\* SIG-014, H-001 (Dataset E required for validation gate)  
\*\*Spec ref:\*\* BUILD_SPEC.md Section 13  
\*\*Eval ref:\*\* EVAL.md Section 7 (Synthesis - threshold: all 4 sections present, zero hallucinations verified against input findings)  
<br/>\*\*Files in Scope:\*\*  
\- \`agent/nodes/synthesis.py\`  
<br/>\*\*Acceptance criteria (Builder Agent builds - then STOP for validation):\*\*  
\- Model: \`gpt-4o\`, \`temperature=0.3\`, \`max_tokens=1500\`  
\- Empty \`new_findings\` → returns \`"No new findings this week."\` immediately, no LLM call made  
\- Context string per finding uses category, title, source_name, confidence_score, summary  
\- \`briefing_final = briefing_draft\` in Phase 1 (overwritten by HITL in Phase 2)  
\- \`briefing_items\` has one \`BriefingItem\` per entry in \`new_findings\`  
\- Token cost: \`response.usage.total_tokens \* 0.000005\`  
\- GPT-4o trace visible in LangSmith  
\- Reviewer Agent (Bugbot) checks for any hallucinated company names before human review  
<br/>\*\*Human validation gate (PENDING VALIDATION - human confirms):\*\*  
\- Generate briefings from 3 different \`new_findings\` sets including Dataset E per EVAL.md Section 7  
\- All briefings contain all 4 sections: Executive Summary, Funding Highlights, Ecosystem Moves, Trends to Watch  
\- Zero hallucinated company names or funding amounts - verify each claim against input findings  
\- \`briefing_items\` count matches \`new_findings\` count  
\- Mark DONE only after human confirms quality against Dataset E  
<br/>\*\*Stop conditions - escalate to human immediately if:\*\*  
\- \`OPENAI_API_KEY\` missing or \`gpt-4o\` returns 404  
\- \`state\["new_findings"\]\` is missing (SIG-014 did not return correctly)  
\- Synthesis fails after 1 retry - set \`error.code = SYNTHESIS_FAILED\`, abort run, escalate  
<br/>\---  
<br/>\### SIG-019 - Episodic Memory Writer Node (Phase 1 Stub)  
\*\*Tier:\*\* 1 | \*\*Owner:\*\* Builder Agent | \*\*Phase:\*\* 1 | \*\*Status:\*\* TODO  
\*\*Depends on:\*\* SIG-017  
\*\*Spec ref:\*\* BUILD_SPEC.md Section 14  
<br/>\*\*Files in Scope:\*\*  
\- \`agent/nodes/episodic_memory_writer.py\`  
<br/>\*\*Critical ordering rule (DEC-004):\*\* In Phase 1, HITL does not exist - this node runs unconditionally after synthesis. Phase 2 conditional routing (Approve/Edit paths only) is added in SIG-018 via graph edges. Do not add any HITL-awareness to this node - the graph handles routing.  
<br/>\*\*Acceptance criteria:\*\*  
\- \`EPISODIC_MEMORY_STORE = \[\]\` defined at module level  
\- Returns \`{}\`  
\- \`EPISODIC_MEMORY_STORE\` length increases by 1 after each call  
\- Episode dict contains: \`run_id\`, \`thread_id\`, \`timestamp\`, \`item_titles\`, \`source_urls\`, \`company_names_normalized\`, \`briefing_summary\`  
\- \`briefing_summary\` truncated to 200 chars  
\- Print statement: \`f"Episodic memory written: {N} items recorded for run {run_id}"\`  
<br/>\*\*Stop conditions - escalate to human immediately if:\*\*  
\- \`state\["new_findings"\]\` is missing  
\- \`state\["run_id"\]\` is missing or empty string  
\- \`state\["briefing_final"\]\` is missing (SIG-017 did not complete correctly)  
<br/>\---  
<br/>\### SIG-021 - Run Metrics Writer Node (Phase 1 Stub)  
\*\*Tier:\*\* 1 | \*\*Owner:\*\* Builder Agent | \*\*Phase:\*\* 1 | \*\*Status:\*\* TODO  
\*\*Depends on:\*\* SIG-019  
\*\*Spec ref:\*\* BUILD_SPEC.md Section 15  
<br/>\*\*Files in Scope:\*\*  
\- \`agent/nodes/run_metrics_writer.py\`  
<br/>\*\*Acceptance criteria:\*\*  
\- Returns \`{}\`  
\- Console output shows all metrics including \`graph_version\` and \`source_health\` on separate lines  
\- \`findings_dropped_freshness\` and \`findings_dropped_scope\` printed as separate counters - never combined  
\- Warning line printed for any source where \`source_failures\[source\] == True\`  
\- Runs on BOTH approve and reject paths in Phase 2 (graph routing enforces this - node itself is path-agnostic)  
<br/>\*\*Stop conditions - escalate to human immediately if:\*\*  
\- \`state\["graph_version"\]\` missing - indicates SIG-002 config loader error  
\- \`state\["source_failures"\]\` missing - indicates research pipeline state error  
<br/>\---  
<br/>\### SIG-010B - Full Graph Wiring + Run Script  
\*\*Tier:\*\* 1 | \*\*Owner:\*\* Builder Agent | \*\*Phase:\*\* 1 | \*\*Status:\*\* TODO  
\*\*Depends on:\*\* SIG-001C, SIG-002, SIG-003, SIG-004, SIG-005, SIG-006, SIG-007, SIG-008, SIG-009, SIG-011, SIG-012, SIG-013, SIG-014, SIG-017, SIG-019, SIG-021  
\*\*Spec ref:\*\* BUILD_SPEC.md Section 16  
<br/>\*\*Files in Scope:\*\*  
\- \`agent/graph.py\` (replace skeleton from SIG-001C with full 15-node graph)  
\- \`scripts/run_agent.py\`  
<br/>\*\*Acceptance criteria:\*\*  
\- All 15 nodes wired in exact order per BUILD_SPEC.md Section 16.1  
\- \`MemorySaver\` as checkpointer  
\- \`run_graph()\` function builds complete \`initial_state\` internally - no args required  
\- \`python scripts/run_agent.py\` runs to completion  
\- All Phase 1 Definition of Done criteria in BUILD_SPEC.md Section 16.4 pass  
\- All criteria in \`GOLDEN_RUN_SPEC.md\` satisfied - confirmed by human review  
\- LangSmith trace shows all 15 node spans  
\- \`estimated_cost_usd\` non-zero and < \$0.50  
<br/>\*\*Stop conditions - escalate to human immediately if:\*\*  
\- Any node import fails - do not proceed with partial graph  
\- \`graph.compile()\` raises any error  
\- \`graph.invoke()\` raises unhandled exception outside of node-level try/except  
\- LangSmith shows fewer than 15 node spans (node not wired)  
\- \`GOLDEN_RUN_SPEC.md\` criteria not met - do not mark Phase 1 DONE  
<br/>\---  
<br/>\## Vertical Slice 4 - Phase 2 Infrastructure + HITL  
<br/>\*\*Phase:\*\* 2 | \*\*Owner:\*\* Builder Agent  
\*\*Goal:\*\* PostgresSaver live, HITL interrupt working, conditional routing correct per DEC-004, delivery working, all memory and metrics writing to Supabase.  
<br/>\*\*Prerequisites before starting this slice:\*\* H-004 (Supabase) and H-005 (Gmail) must be DONE.  
<br/>\> \*\*Before starting:\*\* Human must update \`CURRENT_PHASE.md\` to Slice 4 and confirm to Builder Agent.  
<br/>\*\*Slice exit criteria:\*\*  
\- \`MemorySaver\` fully replaced by \`PostgresSaver\` - graph state persists across process restarts  
\- \`graph.invoke\` pauses at \`hitl_node\` - confirmed via LangSmith interrupt span  
\- Approve path: \`episodic_memory_writer\` executes → delivery proceeds → episode in PostgresStore  
\- Reject path: \`discard_and_log\` executes → \`episodic_memory_writer\` does NOT execute → no episode in PostgresStore (DEC-004, EVAL.md Section 13)  
\- \`run_metrics_writer\` executes on BOTH approve and reject paths  
\- Approved briefing arrives in \`delivery_email\` inbox  
\- \`agent_run_metrics\` table has one row per run with \`graph_version\` and \`source_health\` as separate columns  
\- Embedding dedup (SIG-014B) catches fuzzy duplicate that stages 0-2 missed  
<br/>\---  
<br/>\### SIG-P2-001 - Supabase Schema Migration  
\*\*Tier:\*\* 1 | \*\*Owner:\*\* Builder Agent | \*\*Phase:\*\* 2 | \*\*Status:\*\* TODO  
\*\*Depends on:\*\* H-004, SIG-010B (Phase 1 DOD must pass first)  
\*\*Spec ref:\*\* BUILD_SPEC.md Section 21, PRD Section 18  
<br/>\*\*Files in Scope:\*\*  
\- \`scripts/migrate_supabase.py\`  
<br/>\*\*Acceptance criteria:\*\*  
\- All tables created: \`users\`, \`user_configs\`, \`briefing_runs\`, \`briefing_items\`, \`agent_run_metrics\`, \`user_feedback\`  
\- \`agent_run_metrics\` has \`graph_version text\` and \`source_health jsonb\` as separate columns  
\- \`briefing_runs\` has \`graph_version text\` column  
\- \`briefing_items\` has \`embedding vector(1536)\` column (pgvector)  
\- Migration script uses \`CREATE TABLE IF NOT EXISTS\` - idempotent, safe to re-run  
\- RLS enabled on all tables  
\- Additional columns per BUILD_SPEC.md Section 21 added if not already present  
<br/>\*\*Stop conditions - escalate to human immediately if:\*\*  
\- \`SUPABASE_URL\` or \`SUPABASE_SERVICE_KEY\` missing from \`.env\`  
\- pgvector extension not enabled - \`create extension if not exists vector\` must succeed first (H-004)  
\- Any table creation fails with a non-\`already exists\` error  
\- \`vector(1536)\` column type rejected - pgvector version incompatible  
<br/>\---  
<br/>\### SIG-P2-002 - PostgresSaver + PostgresStore Migration  
\*\*Tier:\*\* 1 | \*\*Owner:\*\* Builder Agent | \*\*Phase:\*\* 2 | \*\*Status:\*\* TODO  
\*\*Depends on:\*\* SIG-P2-001  
\*\*Spec ref:\*\* BUILD_SPEC.md Section 17.1  
<br/>\*\*Files in Scope:\*\*  
\- \`agent/graph.py\`  
<br/>\*\*Acceptance criteria:\*\*  
\- \`MemorySaver\` replaced by \`PostgresSaver\` using \`DATABASE_URL\` from \`.env\`  
\- \`InMemoryStore\` replaced by \`PostgresStore\` for all memory namespaces  
\- \`graph.compile(checkpointer=postgres_saver, store=postgres_store)\`  
\- \`python scripts/run_agent.py\` still runs end-to-end after migration  
\- Kill process mid-run, restart → graph resumes from last checkpoint (verify via LangSmith)  
<br/>\*\*Stop conditions - escalate to human immediately if:\*\*  
\- \`DATABASE_URL\` missing from \`.env\`  
\- \`PostgresSaver\` import fails - package not in \`requirements.txt\`  
\- \`graph.compile()\` raises error with new checkpointer  
\- Process restart does not resume from checkpoint (PostgresSaver not persisting correctly)  
<br/>\---  
<br/>\### SIG-002B - Config Loader Phase 2 Supabase Upgrade  
\*\*Tier:\*\* 1 | \*\*Owner:\*\* Builder Agent | \*\*Phase:\*\* 2 | \*\*Status:\*\* TODO  
\*\*Depends on:\*\* SIG-P2-001, SIG-P2-002  
\*\*Spec ref:\*\* BUILD_SPEC.md Section 4.1 ("Phase 2 reads from Supabase \`user_configs\` table")  
<br/>\*\*Files in Scope:\*\*  
\- \`agent/nodes/config_loader.py\`  
<br/>\*\*Acceptance criteria:\*\*  
\- Phase 1 hardcoded static \`user_config\` dict replaced with Supabase read from \`user_configs\` table filtered by \`user_id\`  
\- Fallback to static defaults if no row found for \`user_id\` (graceful degradation)  
\- Phase 2 \`procedural_memory\` reads from PostgresStore namespace \`("user", user_id, "procedural")\` if exists, falls back to defaults  
\- \`semantic_memory\` reads from PostgresStore namespace \`("user", user_id, "semantic")\` if exists, falls back to \`{}\`  
\- All other return fields unchanged from Phase 1 contract  
\- \`GET /config\` and \`PUT /config\` API endpoints work correctly after this upgrade (reads/writes to \`user_configs\`)  
<br/>\*\*Stop conditions - escalate to human immediately if:\*\*  
\- \`SUPABASE_URL\` or \`SUPABASE_SERVICE_KEY\` missing from \`.env\`  
\- \`user_configs\` table does not exist (SIG-P2-001 not complete)  
\- PostgresStore unavailable (SIG-P2-002 not complete)  
\- Supabase read raises exception - must not crash run, must fall back to defaults  
<br/>\---  
<br/>\### SIG-018 - HITL Node + Phase 2 Conditional Graph Routing  
\*\*Tier:\*\* 1 | \*\*Owner:\*\* Builder Agent | \*\*Phase:\*\* 2 | \*\*Status:\*\* TODO  
\*\*Depends on:\*\* SIG-P2-002, SIG-017  
\*\*Spec ref:\*\* BUILD_SPEC.md Section 17.1, 17.2, 17.3  
<br/>\*\*Files in Scope:\*\*  
\- \`agent/nodes/hitl.py\`  
\- \`agent/nodes/discard_and_log.py\`  
\- \`agent/graph.py\`  
\- \`scripts/test_hitl.py\`  
<br/>\*\*Critical - DEC-004 compliance:\*\* The conditional routing after \`hitl_node\` is the sole enforcement mechanism for DEC-004. The \`episodic_memory_writer\` node has no HITL awareness - graph edges determine whether it runs. This wiring must be exact.  
<br/>\*\*Acceptance criteria:\*\*  
\- \`hitl_node\` uses \`from langgraph.types import interrupt\`  
\- \`route_after_hitl()\` returns \`"episodic_memory_writer"\` for approve/edit, \`"discard_and_log"\` for reject  
\- \`add_conditional_edges("hitl_node", route_after_hitl, {...})\` wired correctly in \`graph.py\`  
\- \`discard_and_log\` prints rejection message, returns \`{"delivery_status": "rejected"}\`  
\- Graph edge chain: \`synthesis → hitl_node → \[conditional\] → episodic_memory_writer → delivery → run_metrics_writer\` OR \`discard_and_log → run_metrics_writer\`  
\- \`scripts/test_hitl.py\` verifies approve path: episode exists in PostgresStore after approve  
\- \`scripts/test_hitl.py\` verifies reject path: no episode in PostgresStore after reject (DEC-004)  
\- \`run_metrics_writer\` executes on BOTH paths - verified in test script  
<br/>\*\*Stop conditions - escalate to human immediately if:\*\*  
\- \`interrupt\` import fails - LangGraph version incompatible with HITL  
\- \`PostgresSaver\` not active - \`interrupt()\` will not persist state (SIG-P2-002 not complete)  
\- \`route_after_hitl\` returns wrong branch for reject - stop immediately, DEC-004 violation risk  
\- Episode found in PostgresStore after reject path - hard DEC-004 violation, stop build  
<br/>\---  
<br/>\### SIG-014B - Hybrid Dedup Phase 2 Embedding Upgrade  
\*\*Tier:\*\* 1 | \*\*Owner:\*\* Builder Agent | \*\*Phase:\*\* 2 | \*\*Status:\*\* TODO  
\*\*Depends on:\*\* SIG-P2-001, SIG-014  
\*\*Spec ref:\*\* BUILD_SPEC.md Section 12.2  
<br/>\*\*Files in Scope:\*\*  
\- \`agent/nodes/hybrid_dedup.py\`  
<br/>\*\*Acceptance criteria:\*\*  
\- Stage 3 added after Stage 2 in \`hybrid_dedup\` - Stages 0→1→2→3 in order (DEC-002)  
\- \`text-embedding-3-small\` used for embedding generation (DEC-014)  
\- Cosine threshold: \`> 0.85\` = hard duplicate, \`0.75-0.85\` = near-duplicate (keep, flag \`related_to_previous_coverage: True\`) (DEC-014)  
\- Embeddings stored in \`briefing_items.embedding\` (vector(1536)) in Supabase  
\- Fuzzy duplicate test: same company, same funding round, different publication, different URL, similar but not identical title → caught by Stage 3 only  
\- Genuinely different article from different company → NOT flagged by Stage 3  
<br/>\*\*Stop conditions - escalate to human immediately if:\*\*  
\- \`text-embedding-3-small\` returns 404 - model name changed, escalate  
\- pgvector \`briefing_items.embedding\` column missing (SIG-P2-001 not complete)  
\- Stage 3 runs before Stages 0-2 - violates DEC-002, stop immediately  
\- Cosine threshold hardcoded at any value other than 0.85 - violates DEC-014  
<br/>\---  
<br/>\### SIG-019B - Episodic Memory Writer Phase 2 Upgrade  
\*\*Tier:\*\* 1 | \*\*Owner:\*\* Builder Agent | \*\*Phase:\*\* 2 | \*\*Status:\*\* TODO  
\*\*Depends on:\*\* SIG-P2-002, SIG-019, SIG-018  
\*\*Spec ref:\*\* BUILD_SPEC.md Section 14.3  
<br/>\*\*Files in Scope:\*\*  
\- \`agent/nodes/episodic_memory_writer.py\`  
<br/>\*\*Acceptance criteria:\*\*  
\- \`EPISODIC_MEMORY_STORE.append(episode)\` replaced with \`store.put(namespace=("user", user_id, "episodic"), key=run_id, value=episode)\`  
\- Function signature unchanged - only internals changed  
\- Graph routing (Approve/Edit only, enforced by SIG-018 edges) unchanged - this node has no HITL-awareness  
\- After approve run: \`store.get(namespace=("user", "user_001", "episodic"), key=run_id)\` returns episode  
\- After reject run: same call returns nothing (DEC-004) - verified via \`scripts/test_hitl.py\`  
<br/>\*\*Stop conditions - escalate to human immediately if:\*\*  
\- \`PostgresStore\` not available (SIG-P2-002 not complete)  
\- \`store.put()\` raises exception - do not silently swallow, escalate  
\- Episode found after reject path (DEC-004 violation - stop build, escalate immediately)  
<br/>\---  
<br/>\### SIG-020A - Gmail Delivery Node  
\*\*Tier:\*\* 1 | \*\*Owner:\*\* Builder Agent | \*\*Phase:\*\* 2 | \*\*Status:\*\* TODO  
\*\*Depends on:\*\* SIG-019B, H-005  
\*\*Spec ref:\*\* BUILD_SPEC.md Section 17.5  
<br/>\*\*Files in Scope:\*\*  
\- \`agent/nodes/delivery.py\`  
\- \`agent/graph.py\` (add delivery node on Approve/Edit path only)  
<br/>\*\*Acceptance criteria:\*\*  
\- \`delivery\` node added to graph on Approve/Edit path: \`episodic_memory_writer → delivery → run_metrics_writer\`  
\- Email subject: \`f"Signal Weekly Briefing - {datetime.now().strftime('%b %d, %Y')}"\`  
\- Retry policy: 3 retries, backoff \`\[30, 60, 120\]\` seconds  
\- On all retries exhausted: \`return {"delivery_status": "failed"}\` - do NOT raise, do NOT abort run  
\- Delivery node does not appear on Reject path - confirmed by reading graph edges  
\- Approved briefing arrives in \`delivery_email\` inbox (verify manually)  
\- Delivery failure (wrong App Password) → run completes, episodic memory row exists (DEC-004)  
<br/>\*\*Stop conditions - escalate to human immediately if:\*\*  
\- \`GMAIL_ADDRESS\` or \`GMAIL_APP_PASSWORD\` missing from \`.env\`  
\- Delivery node accidentally wired on Reject path - violates DEC-004  
\- \`smtplib.SMTP_SSL\` raises \`ConnectionRefusedError\` on first attempt before retries (port blocked)  
<br/>\---  
<br/>\### SIG-021B - Run Metrics Writer Phase 2 Upgrade  
\*\*Tier:\*\* 1 | \*\*Owner:\*\* Builder Agent | \*\*Phase:\*\* 2 | \*\*Status:\*\* TODO  
\*\*Depends on:\*\* SIG-P2-001, SIG-021  
\*\*Spec ref:\*\* BUILD_SPEC.md Section 15.2  
<br/>\*\*Files in Scope:\*\*  
\- \`agent/nodes/run_metrics_writer.py\`  
<br/>\*\*Acceptance criteria:\*\*  
\- \`print\` block replaced with INSERT into \`agent_run_metrics\`  
\- \`graph_version\` and \`source_health\` inserted as separate columns - not inside a JSON blob  
\- Also updates \`briefing_runs\` row with \`graph_version\`  
\- Supabase INSERT succeeds for both approve and reject run paths  
\- \`SELECT graph_version, source_health FROM agent_run_metrics ORDER BY created_at DESC LIMIT 1\` returns correct values  
<br/>\*\*Stop conditions - escalate to human immediately if:\*\*  
\- \`graph_version\` or \`source_health\` columns missing from \`agent_run_metrics\` table (SIG-P2-001 not complete)  
\- Supabase INSERT raises exception - do not swallow, escalate  
\- INSERT only occurs on one path - must occur on both approve and reject  
<br/>\---  
<br/>\### SIG-022 - Feedback Collector  
\*\*Tier:\*\* 1 | \*\*Owner:\*\* Builder Agent | \*\*Phase:\*\* 2 | \*\*Status:\*\* TODO  
\*\*Depends on:\*\* SIG-P2-001, SIG-020A  
\*\*Spec ref:\*\* BUILD_SPEC.md Section 18 (feedback endpoint), PRD Section 7  
<br/>\*\*Files in Scope:\*\*  
\- \`agent/nodes/feedback_collector.py\`  
\- \`agent/memory/feedback_store.py\`  
<br/>\*\*Acceptance criteria:\*\*  
\- \`agent/memory/feedback_store.py\` created with \`fetch_all_feedback_for_user(user_id: str) -> list\[dict\]\` function  
\- \`fetch_all_feedback_for_user\` queries \`user_feedback\` table filtered by \`user_id\`, returns all rows as list of dicts  
\- \`user_feedback\` table accepts inserts with: \`user_id\`, \`briefing_item_id\`, \`category\`, \`source_name\`, \`feedback\` (\`"useful"\` or \`"not_relevant"\`), \`reason\`  
\- Direct Supabase INSERT from Python test script works  
\- \`SIG-023\` imports \`fetch_all_feedback_for_user\` from \`agent.memory.feedback_store\` - no duplication  
<br/>\*\*Stop conditions - escalate to human immediately if:\*\*  
\- \`user_feedback\` table missing from Supabase (SIG-P2-001 not complete)  
\- \`fetch_all_feedback_for_user\` returns non-list type  
\- Supabase INSERT raises constraint violation - check schema column types  
<br/>\---  
<br/>\## Vertical Slice 5 - API, Frontend & Scheduler  
<br/>\*\*Phase:\*\* 2/3 | \*\*Owner:\*\* Builder Agent  
\*\*Goal:\*\* Full system accessible via browser. User triggers runs, reviews briefings, approves/rejects from UI. Weekly scheduler runs autonomously.  
<br/>\*\*Prerequisites before starting this slice:\*\* H-006 (Northflank) must be DONE.  
<br/>\> \*\*Before starting:\*\* Human must update \`CURRENT_PHASE.md\` to Slice 5 and confirm to Builder Agent.  
<br/>\*\*Slice exit criteria:\*\*  
\- \`uvicorn api.main:app\` starts without error  
\- All 15 API endpoints in BUILD_SPEC.md Section 18 return 200 on valid requests  
\- \`POST /agent/run\` triggers real graph invoke  
\- \`POST /briefings/{id}/approve\` resumes interrupted graph on Approve/Edit branch  
\- \`POST /briefings/{id}/reject\` resumes on Reject branch - no episodic memory written (DEC-004)  
\- Frontend renders in browser: all 8 screens per PRD Section 21  
\- APScheduler triggers weekly run autonomously - confirmed by waiting or mocking time  
\- After ≥5 feedback signals: procedural memory updates, next run reflects changes (DEC-007)  
<br/>\---  
<br/>\### SIG-P2-API - FastAPI Backend  
\*\*Tier:\*\* 1 | \*\*Owner:\*\* Builder Agent | \*\*Phase:\*\* 2 | \*\*Status:\*\* DONE  
\*\*Depends on:\*\* SIG-018, SIG-020A, SIG-021B, SIG-022  
\*\*Spec ref:\*\* BUILD_SPEC.md Section 18  
<br/>\*\*Files in Scope:\*\*  
\- \`api/main.py\`  
<br/>\*\*Acceptance criteria:\*\*  
\- All 15 endpoints in BUILD_SPEC.md Section 18 implemented  
\- JWT middleware validates \`Authorization: Bearer &lt;token&gt;\` via Supabase Auth on all protected routes  
\- \`POST /agent/run\` triggers \`graph.invoke\` in background thread, returns \`{"status": "started"}\`  
\- \`GET /agent/status\` returns \`"idle"\` | \`"running"\` | \`"pending_hitl"\` - never crashes  
\- \`POST /briefings/{id}/approve\` resumes graph with \`{"action": "approve"}\` on correct branch  
\- \`POST /briefings/{id}/reject\` resumes graph with \`{"action": "reject"}\` - episodic memory not written (DEC-004)  
\- \`POST /items/{id}/feedback\` inserts into \`user_feedback\` table  
\- \`GET /memory/episodic\` returns episodes from PostgresStore  
<br/>\*\*Stop conditions - escalate to human immediately if:\*\*  
\- \`fastapi\` or \`uvicorn\` not in \`requirements.txt\`  
\- Supabase JWT secret not configured - all protected routes would be open  
\- \`/briefings/{id}/reject\` endpoint accidentally triggers \`episodic_memory_writer\` - DEC-004 violation  
\- Background thread raises unhandled exception - graph invoke must never crash the API process  
<br/>\---  
<br/>\### SIG-P2-Frontend - HTML/JS Frontend  
\*\*Tier:\*\* 1 | \*\*Owner:\*\* Builder Agent | \*\*Phase:\*\* 2 | \*\*Status:\*\* DONE  
\*\*Depends on:\*\* SIG-P2-API  
\*\*Spec ref:\*\* PRD Section 21 (8 screens)  
<br/>\*\*Files in Scope:\*\*  
\- \`frontend/index.html\`  
<br/>\*\*Acceptance criteria:\*\*  
\- Single-file HTML/JS - no build step, no npm, no bundler  
\- Screen 1: Login - email + password, calls \`POST /auth/login\`  
\- Screen 2: Dashboard - list of past briefings, calls \`GET /briefings\`  
\- Screen 3: Agent status - idle/running/pending_hitl, polls \`GET /agent/status\` every 5s  
\- Screen 4: HITL Review - briefing draft + items list + Approve/Edit/Reject buttons (PRD Section 21 - most important screen)  
\- Screen 5: Briefing view - final approved briefing  
\- Screen 6: Feedback - thumbs up/down per item, calls \`POST /items/{id}/feedback\`  
\- Screen 7: Config - keywords, verticals, stage filter, calls \`GET/PUT /config\`  
\- Screen 8: Memory - shows semantic, episodic, procedural state, calls \`GET /memory/\*\`  
\- Approve button calls \`POST /briefings/{id}/approve\`, shows delivery confirmation  
\- Reject button calls \`POST /briefings/{id}/reject\`, confirms no email sent  
<br/>\*\*Stop conditions - escalate to human immediately if:\*\*  
\- API base URL in HTML points to localhost when deploying to Vercel (must point to Northflank URL)  
\- Approve/Reject buttons call wrong endpoints - DEC-004 compliance risk  
\- Screen 4 (HITL Review) cannot render if \`briefing_items\` is empty - handle gracefully  
<br/>\---  
<br/>\### SIG-023 - Procedural Memory Updater  
\*\*Tier:\*\* 1 | \*\*Owner:\*\* Builder Agent | \*\*Phase:\*\* 3 | \*\*Status:\*\* TODO  
\*\*Depends on:\*\* SIG-022, SIG-P2-API  
\*\*Spec ref:\*\* BUILD_SPEC.md Section 17.6  
<br/>\*\*Files in Scope:\*\*  
\- \`agent/nodes/procedural_memory_updater.py\`  
<br/>\*\*Critical - DEC-007 compliance:\*\* No LLM may rewrite procedural memory. Logic is deterministic aggregation only. Source weights floored at 0.3. Minimum 5 feedback signals before any update fires.  
<br/>\*\*Acceptance criteria:\*\*  
\- Imports \`fetch_all_feedback_for_user\` from \`agent.memory.feedback_store\` - no local redefinition  
\- Returns \`{}\` immediately if \`len(all_feedback) < 5\` - no update fires  
\- \`high_signal_categories\`: categories with >60% useful feedback ratio  
\- \`low_signal_categories\`: categories with >60% not_relevant feedback ratio  
\- \`source_weights\`: \`max(0.3, ratio)\` per source - no weight ever drops below 0.3 (DEC-007)  
\- \`store.put(namespace=("user", user_id, "procedural"), key="preferences", value=updated)\` called  
\- After ≥5 signals: \`store.get\` returns updated procedural memory with changed values  
\- Next \`run_graph()\` call: \`search_planner\` reads updated \`source_weights\` from state - confirmed in run output  
<br/>\*\*Stop conditions - escalate to human immediately if:\*\*  
\- Any LLM call detected in this node - hard DEC-007 violation, stop immediately  
\- Source weight drops below 0.3 - hard DEC-007 violation  
\- Update fires with fewer than 5 feedback signals - threshold logic broken  
\- \`fetch_all_feedback_for_user\` import fails (SIG-022 not complete)  
<br/>\---  
<br/>\### SIG-023-deploy - Northflank Deployment + APScheduler  
\*\*Tier:\*\* 1 | \*\*Owner:\*\* Builder Agent | \*\*Phase:\*\* 3 | \*\*Status:\*\* TODO  
\*\*Depends on:\*\* SIG-P2-Frontend, SIG-023, H-006  
\*\*Spec ref:\*\* BUILD_SPEC.md Section 20  
<br/>\*\*Files in Scope:\*\*  
\- \`api/main.py\` (add APScheduler startup event)  
<br/>\*\*Acceptance criteria:\*\*  
\- FastAPI deployed to Northflank as a Deployment service (not a Job - no cold-start)  
\- Runtime: \`uvicorn api.main:app --host 0.0.0.0 --port 8080\`  
\- All \`.env\` vars set as Northflank environment variables - \`.env\` file not uploaded  
\- Frontend deployed to Vercel, API base URL in \`frontend/index.html\` updated to Northflank URL  
\- APScheduler added to \`api/main.py\` [\`@app.on_event("startup")\`](mailto:`@app.on_event%28): triggers \`run_graph()\` on weekly cadence  
\- External cron at cron-job.org configured as fallback: calls \`POST /agent/run\` weekly  
\- End-to-end smoke test passes: trigger run from frontend → briefing appears → HITL screen appears → approve → email arrives in inbox  
<br/>\*\*Stop conditions - escalate to human immediately if:\*\*  
\- Northflank service type set to Job instead of Deployment (causes cold-start between runs)  
\- Any secret key appears in Northflank build logs - stop, rotate keys, escalate  
\- APScheduler fails to start on service boot - fallback cron must be active before marking DONE  
\- Smoke test email does not arrive within 5 minutes of approve action  
<br/>\---  
<br/>\## Dependency Graph - Critical Path  
<br/>

H-002, H-003 └─► SIG-001A └─► SIG-001B ──────────────────────────────────────────┐ ├─► SIG-001C │ └─► SIG-001D │ │ SIG-002 ─► SIG-003 ─► SIG-004 ┐ │ SIG-005 ├─► SIG-008 ─► SIG-009 │ SIG-006 │ └─► SIG-011 (T2) ◄── H-001 SIG-007 ─┘ └─► SIG-012 └─► SIG-013 └─► SIG-014 (T2) ◄── H-001 └─► SIG-017 (T2) ◄── H-001 └─► SIG-019 └─► SIG-021 │ All 15 nodes ────────────────────────────────────────────────────────────────┘ └─► SIG-010B ◄── GOLDEN_RUN_SPEC.md \[PHASE 1 DOD\]

H-004 ─► SIG-P2-001 ─► SIG-P2-002 ─► SIG-018 │ └─► SIG-019B ─► SIG-020A ◄── H-005 │ └─► SIG-002B │ └─► SIG-014B └─► SIG-021B └─► SIG-022 ─► \[fetch_all_feedback_for_user in feedback_store.py\] └─► SIG-P2-API ─► SIG-P2-Frontend └─► SIG-023 ◄── SIG-022 └─► SIG-023-deploy ◄── H-006

\---  
<br/>\## Task Count Summary  
<br/>| Slice | Tasks | Tier 1 (Builder Agent) | Tier 2 (Builder + Reviewer) | Tier 3 (Human) |  
|---|---|---|---|---|  
| Human Prereqs | 7 | 0 | 0 | 7 |  
| Slice 1 - Foundation | 4 | 4 | 0 | 0 |  
| Slice 2 - Research Pipeline | 7 | 7 | 0 | 0 |  
| Slice 3 - Processing + Phase 1 DOD | 9 | 6 | 3 | 0 |  
| Slice 4 - Phase 2 Infra + HITL | 9 | 9 | 0 | 0 |  
| Slice 5 - API + Frontend + Scheduler | 4 | 4 | 0 | 0 |  
| \*\*Total\*\* | \*\*40\*\* | \*\*30\*\* | \*\*3\*\* | \*\*7\*\* |  
<br/>\---  
<br/>\*Signal TASKS.md v3.0 - Execution driven by this file + CURRENT_PHASE.md. Implementation detail in BUILD_SPEC.md. Architecture in DECISIONS.md (highest priority - always wins conflicts). Evaluation thresholds in EVAL.md. Golden run criteria in GOLDEN_RUN_SPEC.md.\*