# Signal - PRD 

## Indian Startup & Funding Intelligence Agent

**Last updated:** June 2026 | **Status:** Ready for development | **Supersedes:** v1.1

## Changelog from v1.1

| **#** | **Change**                                                                                                                            | **Impact**                                                                       |
| ----- | ------------------------------------------------------------------------------------------------------------------------------------- | -------------------------------------------------------------------------------- |
| 1     | Freshness Validation Node added - between Reducer and Entity Extraction                                                               | Drops stale republished stories before any LLM processing                        |
| 2     | Scope Filter Node added - between Entity Extraction and Source Trust Scoring                                                          | Enforces domain boundaries deterministically; prevents noise reaching GPT-4o     |
| 3     | Structured error handling - error: Optional\[dict\] replaces Optional\[str\]; ErrorCode constants defined                             | Node failures are identifiable, recoverable flag enables graph routing decisions |
| 4     | Retry Policy Table added as documentation                                                                                             | Production retry behaviour defined before first timeout is hit                   |
| 5     | Spike 1 validated - Tavily requires include_domains; published_date unreliable; date extracted from body during entity extraction     | Tavily node implementation spec locked                                           |
| 6     | Spike 2 validated - Entity extraction Prompt v3 at 91% accuracy, 0 parse errors, 0 category violations                                | Prompt ready for production; no further iteration needed pre-build               |
| 7     | Spike 3 validated - 0.85 cosine threshold confirmed; company_name_normalized + announced_date pre-filter added before embedding calls | Dedup strategy fully decided; pre-filter reduces embedding API cost              |
| 8     | findings_dropped_freshness added as separate counter in SignalState and agent_run_metrics                                             | Distinguishes freshness drops from scope drops in monitoring                     |
| 9     | Pre-Development Spike Validation section added                                                                                        | Permanent record of validated decisions; eliminates re-litigating during build   |

## Pre-Development Spike Validation

All three pre-coding spikes are closed. Results are locked decisions - not open questions during the build phase.

### Spike 1 - Source Validation: PASS

**What was tested:** Whether the four Phase 1 data sources return usable, India-focused startup content.

**Results:**

- Tavily confirmed as primary data fetch layer. Returned results from inc42.com, entrackr.com, yourstory.com, and economictimes.indiatimes.com across 4/5 queries.
- **Critical finding: include_domains parameter is required.** Generic Tavily queries without it return LinkedIn, YouTube, and social media noise instead of Indian startup publications. Every Tavily query in the Search Planner must pass include_domains.
- **Critical finding: Tavily does not reliably return published_date.** Date extraction will happen from article body text during entity extraction. published_date in RawFinding is treated as unreliable metadata. EntityData.announced_date is the canonical date field - extracted by the LLM from article content.
- YC data sourced via public YC directory scraping, not Tavily.
- Google News RSS and native Inc42/YourStory RSS feeds confirmed working in production. Were blocked only in the testing sandbox environment.

**Locked decision:** Tavily Search Node must pass include_domains on every query. Date extraction responsibility belongs to Entity Extraction, not the research nodes.

### Spike 2 - Entity Extraction: PASS

**What was tested:** Whether a single GPT-4o mini prompt can reliably extract structured entity fields from real Indian startup articles.

**Results:**

- Two prompt iterations run against 25 real Indian startup articles.
- Prompt v2 scored 81.5% overall. Four fields below threshold: amount precision, stage nulling for non-funding categories, date strictness.
- Prompt v3 applied three targeted fixes. Scored **91% overall accuracy**, 0 parse errors, 0 category violations. All eight fields cleared the 80% threshold.

**Locked decision:** Entity Extraction node uses Prompt v3. No further prompt iteration needed before build. The exact prompt text is retained in the project's /prompts/entity_extraction_v3.txt file created during the spike.

### Spike 3 - Dedup Threshold: PASS

**What was tested:** Whether cosine similarity on text-embedding-3-small embeddings reliably separates true duplicates from distinct-but-related articles.

**Results:**

- Tested across 3 real story sets with 3-4 versions each from different Indian publications.
- Clean separation confirmed between true duplicates and unrelated articles at the 0.85 threshold.
- **Key finding: URL matching alone is insufficient for cross-publication dedup.** The same story appears on Inc42, YourStory, and Economic Times with three different URLs. Embedding similarity catches these; URL matching misses them.
- **Pre-filter validated:** Exact match on company_name_normalized + announced_date eliminates the majority of true duplicates before any embedding call. This cuts embedding API cost significantly.
- Model: text-embedding-3-small on title + 300-character snippet.

**Locked decision:** Dedup runs in three stages - (1) pre-filter on company_name_normalized + announced_date, (2) URL exact match, (3) embedding cosine similarity at 0.85 threshold. All three run in Phase 1 for URL and pre-filter; embedding layer added in Phase 2.

## 1\. Overview

Signal is an autonomous AI agent that monitors the Indian startup and funding ecosystem, removes already-reported noise, and delivers a personalized weekly intelligence briefing. It runs on a schedule, accumulates memory across sessions, and improves its search strategy based on user feedback over time.

It is an **agent-as-system**, not a chatbot.

The most important requirement of this system is that **data coming in is relevant and fresh**. Architecture decisions, source selection, dedup strategy, and metrics all serve this single requirement.

## 2\. Problem

Founders, AI engineers, and operators in the Indian startup ecosystem have no tool that:

- Monitors the market continuously and automatically
- Deduplicates against everything it has already reported
- Learns what the user cares about and filters accordingly

Newsletters are generic. News sites require manual reading. Nothing learns from feedback.

## 3\. Target User (Phases 1-3)

Single user. An AI engineer or founder who wants to stay current on the Indian startup ecosystem without spending time manually reading news. Cares about: funding signals, emerging verticals, hiring trends, new entrants, and ecosystem patterns.

Multi-tenancy is a Phase 4 concern. Phases 1-3 are built and optimized for one user.

## 4\. Domain Scope

**In scope:**

- Indian-headquartered or Indian-founded startups
- Funding range: \$500K-\$50M (Seed to Series B)
- Announcements from the last 30 days
- Verticals: AI, fintech, healthtech, B2B SaaS, climate, edtech

**Weekly briefing covers:**

- New funding rounds
- YC and accelerator batch acceptances
- Founder moves (new companies, exits, joins)
- Hiring signals (fast-growing headcount)
- Startup failures, pivots, shutdowns
- Emerging vertical trends
- Weekly narrative synthesis

**Out of scope:**

- Enterprise IT companies (Infosys, Wipro, TCS)
- Funding rounds above \$50M
- Global startups with no Indian connection
- Real-time/breaking news (weekly cadence only)

## 5\. Category Taxonomy

Locked constant. Entity extraction prompt must enforce this list. LLM must not invent new categories.

ALLOWED_CATEGORIES = \[  
"funding", # Funding round announced  
"hiring", # Fast headcount growth or job signal  
"founder_move", # Founder starts company, exits, or joins  
"accelerator", # YC, Surge, or other batch acceptance  
"shutdown", # Company closed or wound down  
"pivot", # Company changed business model or direction  
"ecosystem_trend" # Pattern across multiple companies/verticals  
\]

The entity extraction prompt must include: _"Classify this finding using exactly one category from this list: funding, hiring, founder_move, accelerator, shutdown, pivot, ecosystem_trend. Do not use any other value."_

## 6\. Agent Workflow

┌─────────────────────────────────────────────────────────┐  
│ SIGNAL AGENT GRAPH │  
└─────────────────────────────────────────────────────────┘  
<br/>Trigger (APScheduler or manual /agent/run)  
│  
▼  
┌─────────────┐  
│ Config │ Reads user*config + procedural memory  
│ Loader │ from LangGraph Store  
└──────┬──────┘  
│  
▼  
┌─────────────┐  
│ Search │ Phase 1: deterministic query generation  
│ Planner │ Phase 2+: reads procedural memory JSON,  
└──────┬──────┘ adjusts query terms and source weights  
│ All Tavily queries include include_domains  
│  
│ Send API - fires all nodes in parallel  
├──────────────────────────────────────────┐  
│ │ │ │  
▼ ▼ ▼ ▼  
┌────────────┐ ┌────────────┐ ┌──────────┐ ┌──────────────┐  
│ Tavily │ │ YC API │ │ HN │ │ Google News │  
│ Search │ │ Node │ │ Algolia │ │ RSS Node │  
│ Node │ │ (directory │ │ Node │ │ │  
│ (requires │ │ scraping) │ │ │ │ │  
│include*│ │ │ │ │ │ │  
│ domains) │ │ │ │ │ │ │  
└────────────┘ └────────────┘ └──────────┘ └──────────────┘  
│ │ │ │  
└──────────────┴──────────────┴────────────┘  
│  
▼  
┌──────────────────┐  
│ Reducer │ Merges all parallel  
│ │ outputs - operator.add  
└────────┬─────────┘ no overwrite  
│  
▼  
┌──────────────────┐ ◄── NEW v1.2  
│ Freshness │ Deterministic. No LLM.  
│ Validation │ Drops findings where  
│ Node │ announced_date > 30 days.  
└────────┬─────────┘ Flags undated findings  
│ with confidence penalty.  
▼  
┌──────────────────┐  
│ Entity │ Extracts structured entities  
│ Extraction │ + normalizes names.  
│ │ Enforces ALLOWED_CATEGORIES.  
└────────┬─────────┘ Extracts announced_date  
│ from article body text.  
│ Uses Prompt v3 (91% accuracy).  
▼  
┌──────────────────┐ ◄── NEW v1.2  
│ Scope Filter │ Deterministic. No LLM.  
│ Node │ Enforces: India only,  
│ │ \$500K-\$50M, Seed-Series B.  
└────────┬─────────┘ Drop only if explicitly  
│ out of scope, not if null.  
▼  
┌──────────────────┐  
│ Source Trust │ Scores each surviving  
│ Scoring │ finding by SOURCE_TRUST.  
└────────┬─────────┘ (deterministic)  
│  
▼  
┌──────────────────┐  
│ Hybrid Dedup │ Pre-filter: company_name_normalized  
│ │ + announced_date exact match.  
└────────┬─────────┘ Phase 1: + URL + title match.  
│ Phase 2+: + embedding at 0.85.  
▼  
┌──────────────────┐  
│ Synthesis │ GPT-4o writes structured  
│ Node │ briefing from new findings  
└────────┬─────────┘  
│  
▼  
┌──────────────────┐  
│ HITL Interrupt │ Graph pauses, user  
│ interrupt() │ reviews draft in UI  
└────────┬─────────┘  
│  
┌──────────┴──────────┐  
│ │  
\[Approve/Edit\] \[Reject\]  
│ │  
▼ ▼  
┌──────────────────┐ ┌─────────────────┐  
│ Episodic Memory │ │ Discard + Log │  
│ Writer │ └─────────────────┘  
│ (BEFORE delivery│  
│ - run persisted│  
│ even if Gmail │  
│ fails) │  
└──────┬───────────┘  
│  
▼  
┌──────────────┐  
│ Delivery │ Gmail via smtplib (P2)  
│ Node │ Gmail OAuth (P3)  
└──────┬───────┘  
│  
▼  
┌──────────────┐  
│ Run Metrics │ Writes agent_run_metrics  
│ Writer │ row for this run  
└──────┬───────┘  
│  
▼  
┌──────────────┐  
│ Feedback │ User rates items in UI  
│ Collector │ useful / not_relevant  
└──────┬───────┘ + optional reason  
│  
▼  
┌──────────────┐  
│ Procedural │ Deterministic aggregation  
│ Memory │ of feedback patterns →  
│ Updater │ writes structured JSON  
└──────┬───────┘ preference profile  
│ (no LLM, no prompt rewriting)  
▼  
\[Idle until next scheduled run\]

**Critical order note:** Episodic Memory Writer runs before Delivery. If Gmail fails, the run is already persisted in episodic memory. Dedup integrity is maintained regardless of delivery failures.

## 7\. Node Definitions

| **Node**                                   | **Purpose**                                                                                                                                                                                                                                                | **Inputs**                                 | **Outputs**                                                 | **LangGraph Concept**             | **Model**                             |
| ------------------------------------------ | ---------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- | ------------------------------------------ | ----------------------------------------------------------- | --------------------------------- | ------------------------------------- |
| Config Loader                              | Reads user config and all memory namespaces                                                                                                                                                                                                                | thread_id, user_id                         | config, semantic_memory, procedural_memory                  | Store read                        | None                                  |
| Search Planner                             | Generates query list per research node; all Tavily queries include include_domains                                                                                                                                                                         | config, procedural_memory                  | query_plan (dict of node → query list)                      | Conditional logic                 | Deterministic (P1), GPT-4o mini (P2+) |
| Tavily Search                              | News and funding research via web search. Requires include_domains on every query.                                                                                                                                                                         | query_plan\["tavily"\]                     | raw_findings\[\]                                            | Send API parallel node            | None (API call)                       |
| YC API Node                                | YC company metadata via public directory scraping                                                                                                                                                                                                          | query_plan\["yc"\]                         | raw_findings\[\]                                            | Send API parallel node            | None (scraping)                       |
| HN Algolia Node                            | Show HN posts, founder launches, who is hiring                                                                                                                                                                                                             | query_plan\["hn"\]                         | raw_findings\[\]                                            | Send API parallel node            | None (API call)                       |
| Google News RSS Node                       | RSS feed parsing for Indian startup news                                                                                                                                                                                                                   | query_plan\["rss"\]                        | raw_findings\[\]                                            | Send API parallel node            | None (feedparser)                     |
| Reducer                                    | Merges all parallel node outputs into shared state                                                                                                                                                                                                         | raw_findings\[\] from all nodes            | merged raw_findings\[\]                                     | Reducer function - operator.add   | None                                  |
| **Freshness Validation Node** _(new v1.2)_ | Drops findings older than 30 days. Flags undated findings with confidence penalty. Deterministic, no LLM. Runs on merged raw_findings before any LLM processing.                                                                                           | raw_findings\[\]                           | filtered raw_findings\[\], findings_dropped_freshness count | Standard node - pure Python       | None                                  |
| Entity Extraction                          | Extracts structured entities, normalizes names, enforces category taxonomy. Extracts announced_date from article body text (not from metadata). Uses Prompt v3 (91% accuracy, validated).                                                                  | filtered raw_findings\[\]                  | findings_with_entities\[\]                                  | LLM structured output             | GPT-4o mini                           |
| **Scope Filter Node** _(new v1.2)_         | Enforces three domain boundaries: India only, \$500K-\$50M, Seed-Series B. Rule: drop only if explicitly out of scope, never if field is null. Deterministic, no LLM. Runs before source trust scoring - no point scoring something about to be discarded. | findings_with_entities\[\]                 | scope_filtered_findings\[\], findings_dropped_scope count   | Standard node - pure Python       | None                                  |
| Source Trust Scoring                       | Assigns confidence score to each finding that survived scope filtering                                                                                                                                                                                     | scope_filtered_findings\[\]                | scored_findings\[\]                                         | Deterministic transform           | None                                  |
| Hybrid Dedup                               | Pre-filter: exact match on company_name_normalized + announced_date. Phase 1: + URL match + normalized title match. Phase 2+: + embedding cosine similarity at 0.85 threshold.                                                                             | scored_findings\[\], episodic_memory       | new_findings\[\]                                            | Store read + embedding comparison | text-embedding-3-small (P2+)          |
| Synthesis                                  | Writes structured briefing from new findings                                                                                                                                                                                                               | new_findings\[\], semantic_memory          | briefing_draft                                              | LLM generation                    | GPT-4o                                |
| HITL Interrupt                             | Pauses graph for user review                                                                                                                                                                                                                               | briefing_draft                             | hitl_decision                                               | interrupt()                       | None                                  |
| Episodic Memory Writer                     | Runs before Delivery. Persists run to episodic memory                                                                                                                                                                                                      | new_findings\[\], briefing_final           | -                                                           | Store write                       | None                                  |
| Delivery                                   | Sends approved briefing via Gmail                                                                                                                                                                                                                          | briefing_final, user_email                 | delivery_status                                             | Side effect node                  | None (smtplib)                        |
| Run Metrics Writer                         | Records run performance stats including freshness and scope drop counts                                                                                                                                                                                    | run metadata, findings counts, token usage | -                                                           | Store write                       | None                                  |
| Feedback Collector                         | Records per-item user feedback                                                                                                                                                                                                                             | item_id, feedback, feedback_reason         | -                                                           | Store write                       | None                                  |
| Procedural Memory Updater                  | Deterministic only. Aggregates feedback patterns, writes structured JSON preference profile                                                                                                                                                                | all feedback records for user              | updated_procedural_memory                                   | Store write                       | None - no LLM                         |

## 8\. SignalState TypedDict

Define this before writing any node code. Every node's inputs and outputs derive from this schema.

from typing import TypedDict, Annotated, Optional  
import operator  
<br/><br/>class RawFinding(TypedDict):  
title: str  
summary: str  
source_url: str  
source_name: str  
published_date: Optional\[str\] # Unreliable from Tavily (Spike 1).  
\# Canonical date = EntityData.announced_date,  
\# extracted from article body during entity extraction.  
<br/><br/>class EntityData(TypedDict):  
company_name: Optional\[str\]  
company_name_normalized: Optional\[str\] # lowercased, punctuation removed  
founder_name: Optional\[str\]  
investor_names: Optional\[list\[str\]\]  
investor_names_normalized: Optional\[list\[str\]\]  
funding_amount_usd: Optional\[int\]  
funding_stage: Optional\[str\]  
sector: Optional\[str\]  
location: Optional\[str\]  
announced_date: Optional\[str\] # Canonical date. Extracted from body text.  
<br/><br/>class ScoredFinding(RawFinding):  
entities: EntityData  
category: str # must be one of ALLOWED_CATEGORIES  
confidence_score: float # 0.0-1.0 from SOURCE_TRUST  
freshness_penalized: bool # True if no parseable date found  
is_duplicate: bool  
duplicate_reason: Optional\[str\] # "pre_filter" | "url_match" | "title_match" | "embedding_similarity"  
<br/><br/>class BriefingItem(TypedDict):  
id: str  
title: str  
summary: str  
source_url: str  
source_name: str  
category: str  
confidence_score: float  
entities: EntityData  
<br/><br/>class SignalState(TypedDict):  
\# Run metadata  
run_id: str  
user_id: str  
thread_id: str  
run_type: str # "scheduled" | "manual"  
<br/>\# Config (loaded at start)  
user_config: dict  
semantic_memory: dict  
procedural_memory: dict  
query_plan: dict # node_name → list\[str\]  
<br/>\# Research - Annotated with operator.add so parallel nodes append, not overwrite  
raw_findings: Annotated\[list\[RawFinding\], operator.add\]  
<br/>\# Processing  
scored_findings: list\[ScoredFinding\]  
new_findings: list\[ScoredFinding\] # post-dedup  
<br/>\# Synthesis  
briefing_draft: str  
briefing_items: list\[BriefingItem\]  
briefing_final: str  
<br/>\# HITL  
hitl_decision: Optional\[str\] # "approve" | "edit" | "reject"  
hitl_edits: Optional\[dict\]  
<br/>\# Delivery  
delivery_status: Optional\[str\]  
<br/>\# Metrics (written after delivery)  
sources_queried: list\[str\]  
findings_retrieved: int  
findings_dropped_freshness: int # dropped by Freshness Validation Node  
findings_dropped_dedup: int # removed as duplicates  
findings_dropped_scope: int # dropped by Scope Filter Node  
tokens_used: int  
estimated_cost_usd: float  
run_duration_seconds: float  
<br/>\# Run snapshot for evaluation replay  
run_config_snapshot: dict  
<br/>\# Structured error - None when healthy, dict when a node fails  
error: Optional\[dict\] # {"code": "...", "node": "...", "message": "...", "recoverable": True}

**Key rule:** raw_findings uses Annotated\[list, operator.add\]. This is what makes Send API parallel nodes append results without overwriting each other. All other fields are standard assignment.

## 9\. Error Handling Constants

Define ErrorCode alongside SignalState. The recoverable boolean in the error dict tells the graph whether to retry, skip and continue, or abort the run.

class ErrorCode:  
ENTITY_EXTRACTION_FAILED = "ENTITY_EXTRACTION_FAILED"  
TAVILY_TIMEOUT = "TAVILY_TIMEOUT"  
YC_API_UNAVAILABLE = "YC_API_UNAVAILABLE"  
DEDUP_EMBEDDING_FAILED = "DEDUP_EMBEDDING_FAILED"  
SYNTHESIS_FAILED = "SYNTHESIS_FAILED"  
DELIVERY_FAILED = "DELIVERY_FAILED"  
GMAIL_AUTH_FAILED = "GMAIL_AUTH_FAILED"  
<br/>\# Error dict shape:  
\# {  
\# "code": ErrorCode.TAVILY_TIMEOUT,  
\# "node": "tavily_search",  
\# "message": "Request timed out after 2 retries",  
\# "recoverable": True  
\# }

**Recoverable vs non-recoverable:**

- **Recoverable:** Tavily timeout (retry), HN Algolia timeout (retry), synthesis failure (retry with shorter prompt), entity extraction item failure (skip item, log to failed_findings, continue run)
- **Non-recoverable:** Gmail auth failure (needs human intervention - abort and flag), synthesis failure after all retries exhausted (no briefing possible - abort run, set status = failed)

## 10\. Retry Policy

Documentation only - not implementation. Reference this table when writing error handling in each node. Do not implement retry logic until it is needed; define the policy now so it is not an afterthought on the first Tavily timeout.

| **Node**                     | **Retries** | **Backoff**    | **On Final Failure**                                          |
| ---------------------------- | ----------- | -------------- | ------------------------------------------------------------- |
| Tavily Search                | 2           | 5s, 15s        | Log + continue with other sources                             |
| YC API                       | 2           | 5s, 15s        | Log + continue, flag in metrics                               |
| HN Algolia                   | 2           | 5s, 15s        | Log + continue                                                |
| RSS Feeds                    | 1           | 5s             | Log + continue, not critical                                  |
| Entity Extraction (per item) | 1           | 3s             | Log item to failed_findings, skip item, continue run          |
| Synthesis                    | 1           | 10s            | Abort run, set status = failed                                |
| Gmail Delivery               | 3           | 30s, 60s, 120s | Log delivery_failed; run already persisted in episodic memory |

**The "on final failure" column is as important as the retry count.** Most nodes should fail gracefully and let the run continue with reduced data. Only Synthesis failing exhausting all retries should abort the run entirely - because without synthesis there is no briefing. Delivery failing must never abort the run, because episodic memory was already written before Delivery executes.

## 11\. Memory Architecture

### Short-term - PostgresSaver checkpointer

- Stores current graph state within a single run
- Backed by Supabase PostgreSQL (tables auto-created by PostgresSaver)
- Scoped per thread_id - one thread per run
- Phase 1: MemorySaver (in-memory), Phase 2+: PostgresSaver

### Long-term - LangGraph Store

**Semantic memory**

Namespace: ("user", user_id, "semantic")  
Stores: known startup names and stages, investor profiles,  
verticals being tracked, high-signal source history  
Purpose: background knowledge before research starts

**Episodic memory**

Namespace: ("user", user_id, "episodic")  
Stores: every completed run - timestamp, item titles,  
source URLs, normalized company names, announced_date,  
run summary  
Purpose: dedup node compares every new finding against  
all past episodes. Written BEFORE delivery.

**Procedural memory**

Namespace: ("user", user_id, "procedural")  
<br/>Schema (structured JSON - no prompt rewriting, ever):  
{  
"high_signal_categories": \["funding", "accelerator"\],  
"low_signal_categories": \["hiring"\],  
"trusted_sources": \["inc42", "yc"\],  
"preferred_stage": \["seed", "series_a"\],  
"query_boost_terms": \["Bengaluru", "B2B SaaS", "GPT"\],  
"query_suppress_terms": \["Infosys", "Wipro", "IT services"\],  
"source_weights": {  
"tavily": 1.0,  
"yc": 1.0,  
"hn": 0.7,  
"google_news": 0.65  
},  
"min_confidence_threshold": 0.70  
}  
<br/>Update rule: deterministic aggregation only. Count feedback  
patterns across all items. No LLM involved. Minimum 5  
feedback signals before any update runs. Source weights  
floored at 0.3 - no source ever fully suppressed.

## 12\. Source Trust Matrix

SOURCE_TRUST = {  
"yc": 1.0,  
"techcrunch": 0.95,  
"inc42": 0.90,  
"yourstory": 0.90,  
"economictimes": 0.85,  
"mint": 0.85,  
"hn": 0.70,  
"google_news": 0.65,  
"rss_other": 0.60  
}

Each ScoredFinding carries its confidence_score. The synthesis prompt weights high-confidence findings more heavily. The UI displays confidence as a subtle signal strength indicator on each briefing item. Freshness-penalized findings (no parseable date) receive a 0.1 confidence penalty applied on top of their source trust score.

## 13\. Data Sources

### Phase 1

| **Source**        | **Auth** | **Cost**                  | **Endpoint**                                                 | **Notes**                                                                                                          |
| ----------------- | -------- | ------------------------- | ------------------------------------------------------------ | ------------------------------------------------------------------------------------------------------------------ |
| Tavily Search API | API key  | Free: 1,000 credits/month | REST, JSON                                                   | include_domains required on every query (Spike 1). Without it, returns LinkedIn/social noise. Primary news source. |
| YC Companies API  | None     | \$0                       | Public YC directory scraping                                 | Not Tavily. Direct scraping of public YC directory. Confirmed stable (Spike 1). Have Tavily fallback ready.        |
| HN Algolia API    | None     | \$0                       | hn.algolia.com/api/v1/search?query=...                       | Fully documented, officially maintained. Reliable.                                                                 |
| Google News RSS   | None     | \$0                       | news.google.com/rss/search?q=indian+startup+funding&hl=en-IN | feedparser. No API key. Confirmed working in production (Spike 1).                                                 |

### Phase 2 (added)

| **Source**    | **Auth** | **Cost** | **Endpoint**       | **Notes**                                                                      |
| ------------- | -------- | -------- | ------------------ | ------------------------------------------------------------------------------ |
| Inc42 RSS     | None     | \$0      | inc42.com/feed/    | Standard WordPress RSS. feedparser. Confirmed working in production (Spike 1). |
| YourStory RSS | None     | \$0      | yourstory.com/feed | Standard RSS. feedparser. Confirmed working in production (Spike 1).           |

### Phase 3 (added)

| **Source**     | **Auth** | **Cost** | **Endpoint**                                   | **Notes**                                        |
| -------------- | -------- | -------- | ---------------------------------------------- | ------------------------------------------------ |
| Greenhouse ATS | None     | \$0      | boards-api.greenhouse.io/v1/boards/{slug}/jobs | Requires company slug list from companies table. |
| Lever ATS      | None     | \$0      | api.lever.co/v0/postings/{slug}                | Same requirement as Greenhouse.                  |

### Dropped entirely

- Twitter/X - \$100/month minimum
- LinkedIn scraping - ToS violation
- Work at a Startup - undocumented internal endpoint
- Direct Crunchbase API - \$299/month

## 14\. Freshness Validation Node - Specification

**Type:** Deterministic Python node. No LLM.

**Position:** After Reducer, before Entity Extraction.

**Logic:**

\# Runs on merged raw_findings\[\] after operator.add reduction  
<br/>FRESHNESS_WINDOW_DAYS = 30  
<br/>for finding in raw_findings:  
published = parse_date(finding.published_date) # best-effort parse  
<br/>if published is None:  
\# No parseable date - flag with penalty but do not drop.  
\# Some legitimate sources omit structured dates.  
finding.freshness_penalized = True  
continue  
<br/>days_old = (today - published).days  
<br/>if days_old > FRESHNESS_WINDOW_DAYS:  
\# Drop. Log to failed_findings (Phase 3) with failure_reason: "freshness_filter"  
drop(finding)  
increment(findings_dropped_freshness)

**Drop rule:** Drop only if published_date is parseable AND older than 30 days. Ambiguous (no date) is not a drop - it is a penalty.

**Why this exists:** Indian startup news republishing pattern - a funding round gets covered by Inc42 and YourStory, then 3 months later an aggregator republishes with a fresh URL and yesterday's date. Tavily surfaces it. Without this node, entity extraction treats it as new, it passes dedup (new URL, slightly different title), and it appears in the briefing as a "new" round that happened six months ago. This node catches it before any LLM cost is incurred.

**Logs to:** failed_findings table (Phase 3) with failure_reason: "freshness_filter". Increments findings_dropped_freshness in SignalState and agent_run_metrics.

## 15\. Scope Filter Node - Specification

**Type:** Deterministic Python node. No LLM.

**Position:** After Entity Extraction, before Source Trust Scoring.

**Why this position:** Source Trust Scoring only runs on findings that survive scope filtering - no point scoring something about to be discarded. Synthesis (GPT-4o) only receives findings that have cleared all filters.

**Logic:**

\# Three domain boundaries - check in order  
<br/>for finding in findings_with_entities:  
e = finding.entities  
<br/>\# 1. Geography - India only  
if e.location is not None and not is_india_connected(e.location):  
drop(finding, reason="scope_filter: non_indian_location")  
continue  
\# If location is None → keep. Ambiguous is not a rejection.  
<br/>\# 2. Funding amount - \$500K to \$50M  
if e.funding_amount_usd is not None:  
if e.funding_amount_usd &lt; 500_000 or e.funding_amount_usd &gt; 50_000_000:  
drop(finding, reason="scope_filter: funding_out_of_range")  
continue  
\# If funding_amount_usd is None → keep. Non-funding categories won't have this field.  
<br/>\# 3. Stage - Seed to Series B  
OUT_OF_SCOPE_STAGES = {"series_c", "series_d", "series_e", "ipo", "private_equity"}  
if e.funding_stage is not None and e.funding_stage.lower() in OUT_OF_SCOPE_STAGES:  
drop(finding, reason="scope_filter: stage_out_of_range")  
continue  
\# If funding_stage is None → keep.

**Core rule:** Drop only if explicitly out of scope. Never drop because a field is missing. A finding with location: null is ambiguous - keep it. A finding with location: "San Francisco" and no India connection is a clear rejection.

**Logs to:** failed_findings table (Phase 3) with failure_reason: "scope_filter". Increments findings_dropped_scope in SignalState and agent_run_metrics.

## 16\. Dedup Strategy

Validated in Spike 3. Running in three stages:

Phase 1:  
0\. Pre-filter: exact match on company_name_normalized + announced_date → duplicate if match  
(Eliminates majority of cross-publication duplicates before any other check)  
1\. URL exact match vs episodic memory → duplicate if match  
2\. Normalized title string match → duplicate if match  
<br/>Phase 2+:  
3\. Embedding cosine similarity (pgvector) → duplicate if score > 0.85  
Model: text-embedding-3-small  
Input: title + first 300 characters of summary  
Near-duplicate zone: 0.75-0.85  
→ include with note "related to previous coverage"  
Hard duplicate: > 0.85 → exclude from synthesis

**Why URL matching alone is insufficient:** The same story commonly appears on Inc42, YourStory, and Economic Times with three different URLs. The pre-filter on company_name_normalized + announced_date catches most of these at zero cost. Embedding similarity catches the remainder. (Spike 3 validated this.)

Flag duplicate: set is_duplicate=True, record duplicate_reason.

Phase 1 dedup: pre-filter + URL match + normalized title only. Phase 2 adds embedding similarity. pgvector must be enabled on Supabase project before Phase 2 starts.

## 17\. Name Normalization

Applied during Entity Extraction. Store both raw and normalized forms.

import re  
<br/>def normalize_name(name: str) -> str:  
if not name:  
return ""  
name = name.lower()  
name = re.sub(r'\[^a-z0-9\\s\]', '', name) # remove punctuation  
name = re.sub(r'\\s+', ' ', name).strip() # collapse whitespace  
return name  
<br/>\# Examples:  
\# "Razor-Pay" → "razorpay" (after manual alias mapping)  
\# "Razor Pay" → "razor pay"  
\# "CRED." → "cred"

For known aliases (Razorpay / Razor Pay / Razor-Pay), maintain a small alias dictionary in config. This is not automated - add entries manually as they appear.

company_name_normalized and investor_names_normalized in EntityData store the normalized versions. Dedup and analytics use normalized fields; display uses raw fields.

## 18\. Database Schema

### Supabase Auth

Handled automatically by Supabase. user_id (UUID) from auth.users is foreign key for all custom tables. RLS enabled on all tables - every query auto-scoped to the authenticated user.

### user_configs

id uuid primary key default gen_random_uuid()  
user_id uuid references auth.users not null  
keywords text\[\]  
verticals text\[\]  
stage_filter text\[\]  
schedule_freq text -- 'daily' | 'weekly'  
delivery_email text  
created_at timestamptz default now()  
updated_at timestamptz default now()

### briefing_runs

id uuid primary key default gen_random_uuid()  
user_id uuid references auth.users not null  
run_at timestamptz default now()  
status text -- running | pending_hitl | completed | failed | rejected  
raw_findings jsonb  
final_briefing text  
was_approved boolean default false  
approved_at timestamptz  
thread_id text -- LangGraph thread_id for time travel  
run_config jsonb -- snapshot of config + procedural memory at run time

### briefing_items

id uuid primary key default gen_random_uuid()  
briefing_run_id uuid references briefing_runs not null  
user_id uuid references auth.users not null  
title text  
summary text  
source_url text  
source_name text  
category text -- must be from ALLOWED_CATEGORIES  
confidence_score float  
entities jsonb -- EntityData shape  
embedding vector(1536) -- Phase 2+, requires pgvector  
feedback text -- useful | not_relevant | null  
feedback_reason text -- already_knew | wrong_stage | wrong_sector | too_generic | great_find  
feedback_at timestamptz

### companies (data shape defined Phase 1, table created Phase 2)

Phase 1: entity extraction outputs company-shaped data. Stored in briefing_items.entities JSONB column. Phase 2: migrate to this dedicated table.

id uuid primary key default gen_random_uuid()  
name_raw text not null  
name_normalized text not null  
sector text  
stage text  
location text  
founded_year int  
yc_batch text  
greenhouse_slug text -- for Phase 3 ATS queries  
lever_slug text -- for Phase 3 ATS queries  
first_seen_at timestamptz default now()  
updated_at timestamptz default now()

### funding_rounds (Phase 2)

id uuid primary key default gen_random_uuid()  
company_id uuid references companies  
amount_usd bigint  
stage text  
announced_at date  
source_url text  
investor_names text\[\]  
investor_names_normalized text\[\]  
briefing_item_id uuid references briefing_items  
created_at timestamptz default now()

### agent_run_metrics (Phase 1 - critical for data quality monitoring)

id uuid primary key default gen_random_uuid()  
briefing_run_id uuid references briefing_runs not null  
user_id uuid references auth.users not null  
run_at timestamptz default now()  
sources_queried text\[\]  
findings_retrieved int -- total before any filtering  
findings_dropped_freshness int -- dropped by Freshness Validation Node  
findings_dropped_scope int -- dropped by Scope Filter Node  
findings_dropped_dedup int -- removed as duplicates  
findings_in_briefing int -- final count delivered to user  
tokens_used int  
estimated_cost_usd float  
run_duration_seconds float  
tavily_result_count int  
yc_result_count int  
hn_result_count int  
rss_result_count int

This table is the primary instrument for monitoring whether data is fresh and relevant. If findings_retrieved drops consistently, sources are degrading. If findings_dropped_dedup spikes, the agent is looping. If findings_dropped_freshness spikes, sources are publishing stale aggregator content. If one source's count drops to zero, the endpoint changed.

### evaluation_datasets (Phase 3)

id uuid primary key default gen_random_uuid()  
user_id uuid references auth.users not null  
briefing_run_id uuid references briefing_runs  
input_snapshot jsonb  
expected_output text  
actual_output text  
relevance_score float  
dedup_accurate boolean  
notes text  
created_at timestamptz default now()

### failed_findings (Phase 3 - debugging, not MVP)

id uuid primary key default gen_random_uuid()  
briefing_run_id uuid references briefing_runs not null  
source_url text  
source_name text  
raw_content text  
failure_reason text -- "freshness_filter" | "entity_extraction_failed" | "scope_filter" | "dedup_removed"  
created_at timestamptz default now()

### agent_memory

id uuid primary key default gen_random_uuid()  
user_id uuid references auth.users not null  
memory_type text -- semantic | episodic | procedural  
namespace_key text  
content jsonb  
created_at timestamptz default now()  
updated_at timestamptz default now()

PostgresSaver creates its own checkpointer tables automatically - do not define those manually.

## 19\. FastAPI Endpoints

Auth (Supabase handles directly):  
POST /auth/signup  
POST /auth/login  
<br/>Agent control (JWT required):  
POST /agent/run Manually trigger a full run  
GET /agent/status Returns: idle | running | pending_hitl  
<br/>Briefings (JWT required):  
GET /briefings List of past runs for user  
GET /briefings/{id} Single briefing with all items  
POST /briefings/{id}/approve Resume graph from HITL interrupt  
POST /briefings/{id}/edit Update content then resume  
POST /briefings/{id}/reject Discard run  
<br/>Feedback (JWT required):  
POST /items/{id}/feedback  
Body: { "feedback": "useful"|"not_relevant", "reason": "already_knew|wrong_stage|wrong_sector|too_generic|great_find" }  
<br/>Config (JWT required):  
GET /config  
PUT /config  
<br/>Metrics (JWT required):  
GET /metrics/runs Returns agent_run_metrics for last N runs  
GET /metrics/sources Returns per-source finding counts over time  
<br/>Memory (JWT required, read-only):  
GET /memory/semantic  
GET /memory/episodic  
GET /memory/procedural

## 20\. Authentication

- Provider: Supabase Auth, email/password
- JWT returned on login, stored in frontend memory (not localStorage)
- Sent as Authorization: Bearer &lt;token&gt; on all API calls
- FastAPI middleware validates JWT using Supabase JWT secret
- RLS on all custom tables - queries auto-scoped to user_id
- user_id is the LangGraph Store namespace key → Phase 4 multi-tenancy is a config change, not a rebuild

## 21\. UI Screens

**Screen 1 - Login / Signup** Supabase Auth form. First login → Onboarding. Returning login → Dashboard.

**Screen 2 - Onboarding / Config** Keywords input, verticals checkboxes (AI / fintech / healthtech / B2B SaaS / climate / edtech), stage filter (Seed / Series A / Series B), schedule (daily or weekly), delivery email.

**Screen 3 - Dashboard / Briefing Feed** Agent status indicator (idle / running / waiting for your review), past briefings list (date, status, item count), manual run trigger button, briefings expandable inline.

**Screen 4 - HITL Review Screen** _(most important for demo)_ Full draft briefing with all items, edit capability per item, Approve button (resumes graph), Reject button (discards run). This screen demonstrates the human-in-the-loop architecture visually.

**Screen 5 - Briefing Detail** Each item as a card: title, summary, source link, category, confidence score indicator. Thumbs up (useful) / thumbs down (not relevant) buttons. Optional feedback reason dropdown. Timestamp if already rated.

**Screen 6 - Run Metrics** _(data quality monitor)_ Shows agent_run_metrics for the last 5 runs. Per-source result counts, freshness drop rate, scope drop rate, dedup drop rate, token cost, runtime. Answers: is my data fresh and relevant this week?

**Screen 7 - Memory Inspector** _(portfolio/demo feature)_ Three tabs: Semantic | Episodic | Procedural. Shows the agent's current memory state. Read-only. Procedural tab shows the JSON preference profile and when it was last updated.

**Screen 8 - Config / Settings** Editable version of onboarding. Update keywords, verticals, schedule at any time.

## 22\. Feedback Loop (Step by Step)

1\. User reads briefing on Screen 5  
2\. Clicks thumbs up/down + optional reason per item  
3\. POST /items/{id}/feedback → writes to briefing_items table  
4\. After minimum 5 feedback signals accumulated:  
5\. Procedural Memory Updater triggers (deterministic - no LLM)  
6\. Reads all feedback records for user  
7\. Counts patterns:  
\- Which categories have >60% "useful" rate → high_signal_categories  
\- Which categories have >60% "not_relevant" rate → low_signal_categories  
\- Which sources produce high-feedback items → boost source_weights  
\- Which terms appear in useful items' entities → query_boost_terms  
8\. Writes updated procedural memory JSON to LangGraph Store  
9\. No prompt rewriting. No autonomous strategy generation.  
Structured preference JSON update only.  
10\. Next run: Search Planner reads updated procedural memory,  
adjusts query terms, source priorities  
11\. Over 3-5 runs: briefing shifts measurably toward user interests

## 23\. LangSmith Evaluation

- Every node traced via LANGCHAIN_TRACING_V2=true + LANGSMITH_API_KEY
- Each run produces ~17-22 traces (2 more nodes than v1.1)
- Free tier: 5,000 traces/month - sufficient for entire build phase

**Phase 3 evaluation dataset:**

- Manually create 10-15 golden runs in evaluation_datasets table
- LangSmith evaluation API scores new runs against golden set

**What is measured:**

- Briefing relevance score (manual 0-1)
- Dedup accuracy (did already-reported items resurface?)
- Freshness accuracy (did stale items slip through the freshness node?)
- Scope accuracy (did out-of-scope items reach synthesis?)
- Synthesis quality (coherence, completeness, actionability)
- Source distribution (over-reliance on one source?)
- Entity extraction accuracy (are company/amount/stage fields populated correctly?)

## 24\. Tech Stack

| **Component**   | **Choice**                                           | **Reason**                                      |
| --------------- | ---------------------------------------------------- | ----------------------------------------------- |
| Language        | Python                                               | LangGraph is Python-first                       |
| Agent framework | LangGraph                                            | Core learning objective                         |
| LLM - nodes     | GPT-4o mini                                          | Fast, cheap, classification and extraction      |
| LLM - synthesis | GPT-4o                                               | Quality briefing generation                     |
| Embeddings      | text-embedding-3-small                               | Cheap, fast, 0.85 threshold validated (Spike 3) |
| Search          | Tavily API with include_domains                      | Free tier; include_domains required (Spike 1)   |
| Database        | Supabase PostgreSQL + pgvector                       | Free tier, familiar from Grape Guru             |
| Checkpointer    | MemorySaver (P1) → PostgresSaver (P2)                | Start simple, migrate cleanly                   |
| Memory store    | InMemoryStore (P1) → PostgresStore (P2)              | Same migration pattern                          |
| Auth            | Supabase Auth (email/password)                       | Same pattern as Grape Guru                      |
| Observability   | LangSmith                                            | Free tier, traces every node                    |
| Email delivery  | smtplib + Gmail App Password (P2) → Gmail OAuth (P3) | Zero friction to start                          |
| Scheduler       | APScheduler                                          | Pure Python, no infra needed locally            |
| Backend         | FastAPI                                              | Lightweight, async, pairs well with LangGraph   |
| Frontend        | HTML/JS (clean, custom)                              | Focus on LangGraph, not frontend complexity     |
| IDE             | Cursor Pro + Claude                                  | Existing setup                                  |

## 25\. Build Phases

### Phase 1 - One Working Run

**Target:** 2-3 weeks **Goal:** A single end-to-end run producing a readable, real briefing with metrics.

**Build order (strict):**

- SignalState TypedDict and all data models - before any node code
- ALLOWED_CATEGORIES, SOURCE_TRUST, ErrorCode constants
- Config Loader (static config dict, no DB)
- Search Planner (deterministic query generation; all Tavily queries include include_domains)
- Parallel research nodes via Send API: Tavily + YC API + HN Algolia + Google News RSS
- Reducer
- **Freshness Validation Node** (deterministic, pure Python - build immediately after Reducer)
- Entity Extraction (GPT-4o mini, structured output, name normalization; use Prompt v3)
- **Scope Filter Node** (deterministic, pure Python - build immediately after Entity Extraction)
- Source Trust Scoring (deterministic)
- Dedup (pre-filter on company_name_normalized + announced_date + URL match + normalized title match)
- Synthesis (GPT-4o)
- Episodic Memory Writer (InMemoryStore)
- Run Metrics Writer (log to console in Phase 1, write to DB in Phase 2)
- Output to terminal or simple HTML page

**Memory:** MemorySaver + InMemoryStore. No Supabase. **Not in Phase 1:** Gmail, Scheduler, HITL, Auth, Supabase, pgvector, embeddings.

**Definition of done (strict):**

- One complete run with ≥5 deduplicated items from ≥2 distinct sources
- Entity extraction uses Prompt v3 and returns structured fields for ≥3 items including normalized name
- Category is always from ALLOWED_CATEGORIES - no exceptions
- Freshness Validation Node logs dropped count to console; at least 1 drop confirmed in a test run
- Scope Filter Node logs dropped count to console
- agent_run_metrics data logged (even if just to console), including findings_dropped_freshness and findings_dropped_scope
- Full run traced in LangSmith with no missing node spans
- Briefing output is readable as a standalone document
- No crashes, no unhandled exceptions

### Phase 2 - Persistence, Scheduling, HITL, Delivery

**Target:** 2-3 weeks

**Build:**

- Supabase project setup + pgvector enabled
- Full database schema created (all tables)
- PostgresSaver replacing MemorySaver
- PostgresStore replacing InMemoryStore
- Semantic memory + Episodic memory implemented in Store
- Embedding generation on entity extraction + pgvector dedup at 0.85 threshold
- companies and funding_rounds tables populated from entity extraction output
- Supabase Auth + FastAPI JWT middleware + RLS
- APScheduler
- HITL interrupt() - graph pauses, persists, resumes
- Episodic Memory Writer confirmed running before Delivery node
- Gmail delivery via smtplib + App Password
- agent_run_metrics writing to DB
- FastAPI backend with all endpoints including /metrics/runs and /metrics/sources
- Frontend: Dashboard, HITL Review Screen, Briefing Detail, Run Metrics screen
- Inc42 RSS + YourStory RSS nodes added to parallel research

**Definition of done:**

- Agent runs on schedule
- Pauses at HITL, resumes on approve, discards on reject
- Sends approved briefing via Gmail
- Does not re-report items from previous runs (embedding dedup working)
- agent_run_metrics table populated after every run including freshness and scope drop counts
- Feedback buttons write to DB

### Phase 3 - Feedback Loop, Evaluation, ATS, Failure Queue

**Target:** 2-3 weeks

**Build:**

- Procedural Memory Updater (deterministic, triggers after ≥5 feedback signals)
- Memory Inspector UI screen (3 tabs)
- Config / Settings screen
- evaluation_datasets table + manual golden run creation
- LangSmith evaluation layer (including freshness and scope accuracy metrics)
- Gmail OAuth upgrade
- Greenhouse + Lever ATS nodes (using companies table slugs)
- failed_findings table and failure logging (captures freshness_filter, scope_filter, entity_extraction_failed, dedup_removed)
- Evaluation datasets first eval run against LangSmith

**Definition of done:**

- After 3 consecutive weekly runs with feedback, procedural memory JSON shows visible updates
- Briefing measurably shifts to reflect preferences (verified via metrics)
- LangSmith eval scoring works against at least one golden example
- failed_findings table populated; at least one entry per failure type visible

### Phase 4 - Multi-Tenancy

**Timeline:** undefined, post-MVP

- Namespace all Store reads/writes by user_id (already built in from Phase 2)
- User management UI
- Test with 2-3 distinct user configs
- Refactor, not rebuild

## 26\. Cost Structure

| **Service**                                    | **Build phase cost**               |
| ---------------------------------------------- | ---------------------------------- |
| OpenAI API (GPT-4o mini + GPT-4o + embeddings) | \$5-\$20                           |
| Tavily (1,000 free credits/month)              | \$0                                |
| Supabase (free tier: 500MB, 2 projects)        | \$0                                |
| LangSmith (free tier: 5,000 traces/month)      | \$0                                |
| Gmail delivery                                 | \$0                                |
| All other tools and libraries                  | \$0                                |
| **Total**                                      | **\$5-\$20, will not exceed \$25** |

## 27\. Known Risks and Mitigations

| **Risk**                                                       | **Mitigation**                                                                                                                                            |
| -------------------------------------------------------------- | --------------------------------------------------------------------------------------------------------------------------------------------------------- |
| Gmail delivery fails mid-run                                   | Episodic Memory Writer runs before Delivery. Run is persisted regardless. Retry delivery without re-running graph.                                        |
| Tavily returns thin signal on slow news weeks                  | YC API and HN Algolia are news-cycle independent. Shorter briefings are realistic. Monitor via findings_retrieved in run metrics.                         |
| Tavily returns off-topic results                               | include_domains required on all queries (Spike 1 finding). Without it, LinkedIn/YouTube noise dominates. Never call Tavily without include_domains.       |
| YC Companies API endpoint changes                              | Not using Tavily for YC. Fallback: Tavily queries with include_domains=\["ycombinator.com"\] targeting YC content directly.                               |
| Entity extraction returns wrong category                       | ALLOWED_CATEGORIES enforced in Prompt v3. Add validation in node - reject any item with invalid category, log to failed_findings.                         |
| Company name variants break dedup                              | Normalize at extraction. Maintain manual alias dict. Monitor findings_dropped_dedup rate - spike means normalization is failing.                          |
| Freshness Validation drops valid content from dateless sources | Undated findings are penalized (−0.10 confidence), not dropped. Only findings with parseable dates older than 30 days are dropped.                        |
| Scope Filter drops findings with null location                 | Drop rule is "drop only if explicitly out of scope." Null location = ambiguous = keep. Non-Indian explicit location = drop.                               |
| Embedding dedup false positives                                | Start at 0.85 cosine threshold (validated in Spike 3). Track near-duplicates (0.75-0.85) separately. Tune after 3 real runs with data.                    |
| LangGraph state complexity causes hard-to-debug errors         | SignalState locked before any node code. ErrorCode constants defined. LangSmith from day one. Never add a node until previous is fully tested and traced. |
| APScheduler process dies on deployment                         | Local dev: acceptable. Cloud: expose /agent/run, trigger via external cron (cron-job.org is free).                                                        |
| Supabase project pauses after 7 days inactivity                | Daily scheduled runs keep project active. Non-issue once scheduling runs.                                                                                 |
| Procedural memory over-corrects on few signals                 | Minimum 5 signals before any update. Source weights floored at 0.3 - no source ever fully suppressed.                                                     |

## 28\. LangGraph Concepts Demonstrated

| **Concept**                      | **Where Used**                                                      |
| -------------------------------- | ------------------------------------------------------------------- |
| TypedDict state schema           | SignalState - foundation of entire graph                            |
| Conditional edges                | Router: scheduled full run vs manual                                |
| Send API - parallel nodes        | All research nodes fire simultaneously                              |
| Reducer functions                | raw_findings: Annotated\[list, operator.add\]                       |
| Deterministic intermediate nodes | Freshness Validation + Scope Filter - pure Python between LLM nodes |
| MemorySaver → PostgresSaver      | Phase 1 → Phase 2 migration                                         |
| InMemoryStore → PostgresStore    | Phase 1 → Phase 2 migration                                         |
| LangGraph Store (3 memory types) | Semantic, Episodic, Procedural namespaces                           |
| interrupt() - HITL               | Graph pauses, persists, resumes on user action                      |
| Scheduled execution              | Agent as persistent running system                                  |
| Cross-session persistence        | Full memory survives restarts                                       |
| LangSmith tracing                | Every node input/output logged                                      |
| Time travel                      | thread_id stored per run enables state replay                       |

## 29\. GitHub Reference Repositories

Study these before and during development. Not optional reading for the graph code.

### Must Read - Study Before Writing Any Graph Code

[**langchain-ai/langgraph**](https://github.com/langchain-ai/langgraph) The core framework. Read the source before using it. Specific sections to study:

- langgraph/graph/state.py - how StateGraph and TypedDict state work
- langgraph/channels/ - how Annotated reducers are implemented
- langgraph/pregel/ - how Send API dispatches parallel nodes
- docs/docs/concepts/ - persistence, memory, interrupts

Use when implementing: SignalState, Send API parallel research layer, Reducer, interrupt() for HITL, PostgresSaver migration.

[**langchain-ai/open_deep_research**](https://github.com/langchain-ai/open_deep_research) The single closest existing project to Signal's architecture. A research agent that runs parallel web searches, synthesizes findings, and produces structured reports. Study:

- How the research planner generates query plans
- How parallel search results are reduced into shared state
- How the report synthesis node structures its output prompt
- How intermediate filter nodes are placed between parallel search and synthesis

You will likely borrow patterns from this repo directly. Read it before writing the Search Planner node.

### Reference During Development

[**langchain-ai/langgraph-example**](https://github.com/langchain-ai/langgraph-example) Canonical examples for persistence patterns, HITL with interrupt(), and memory. Use when implementing:

- PostgresSaver checkpointer setup
- interrupt() and graph resume after user action
- LangGraph Store read/write patterns

[**NirDiamant/GenAI_Agents**](https://github.com/NirDiamant/GenAI_Agents) Collection of agent patterns with explanations. Use for reference when implementing:

- Structured entity extraction with GPT-4o mini
- Memory patterns (episodic, semantic)
- Evaluation approaches for agent output quality
- Agent observability patterns

### Inspiration / Future Reference

[**ashishpatel26/500-AI-Agents-Projects**](https://github.com/ashishpatel26/500-AI-Agents-Projects) Broad catalog of agent project ideas and patterns. Not architecture reference - use for feature ideas when planning Phase 3 and Phase 4 extensions. Do not use as a pattern source during active development.

_Signal PRD v1.2 - spikes validated, architecture production-hardened, ready for node code._