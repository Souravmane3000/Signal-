"""SignalState, TypedDicts, ErrorCode, and shared constants."""

from __future__ import annotations

from enum import StrEnum
from typing import Any, TypedDict


class ErrorCode(StrEnum):
    CONFIG_LOAD_FAILED = "config_load_failed"
    SEARCH_FAILED = "search_failed"
    FRESHNESS_FAILED = "freshness_failed"
    ENTITY_EXTRACTION_FAILED = "entity_extraction_failed"
    SYNTHESIS_FAILED = "synthesis_failed"
    UNKNOWN = "unknown"


class SearchQuery(TypedDict):
    query: str
    source: str
    priority: int


class RawFinding(TypedDict, total=False):
    id: str
    title: str
    url: str
    snippet: str
    source: str
    published_at: str
    raw: dict[str, Any]


class ValidatedFinding(TypedDict, total=False):
    id: str
    title: str
    url: str
    snippet: str
    source: str
    published_at: str
    freshness_score: float
    trust_score: float
    entities: list[str]
    in_scope: bool


class EntityRecord(TypedDict, total=False):
    name: str
    type: str
    confidence: float
    source_finding_id: str


class SynthesisOutput(TypedDict, total=False):
    summary: str
    key_entities: list[str]
    sources: list[str]
    confidence: float


class SignalState(TypedDict, total=False):
    """LangGraph state for the Signal agent."""

    run_id: str
    config: dict[str, Any]
    search_plan: list[SearchQuery]
    raw_findings: list[RawFinding]
    validated_findings: list[ValidatedFinding]
    entities: list[EntityRecord]
    deduped_findings: list[ValidatedFinding]
    synthesis: SynthesisOutput
    errors: list[dict[str, Any]]
    metrics: dict[str, Any]


# --- constants ---

DEFAULT_MAX_RESULTS = 20
DEFAULT_FRESHNESS_DAYS = 30
TRUST_SCORE_THRESHOLD = 0.5
DEDUP_SIMILARITY_THRESHOLD = 0.85

SUPPORTED_SOURCES = (
    "tavily",
    "yc",
    "hn_algolia",
    "google_news_rss",
)

PROMPT_PATH_ENTITY_EXTRACTION = "agent/prompts/entity_extraction_v3.txt"
