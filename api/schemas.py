"""Pydantic request/response models for the Signal API."""

from __future__ import annotations

from typing import Any, Literal, Optional

from pydantic import BaseModel, Field


class HealthResponse(BaseModel):
    status: Literal["ok"] = "ok"


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


class RunResponse(BaseModel):
    run_id: str
    status: Literal["completed", "pending_hitl", "failed"]
    briefing_summary: str
    delivery_status: Optional[str] = None
    runtime_metrics: Optional[RuntimeMetrics] = None
    error: Optional[dict[str, Any]] = None
