"""HTTP route handlers for the Signal API."""

from __future__ import annotations

import logging
import os
import time
from uuid import uuid4

from fastapi import APIRouter, HTTPException

from api.schemas import HealthResponse, RunRequest, RunResponse, RuntimeMetrics

logger = logging.getLogger(__name__)

router = APIRouter()

_BRIEFING_SUMMARY_MAX_LEN = 500


def _build_initial_state(request: RunRequest, run_id: str) -> dict:
    """Mirror agent.graph.run_graph initial state with optional API overrides."""
    return {
        "run_id": run_id,
        "raw_findings": [],
        "scored_findings": [],
        "new_findings": [],
        "briefing_items": [],
        "sources_queried": [],
        "findings_retrieved": 0,
        "findings_dropped_freshness": 0,
        "findings_dropped_dedup": 0,
        "findings_dropped_scope": 0,
        "tokens_used": 0,
        "estimated_cost_usd": 0.0,
        "run_duration_seconds": 0.0,
        "run_config_snapshot": {},
        "error": None,
        "source_failures": {},
        "semantic_memory": {},
        "procedural_memory": {},
        "query_plan": {},
        "user_config": {},
        "user_id": request.user_id or "",
        "thread_id": request.thread_id or "",
        "run_type": request.run_type,
        "graph_version": os.getenv("GRAPH_VERSION", "1.0"),
        "hitl_decision": None,
        "hitl_edits": None,
        "delivery_status": None,
        "briefing_draft": "",
        "briefing_final": "",
    }


def _briefing_summary_from_state(state: dict) -> str:
    text = (
        state.get("briefing_final")
        or state.get("briefing_draft")
        or ""
    )
    if len(text) <= _BRIEFING_SUMMARY_MAX_LEN:
        return text
    return text[: _BRIEFING_SUMMARY_MAX_LEN - 3] + "..."


def _runtime_metrics_from_state(state: dict) -> RuntimeMetrics:
    return RuntimeMetrics(
        run_duration_seconds=float(state.get("run_duration_seconds") or 0.0),
        tokens_used=int(state.get("tokens_used") or 0),
        estimated_cost_usd=float(state.get("estimated_cost_usd") or 0.0),
        findings_retrieved=int(state.get("findings_retrieved") or 0),
        findings_dropped_freshness=int(state.get("findings_dropped_freshness") or 0),
        findings_dropped_scope=int(state.get("findings_dropped_scope") or 0),
        findings_dropped_dedup=int(state.get("findings_dropped_dedup") or 0),
        graph_version=str(state.get("graph_version") or ""),
    )


def _resolve_status(final_state: dict, graph_state) -> str:
    if graph_state.next:
        return "pending_hitl"
    if final_state.get("error"):
        return "failed"
    return "completed"


def execute_pipeline(request: RunRequest) -> RunResponse:
    """Invoke the existing LangGraph pipeline and map state to a RunResponse."""
    from agent.graph import graph

    run_id = str(uuid4())
    thread_id = request.thread_id or f"run_{uuid4().hex[:12]}"
    initial_state = _build_initial_state(request, run_id)
    config = {"configurable": {"thread_id": thread_id}}

    start = time.perf_counter()
    final_state = graph.invoke(initial_state, config)
    elapsed = time.perf_counter() - start

    if not final_state.get("run_duration_seconds"):
        final_state = {**final_state, "run_duration_seconds": elapsed}

    graph_state = graph.get_state(config)
    status = _resolve_status(final_state, graph_state)

    return RunResponse(
        run_id=str(final_state.get("run_id") or run_id),
        status=status,
        briefing_summary=_briefing_summary_from_state(final_state),
        delivery_status=final_state.get("delivery_status"),
        runtime_metrics=_runtime_metrics_from_state(final_state),
        error=final_state.get("error"),
    )


@router.get("/health", response_model=HealthResponse)
def health() -> HealthResponse:
    return HealthResponse()


@router.post("/run", response_model=RunResponse)
def run_pipeline(request: RunRequest | None = None) -> RunResponse:
    body = request or RunRequest()
    try:
        return execute_pipeline(body)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception as exc:
        logger.exception("Pipeline execution failed")
        raise HTTPException(
            status_code=500,
            detail="Pipeline execution failed. Check server logs for details.",
        ) from exc
