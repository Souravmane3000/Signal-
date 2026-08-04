"""Pydantic request/response models for the Signal API."""

from __future__ import annotations

from typing import Any, Literal, Optional

from pydantic import BaseModel, Field


class HealthResponse(BaseModel):
    status: Literal["ok"] = "ok"


class AgentStatusResponse(BaseModel):
    status: Literal["idle", "running", "pending_hitl"]
    thread_id: Optional[str] = None


class HITLActionRequest(BaseModel):
    action: Literal["approve", "edit", "reject"]
    edits: Optional[dict[str, Any]] = None


class BriefingItemSchema(BaseModel):
    id: str
    title: str
    summary: str
    source_url: str
    source_name: str
    category: str
    confidence_score: float
    entities: dict[str, Any]
    feedback: Optional[Literal["useful", "not_relevant"]] = None
    feedback_reason: Optional[str] = None
    feedback_at: Optional[str] = None


class FeedbackRequest(BaseModel):
    """POST /items/{id}/feedback body (PRD §19)."""

    feedback: Literal["useful", "not_relevant"]
    reason: Optional[
        Literal[
            "already_knew",
            "wrong_stage",
            "wrong_sector",
            "too_generic",
            "great_find",
        ]
    ] = None


class FeedbackResponse(BaseModel):
    id: str
    briefing_item_id: str
    feedback: Literal["useful", "not_relevant"]
    reason: Optional[str] = None
    created_at: str
    duplicate: bool = False


class BriefingResponse(BaseModel):
    run_id: str
    thread_id: str
    status: str
    created_at: str
    briefing_draft: str
    briefing_final: str
    briefing_items: list[BriefingItemSchema]
    runtime_metrics: Optional[RuntimeMetrics] = None


class BriefingListEntry(BaseModel):
    run_id: str
    thread_id: str
    status: str
    created_at: str
    item_count: int


class BriefingListResponse(BaseModel):
    briefings: list[BriefingListEntry]


class RunRequest(BaseModel):
    """Optional overrides for a pipeline run. All fields optional."""

    user_id: Optional[str] = Field(
        default=None,
        description="User namespace key; defaults to user_001 via config_loader.",
    )
    run_type: Literal["manual", "scheduled"] = "manual"
    thread_id: Optional[str] = Field(
        default=None,
        description="LangGraph thread id; auto-generated when omitted.",
    )


class RuntimeMetrics(BaseModel):
    run_duration_seconds: float = 0.0
    tokens_used: int = 0
    estimated_cost_usd: float = 0.0
    findings_retrieved: int = 0
    findings_dropped_freshness: int = 0
    findings_dropped_scope: int = 0
    findings_dropped_dedup: int = 0
    graph_version: str = ""


class RunMetricsEntry(BaseModel):
    """One agent_run_metrics row for the Run Metrics screen (PRD Screen 6)."""

    id: str
    run_id: str
    status: str
    run_at: str
    run_duration_seconds: float = 0.0
    findings_retrieved: int = 0
    findings_in_briefing: int = 0
    findings_dropped_freshness: int = 0
    findings_dropped_scope: int = 0
    findings_dropped_dedup: int = 0
    tokens_used: int = 0
    estimated_cost_usd: float = 0.0
    graph_version: str = ""
    tavily_result_count: Optional[int] = None
    yc_result_count: Optional[int] = None
    hn_result_count: Optional[int] = None
    rss_result_count: Optional[int] = None
    sources_queried: list[str] = Field(default_factory=list)
    source_health: dict[str, Any] = Field(default_factory=dict)


class RunMetricsListResponse(BaseModel):
    runs: list[RunMetricsEntry]


class RunResponse(BaseModel):
    run_id: str
    thread_id: str
    status: Literal["completed", "pending_hitl", "failed"]
    briefing_summary: str
    delivery_status: Optional[str] = None
    runtime_metrics: Optional[RuntimeMetrics] = None
    error: Optional[dict[str, Any]] = None
