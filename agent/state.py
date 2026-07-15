from typing import Annotated, Optional, TypedDict

import operator

ALLOWED_CATEGORIES = [
    "funding",
    "hiring",
    "founder_move",
    "accelerator",
    "shutdown",
    "pivot",
    "ecosystem_trend",
]

SOURCE_TRUST = {
    "yc": 1.0,
    "techcrunch": 0.95,
    "inc42": 0.90,
    "yourstory": 0.90,
    "economictimes": 0.85,
    "mint": 0.85,
    "hn": 0.70,
    "google_news": 0.65,
    "rss_other": 0.60,
}


class ErrorCode:
    ENTITY_EXTRACTION_FAILED = "ENTITY_EXTRACTION_FAILED"
    TAVILY_TIMEOUT = "TAVILY_TIMEOUT"
    YC_API_UNAVAILABLE = "YC_API_UNAVAILABLE"
    DEDUP_EMBEDDING_FAILED = "DEDUP_EMBEDDING_FAILED"
    SYNTHESIS_FAILED = "SYNTHESIS_FAILED"
    DELIVERY_FAILED = "DELIVERY_FAILED"
    GMAIL_AUTH_FAILED = "GMAIL_AUTH_FAILED"


class RawFinding(TypedDict):
    title: str
    summary: str
    source_url: str
    source_name: str
    published_date: Optional[str]


class EntityData(TypedDict):
    company_name: Optional[str]
    company_name_normalized: Optional[str]
    founder_name: Optional[str]
    investor_names: Optional[list[str]]
    investor_names_normalized: Optional[list[str]]
    funding_amount_usd: Optional[int]
    funding_stage: Optional[str]
    sector: Optional[str]
    location: Optional[str]
    announced_date: Optional[str]


class ScoredFinding(TypedDict):
    title: str
    summary: str
    source_url: str
    source_name: str
    published_date: Optional[str]
    entities: EntityData
    category: str
    source_trust_score: float
    freshness_penalty_applied: bool
    confidence_score: float
    is_duplicate: bool
    duplicate_reason: Optional[str]


class BriefingItem(TypedDict):
    id: str
    title: str
    summary: str
    source_url: str
    source_name: str
    category: str
    confidence_score: float
    entities: EntityData


class SignalState(TypedDict):
    run_id: str
    user_id: str
    thread_id: str
    run_type: str
    graph_version: str
    user_config: dict
    semantic_memory: dict
    procedural_memory: dict
    query_plan: dict
    raw_findings: Annotated[list[RawFinding], operator.add]
    scored_findings: list[ScoredFinding]
    new_findings: list[ScoredFinding]
    briefing_draft: str
    briefing_items: list[BriefingItem]
    briefing_final: str
    hitl_decision: Optional[str]
    hitl_edits: Optional[dict]
    delivery_status: Optional[str]
    sources_queried: list[str]
    findings_retrieved: int
    findings_dropped_freshness: int
    findings_dropped_dedup: int
    findings_dropped_scope: int
    tokens_used: int
    estimated_cost_usd: float
    run_duration_seconds: float
    run_config_snapshot: dict
    error: Optional[dict]
    source_failures: dict
