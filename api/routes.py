"""HTTP route handlers for the Signal API."""

from __future__ import annotations

import logging
import json
import time
from datetime import datetime, timezone
from typing import Any, Optional
from uuid import UUID, uuid4

from fastapi import APIRouter, HTTPException, Query
from langgraph.types import Command

from agent.graph import (
    _invoke_with_stale_conn_retry,
    execute_graph,
    graph,
    pool,
)
from agent.nodes.run_metrics_writer import finalize_run_duration
from api.schemas import (
    AgentStatusResponse,
    BriefingItemSchema,
    BriefingListEntry,
    BriefingListResponse,
    BriefingResponse,
    FeedbackRequest,
    FeedbackResponse,
    HealthResponse,
    RunMetricsEntry,
    RunMetricsListResponse,
    RunRequest,
    RunResponse,
    RuntimeMetrics,
)

logger = logging.getLogger(__name__)

router = APIRouter()

_BRIEFING_SUMMARY_MAX_LEN = 500


def _briefing_summary_from_state(state: dict) -> str:
    text = state.get("briefing_final") or state.get("briefing_draft") or ""
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


def _resolve_status(final_state: dict, checkpoint_next: tuple[str, ...]) -> str:
    if checkpoint_next:
        return "pending_hitl"
    if final_state.get("error"):
        return "failed"
    return "completed"


def _is_pending_hitl(graph_state: Any) -> bool:
    """True when the checkpoint is paused at (or inside) HITL."""
    next_nodes = tuple(graph_state.next or ())
    if "hitl_node" in next_nodes:
        return True
    for task in getattr(graph_state, "tasks", ()) or ():
        if getattr(task, "interrupts", None):
            return True
    return False


def _feedback_at_str(value: Any) -> Optional[str]:
    if value is None:
        return None
    if hasattr(value, "isoformat"):
        return value.isoformat()
    text = str(value).strip()
    return text or None


def _briefing_items_from_state(raw_items: Any) -> list[BriefingItemSchema]:
    items: list[BriefingItemSchema] = []
    for item in raw_items or []:
        if not isinstance(item, dict):
            continue
        entities = item.get("entities")
        if not isinstance(entities, dict):
            entities = {}
        fb = item.get("feedback")
        feedback_val = fb if fb in ("useful", "not_relevant") else None
        items.append(
            BriefingItemSchema(
                id=str(item.get("id") or ""),
                title=str(item.get("title") or ""),
                summary=str(item.get("summary") or ""),
                source_url=str(item.get("source_url") or ""),
                source_name=str(item.get("source_name") or ""),
                category=str(item.get("category") or ""),
                confidence_score=float(item.get("confidence_score") or 0.0),
                entities=entities,
                feedback=feedback_val,
                feedback_reason=item.get("feedback_reason"),
                feedback_at=_feedback_at_str(item.get("feedback_at")),
            )
        )
    return items


def _as_uuid_or_none(value: str) -> Optional[UUID]:
    try:
        return UUID(str(value))
    except (ValueError, TypeError, AttributeError):
        return None


def _thread_id_from_briefing_runs(run_id: str) -> Optional[str]:
    """Resolve thread_id from persisted briefing_runs.id (post-HITL only)."""
    run_uuid = _as_uuid_or_none(run_id)
    if run_uuid is None:
        return None
    try:
        with pool.connection() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    "SELECT thread_id FROM briefing_runs WHERE id = %s",
                    (str(run_uuid),),
                )
                row = cur.fetchone()
                if row and row.get("thread_id"):
                    return str(row["thread_id"])
    except Exception:
        logger.exception("Failed to resolve thread_id from briefing_runs")
    return None


def _briefing_from_checkpoint(
    run_id: str, thread_id: str
) -> Optional[BriefingResponse]:
    """Serve HITL draft from checkpointed graph state when paused at HITL.

    Requires the runtime-contract thread_id (from POST /run). Does not reverse-
    lookup thread_id from checkpoint storage.
    """
    config = {"configurable": {"thread_id": thread_id}}
    try:
        graph_state = graph.get_state(config)
    except Exception:
        logger.exception(
            "Failed to load graph state for run_id=%s thread_id=%s",
            run_id,
            thread_id,
        )
        return None

    values = graph_state.values or {}
    if str(values.get("run_id") or "") != str(run_id):
        return None
    if not _is_pending_hitl(graph_state):
        return None

    created_at = getattr(graph_state, "created_at", None)
    if created_at is not None and hasattr(created_at, "isoformat"):
        created_at_str = created_at.isoformat()
    else:
        created_at_str = datetime.now(timezone.utc).isoformat()

    return BriefingResponse(
        run_id=str(values.get("run_id") or run_id),
        thread_id=str(values.get("thread_id") or thread_id),
        status="pending_hitl",
        created_at=created_at_str,
        briefing_draft=str(values.get("briefing_draft") or ""),
        briefing_final=str(values.get("briefing_final") or ""),
        briefing_items=_briefing_items_from_state(values.get("briefing_items")),
        runtime_metrics=_runtime_metrics_from_state(values),
    )


def _briefing_from_db(run_id: str) -> BriefingResponse:
    """Serve completed/rejected briefing from briefing_runs + related tables."""
    run_uuid = _as_uuid_or_none(run_id)
    if run_uuid is None:
        raise HTTPException(status_code=404, detail="Briefing not found")

    with pool.connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT id, thread_id, status, run_at, final_briefing, graph_version
                FROM briefing_runs
                WHERE id = %s
                """,
                (str(run_uuid),),
            )
            run_row = cur.fetchone()
            if not run_row:
                raise HTTPException(status_code=404, detail="Briefing not found")

            cur.execute(
                """
                SELECT id, title, summary, source_url, source_name,
                       category, confidence_score, entities,
                       feedback, feedback_reason, feedback_at
                FROM briefing_items
                WHERE briefing_run_id = %s
                """,
                (str(run_uuid),),
            )
            item_rows = cur.fetchall()

            items = []
            for row in item_rows:
                fb = row.get("feedback")
                feedback_val = fb if fb in ("useful", "not_relevant") else None
                items.append(
                    BriefingItemSchema(
                        id=str(row["id"]),
                        title=row["title"] or "",
                        summary=row["summary"] or "",
                        source_url=row["source_url"] or "",
                        source_name=row["source_name"] or "",
                        category=row["category"] or "",
                        confidence_score=float(row["confidence_score"] or 0.0),
                        entities=(
                            row["entities"]
                            if isinstance(row["entities"], dict)
                            else {}
                        ),
                        feedback=feedback_val,
                        feedback_reason=row.get("feedback_reason"),
                        feedback_at=_feedback_at_str(row.get("feedback_at")),
                    )
                )

            cur.execute(
                """
                SELECT run_duration_seconds, tokens_used, estimated_cost_usd,
                       findings_retrieved, findings_dropped_freshness,
                       findings_dropped_scope, findings_dropped_dedup,
                       graph_version
                FROM agent_run_metrics
                WHERE briefing_run_id = %s
                ORDER BY run_at DESC
                LIMIT 1
                """,
                (str(run_uuid),),
            )
            metrics_row = cur.fetchone()
            metrics = None
            if metrics_row:
                metrics = RuntimeMetrics(
                    run_duration_seconds=float(
                        metrics_row["run_duration_seconds"] or 0.0
                    ),
                    tokens_used=int(metrics_row["tokens_used"] or 0),
                    estimated_cost_usd=float(metrics_row["estimated_cost_usd"] or 0.0),
                    findings_retrieved=int(metrics_row["findings_retrieved"] or 0),
                    findings_dropped_freshness=int(
                        metrics_row["findings_dropped_freshness"] or 0
                    ),
                    findings_dropped_scope=int(
                        metrics_row["findings_dropped_scope"] or 0
                    ),
                    findings_dropped_dedup=int(
                        metrics_row["findings_dropped_dedup"] or 0
                    ),
                    graph_version=str(metrics_row["graph_version"] or ""),
                )

            final_text = run_row.get("final_briefing") or ""
            run_at = run_row.get("run_at")
            created_at = (
                run_at.isoformat()
                if run_at is not None and hasattr(run_at, "isoformat")
                else datetime.now(timezone.utc).isoformat()
            )

            return BriefingResponse(
                run_id=str(run_row["id"]),
                thread_id=str(run_row.get("thread_id") or ""),
                status=str(run_row.get("status") or ""),
                created_at=created_at,
                briefing_draft=final_text,
                briefing_final=final_text,
                briefing_items=items,
                runtime_metrics=metrics,
            )


def execute_pipeline(request: RunRequest) -> RunResponse:
    """Map a validated API request onto the shared graph execution path."""
    thread_id = request.thread_id or f"run_{uuid4().hex[:12]}"
    result = execute_graph(
        user_id=request.user_id,
        run_type=request.run_type,
        thread_id=thread_id,
    )
    final_state = result.state

    return RunResponse(
        run_id=str(final_state.get("run_id") or ""),
        thread_id=str(final_state.get("thread_id") or thread_id),
        status=_resolve_status(final_state, result.checkpoint_next),
        briefing_summary=_briefing_summary_from_state(final_state),
        delivery_status=final_state.get("delivery_status"),
        runtime_metrics=_runtime_metrics_from_state(final_state),
        error=final_state.get("error"),
    )


@router.get("/health", response_model=HealthResponse)
def health() -> HealthResponse:
    return HealthResponse()


@router.get("/agent/status", response_model=AgentStatusResponse)
def get_agent_status(thread_id: str = "run_001") -> AgentStatusResponse:
    """Check the current status of the agent for a given thread."""
    try:
        config = {"configurable": {"thread_id": thread_id}}
        graph_state = graph.get_state(config)

        status = "idle"
        if graph_state.next:
            if "hitl_node" in graph_state.next:
                status = "pending_hitl"
            else:
                status = "running"
        elif _is_pending_hitl(graph_state):
            status = "pending_hitl"

        return AgentStatusResponse(status=status, thread_id=thread_id)
    except Exception as exc:
        logger.exception("Failed to get agent status")
        raise HTTPException(status_code=500, detail=str(exc))


@router.get("/briefings", response_model=BriefingListResponse)
def list_briefings(limit: int = Query(10, ge=1, le=100)) -> BriefingListResponse:
    """List recent briefing runs from the database."""
    try:
        with pool.connection() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    SELECT br.id,
                           br.thread_id,
                           br.status,
                           br.run_at,
                           (
                               SELECT count(*)
                               FROM briefing_items bi
                               WHERE bi.briefing_run_id = br.id
                           ) AS item_count
                    FROM briefing_runs br
                    ORDER BY br.run_at DESC
                    LIMIT %s
                    """,
                    (limit,),
                )
                rows = cur.fetchall()

                briefings = [
                    BriefingListEntry(
                        run_id=str(row["id"]),
                        thread_id=row["thread_id"] or "",
                        status=row["status"] or "",
                        created_at=(
                            row["run_at"].isoformat()
                            if row["run_at"] is not None
                            else ""
                        ),
                        item_count=int(row["item_count"] or 0),
                    )
                    for row in rows
                ]
                return BriefingListResponse(briefings=briefings)
    except Exception as exc:
        logger.exception("Failed to list briefings")
        # Return empty list if table doesn't exist yet (graceful degradation)
        if "does not exist" in str(exc):
            return BriefingListResponse(briefings=[])
        raise HTTPException(status_code=500, detail=str(exc))


def _optional_int(value: Any) -> Optional[int]:
    """Preserve NULL from DB; do not coerce missing counts to fabricated zeros."""
    if value is None:
        return None
    return int(value)


def _source_health_dict(value: Any) -> dict[str, Any]:
    if isinstance(value, dict):
        return dict(value)
    if isinstance(value, str) and value.strip():
        try:
            parsed = json.loads(value)
            if isinstance(parsed, dict):
                return parsed
        except Exception:
            return {}
    return {}


@router.get("/metrics/runs", response_model=RunMetricsListResponse)
def list_run_metrics(limit: int = Query(5, ge=1, le=50)) -> RunMetricsListResponse:
    """Return recent agent_run_metrics rows for the Run Metrics screen."""
    try:
        with pool.connection() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    SELECT m.id,
                           m.briefing_run_id,
                           m.run_at,
                           m.findings_retrieved,
                           m.findings_dropped_freshness,
                           m.findings_dropped_scope,
                           m.findings_dropped_dedup,
                           m.findings_in_briefing,
                           m.tokens_used,
                           m.estimated_cost_usd,
                           m.run_duration_seconds,
                           m.tavily_result_count,
                           m.yc_result_count,
                           m.hn_result_count,
                           m.rss_result_count,
                           m.sources_queried,
                           m.graph_version,
                           m.source_health,
                           br.status AS run_status
                    FROM agent_run_metrics m
                    LEFT JOIN briefing_runs br ON br.id = m.briefing_run_id
                    ORDER BY m.run_at DESC
                    LIMIT %s
                    """,
                    (limit,),
                )
                rows = cur.fetchall()

                runs: list[RunMetricsEntry] = []
                for row in rows:
                    run_at = row.get("run_at")
                    sources = row.get("sources_queried") or []
                    if not isinstance(sources, list):
                        sources = list(sources) if sources else []
                    runs.append(
                        RunMetricsEntry(
                            id=str(row["id"]),
                            run_id=str(row["briefing_run_id"]),
                            status=str(row.get("run_status") or "completed"),
                            run_at=(
                                run_at.isoformat()
                                if run_at is not None and hasattr(run_at, "isoformat")
                                else str(run_at or "")
                            ),
                            run_duration_seconds=float(
                                row.get("run_duration_seconds") or 0.0
                            ),
                            findings_retrieved=int(row.get("findings_retrieved") or 0),
                            findings_in_briefing=int(
                                row.get("findings_in_briefing") or 0
                            ),
                            findings_dropped_freshness=int(
                                row.get("findings_dropped_freshness") or 0
                            ),
                            findings_dropped_scope=int(
                                row.get("findings_dropped_scope") or 0
                            ),
                            findings_dropped_dedup=int(
                                row.get("findings_dropped_dedup") or 0
                            ),
                            tokens_used=int(row.get("tokens_used") or 0),
                            estimated_cost_usd=float(
                                row.get("estimated_cost_usd") or 0.0
                            ),
                            graph_version=str(row.get("graph_version") or ""),
                            tavily_result_count=_optional_int(
                                row.get("tavily_result_count")
                            ),
                            yc_result_count=_optional_int(row.get("yc_result_count")),
                            hn_result_count=_optional_int(row.get("hn_result_count")),
                            rss_result_count=_optional_int(row.get("rss_result_count")),
                            sources_queried=[str(s) for s in sources],
                            source_health=_source_health_dict(row.get("source_health")),
                        )
                    )
                return RunMetricsListResponse(runs=runs)
    except Exception as exc:
        logger.exception("Failed to list run metrics")
        if "does not exist" in str(exc):
            return RunMetricsListResponse(runs=[])
        raise HTTPException(status_code=500, detail=str(exc))


@router.get("/briefings/{run_id}", response_model=BriefingResponse)
def get_briefing(
    run_id: str,
    thread_id: Optional[str] = Query(
        None,
        description="LangGraph thread_id from POST /run; required for pending_hitl.",
    ),
) -> BriefingResponse:
    """Get briefing detail.

    pending_hitl → checkpointed LangGraph state via thread_id (no briefing_runs yet).
    After HITL → briefing_runs + briefing_items + agent_run_metrics.
    """
    try:
        if thread_id:
            pending = _briefing_from_checkpoint(run_id, thread_id)
            if pending is not None:
                return pending
        return _briefing_from_db(run_id)
    except HTTPException:
        raise
    except Exception as exc:
        logger.exception("Failed to get briefing detail")
        raise HTTPException(status_code=500, detail=str(exc))


@router.post("/items/{item_id}/feedback", response_model=FeedbackResponse)
def submit_item_feedback(
    item_id: str, body: FeedbackRequest
) -> FeedbackResponse:
    """Persist feedback atomically into user_feedback + briefing_items."""
    item_uuid = _as_uuid_or_none(item_id)
    if item_uuid is None:
        raise HTTPException(status_code=404, detail="Briefing item not found")

    try:
        with pool.connection() as conn:
            try:
                with conn.cursor() as cur:
                    cur.execute(
                        """
                        SELECT id, user_id, category, source_name, feedback
                        FROM briefing_items
                        WHERE id = %s
                        """,
                        (str(item_uuid),),
                    )
                    item_row = cur.fetchone()
                    if not item_row:
                        raise HTTPException(
                            status_code=404, detail="Briefing item not found"
                        )

                    cur.execute(
                        """
                        SELECT id
                        FROM user_feedback
                        WHERE briefing_item_id = %s
                        LIMIT 1
                        """,
                        (str(item_uuid),),
                    )
                    existing = cur.fetchone()
                    if existing or item_row.get("feedback") in (
                        "useful",
                        "not_relevant",
                    ):
                        raise HTTPException(
                            status_code=409,
                            detail="Already submitted.",
                        )

                    now = datetime.now(timezone.utc)
                    cur.execute(
                        """
                        INSERT INTO user_feedback (
                            user_id, briefing_item_id, category, source_name,
                            feedback, reason
                        ) VALUES (
                            %s, %s, %s, %s, %s, %s
                        )
                        RETURNING
                            id, user_id, briefing_item_id, category, source_name,
                            feedback, reason, created_at
                        """,
                        (
                            str(item_row["user_id"]),
                            str(item_uuid),
                            item_row.get("category"),
                            item_row.get("source_name"),
                            body.feedback,
                            body.reason,
                        ),
                    )
                    inserted = cur.fetchone()
                    if not inserted:
                        raise RuntimeError("user_feedback insert returned no row")

                    cur.execute(
                        """
                        UPDATE briefing_items
                        SET feedback = %s,
                            feedback_reason = %s,
                            feedback_at = %s
                        WHERE id = %s
                        """,
                        (
                            body.feedback,
                            body.reason,
                            now,
                            str(item_uuid),
                        ),
                    )

                conn.commit()
            except HTTPException:
                conn.rollback()
                raise
            except Exception:
                conn.rollback()
                raise

        created_at = _feedback_at_str(inserted.get("created_at")) or now.isoformat()
        return FeedbackResponse(
            id=str(inserted["id"]),
            briefing_item_id=str(item_uuid),
            feedback=body.feedback,
            reason=body.reason,
            created_at=created_at,
            duplicate=False,
        )
    except HTTPException:
        raise
    except Exception:
        logger.exception("Failed to submit item feedback")
        raise HTTPException(
            status_code=500,
            detail="Couldn't save feedback. Please try again.",
        )


@router.post("/briefings/{run_id}/approve", response_model=RunResponse)
def approve_briefing(
    run_id: str,
    thread_id: Optional[str] = Query(
        None,
        description="LangGraph thread_id from POST /run; required during pending_hitl.",
    ),
) -> RunResponse:
    """Resume the graph with 'approve' action for a given run."""
    return _resume_hitl(run_id, "approve", thread_id=thread_id)


@router.post("/briefings/{run_id}/reject", response_model=RunResponse)
def reject_briefing(
    run_id: str,
    thread_id: Optional[str] = Query(
        None,
        description="LangGraph thread_id from POST /run; required during pending_hitl.",
    ),
) -> RunResponse:
    """Resume the graph with 'reject' action for a given run."""
    return _resume_hitl(run_id, "reject", thread_id=thread_id)


def _resume_hitl(
    run_id: str,
    action: str,
    edits: dict | None = None,
    thread_id: Optional[str] = None,
) -> RunResponse:
    """Helper to resume the graph from HITL interrupt.

    Matches scripts/test_hitl.py: graph.invoke(Command(resume=...), config).
    Do not pass a plain dict — LangGraph treats that as a SignalState update.
    """
    try:
        tid = thread_id or _thread_id_from_briefing_runs(run_id)
        if not tid:
            raise HTTPException(status_code=404, detail="Run not found")

        config = {"configurable": {"thread_id": tid}}

        # Same contract as scripts/test_hitl.py and hitl_node interrupt resume.
        # HITL waits can outlive Supabase idle timeouts — retry path refreshes pool.
        if edits is not None:
            resume_payload: Any = {"action": action, "edits": edits}
        else:
            resume_payload = action

        start = time.perf_counter()
        final_state = _invoke_with_stale_conn_retry(
            Command(resume=resume_payload), config
        )
        elapsed = time.perf_counter() - start

        # Accumulate prior segment duration (saved at HITL pause) + this resume.
        prev = float(final_state.get("run_duration_seconds") or 0.0)
        total_duration = elapsed if prev <= 0.0 else prev + elapsed
        try:
            graph.update_state(config, {"run_duration_seconds": total_duration})
        except Exception:
            pass
        finalize_run_duration(final_state.get("run_id") or run_id, total_duration)
        final_state = {**final_state, "run_duration_seconds": total_duration}

        graph_state = graph.get_state(config)
        checkpoint_next = tuple(graph_state.next or ())

        return RunResponse(
            run_id=str(final_state.get("run_id") or ""),
            thread_id=str(final_state.get("thread_id") or tid),
            status=_resolve_status(final_state, checkpoint_next),
            briefing_summary=_briefing_summary_from_state(final_state),
            delivery_status=final_state.get("delivery_status"),
            runtime_metrics=_runtime_metrics_from_state(final_state),
            error=final_state.get("error"),
        )
    except HTTPException:
        raise
    except Exception as exc:
        logger.exception("Failed to resume HITL")
        raise HTTPException(status_code=500, detail=str(exc))


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
