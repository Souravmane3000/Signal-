"""HTTP route handlers for the Signal API."""

from __future__ import annotations

import logging
import json
import time
from datetime import datetime, timezone
from typing import Any, Optional
from uuid import UUID, uuid4

from fastapi import APIRouter, Depends, HTTPException, Query
from langgraph.types import Command

from agent.graph import (
    _invoke_with_stale_conn_retry,
    execute_graph,
    get_live_node,
    graph,
    graph_invoke_config,
    lookup_langsmith_pipeline_node,
    pipeline_stage,
    pool,
)
from agent.nodes.run_metrics_writer import finalize_run_duration
from api.auth import (
    AuthUser,
    get_current_user,
    login_with_password,
    signup_with_password,
)
from api.schemas import (
    AgentStatusResponse,
    AuthCredentialsRequest,
    AuthResponse,
    AuthUserSchema,
    BriefingItemSchema,
    BriefingListEntry,
    BriefingListResponse,
    BriefingResponse,
    EpisodicMemoryEntry,
    EpisodicMemoryResponse,
    FeedbackRequest,
    FeedbackResponse,
    HealthResponse,
    ProceduralMemoryResponse,
    RunMetricsEntry,
    RunMetricsListResponse,
    RunRequest,
    RunResponse,
    RuntimeMetrics,
    SemanticMemoryResponse,
    UserConfigResponse,
    UserConfigUpdateRequest,
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


def _current_pipeline_node(graph_state: Any) -> Optional[str]:
    """Live cursor: first checkpoint next node, or hitl_node when interrupted."""
    next_nodes = tuple(graph_state.next or ())
    if next_nodes:
        return str(next_nodes[0])
    if _is_pending_hitl(graph_state):
        return "hitl_node"
    return None


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


def _thread_id_from_briefing_runs(
    run_id: str, user_id: Optional[str] = None
) -> Optional[str]:
    """Resolve thread_id from persisted briefing_runs.id (post-HITL only)."""
    run_uuid = _as_uuid_or_none(run_id)
    if run_uuid is None:
        return None
    try:
        with pool.connection() as conn:
            with conn.cursor() as cur:
                if user_id:
                    cur.execute(
                        """
                        SELECT thread_id FROM briefing_runs
                        WHERE id = %s AND user_id = %s
                        """,
                        (str(run_uuid), str(user_id)),
                    )
                else:
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


def _user_needs_onboarding(user_id: str) -> bool:
    """True when no user_configs row exists for this auth user."""
    try:
        with pool.connection() as conn:
            row = _fetch_user_config_row_db(conn, user_id)
            return row is None
    except Exception:
        logger.exception("Failed to check onboarding state for user_id=%s", user_id)
        return True


def _auth_response_from_session(session: dict[str, Any]) -> AuthResponse:
    user_id = str(session["user_id"])
    return AuthResponse(
        access_token=str(session["access_token"]),
        token_type="bearer",
        expires_in=(
            int(session["expires_in"])
            if session.get("expires_in") is not None
            else None
        ),
        user=AuthUserSchema(
            id=user_id,
            email=str(session.get("email") or ""),
        ),
        needs_onboarding=_user_needs_onboarding(user_id),
    )


def _briefing_from_checkpoint(
    run_id: str,
    thread_id: str,
    user_id: Optional[str] = None,
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
    if user_id is not None:
        owner = str(values.get("user_id") or "")
        # Reject only when the checkpoint carries a different owner.
        if owner and owner != str(user_id):
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


def _briefing_from_db(
    run_id: str, user_id: Optional[str] = None
) -> BriefingResponse:
    """Serve completed/rejected briefing from briefing_runs + related tables.

    Single round-trip: run row + items (json_agg) + latest metrics (LATERAL).
    """
    run_uuid = _as_uuid_or_none(run_id)
    if run_uuid is None:
        raise HTTPException(status_code=404, detail="Briefing not found")

    uid = str(user_id) if user_id else None

    with pool.connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT
                    br.id,
                    br.thread_id,
                    br.status,
                    br.run_at,
                    br.final_briefing,
                    br.graph_version,
                    m.run_duration_seconds,
                    m.tokens_used,
                    m.estimated_cost_usd,
                    m.findings_retrieved,
                    m.findings_dropped_freshness,
                    m.findings_dropped_scope,
                    m.findings_dropped_dedup,
                    m.graph_version AS metrics_graph_version,
                    COALESCE(items.items_json, '[]'::json) AS items
                FROM briefing_runs br
                LEFT JOIN LATERAL (
                    SELECT
                        run_duration_seconds,
                        tokens_used,
                        estimated_cost_usd,
                        findings_retrieved,
                        findings_dropped_freshness,
                        findings_dropped_scope,
                        findings_dropped_dedup,
                        graph_version
                    FROM agent_run_metrics
                    WHERE briefing_run_id = br.id
                    ORDER BY run_at DESC
                    LIMIT 1
                ) m ON TRUE
                LEFT JOIN LATERAL (
                    SELECT json_agg(
                        json_build_object(
                            'id', bi.id::text,
                            'title', COALESCE(bi.title, ''),
                            'summary', COALESCE(bi.summary, ''),
                            'source_url', COALESCE(bi.source_url, ''),
                            'source_name', COALESCE(bi.source_name, ''),
                            'category', COALESCE(bi.category, ''),
                            'confidence_score', COALESCE(bi.confidence_score, 0),
                            'entities', COALESCE(bi.entities, '{}'::jsonb),
                            'feedback', bi.feedback,
                            'feedback_reason', bi.feedback_reason,
                            'feedback_at', bi.feedback_at
                        )
                        ORDER BY bi.confidence_score DESC NULLS LAST
                    ) AS items_json
                    FROM briefing_items bi
                    WHERE bi.briefing_run_id = br.id
                      AND (%s::uuid IS NULL OR bi.user_id = %s::uuid)
                ) items ON TRUE
                WHERE br.id = %s
                  AND (%s::uuid IS NULL OR br.user_id = %s::uuid)
                """,
                (uid, uid, str(run_uuid), uid, uid),
            )
            row = cur.fetchone()
            if not row:
                raise HTTPException(status_code=404, detail="Briefing not found")

            raw_items = row.get("items")
            if isinstance(raw_items, str):
                try:
                    raw_items = json.loads(raw_items)
                except json.JSONDecodeError:
                    raw_items = []
            if not isinstance(raw_items, list):
                raw_items = []

            items: list[BriefingItemSchema] = []
            for item in raw_items:
                if not isinstance(item, dict):
                    continue
                fb = item.get("feedback")
                feedback_val = fb if fb in ("useful", "not_relevant") else None
                entities = item.get("entities")
                items.append(
                    BriefingItemSchema(
                        id=str(item.get("id") or ""),
                        title=str(item.get("title") or ""),
                        summary=str(item.get("summary") or ""),
                        source_url=str(item.get("source_url") or ""),
                        source_name=str(item.get("source_name") or ""),
                        category=str(item.get("category") or ""),
                        confidence_score=float(item.get("confidence_score") or 0.0),
                        entities=entities if isinstance(entities, dict) else {},
                        feedback=feedback_val,
                        feedback_reason=item.get("feedback_reason"),
                        feedback_at=_feedback_at_str(item.get("feedback_at")),
                    )
                )

            metrics = None
            has_metrics = any(
                row.get(key) is not None
                for key in (
                    "run_duration_seconds",
                    "tokens_used",
                    "estimated_cost_usd",
                    "findings_retrieved",
                    "findings_dropped_freshness",
                    "findings_dropped_scope",
                    "findings_dropped_dedup",
                    "metrics_graph_version",
                )
            )
            if has_metrics:
                metrics = RuntimeMetrics(
                    run_duration_seconds=float(row.get("run_duration_seconds") or 0.0),
                    tokens_used=int(row.get("tokens_used") or 0),
                    estimated_cost_usd=float(row.get("estimated_cost_usd") or 0.0),
                    findings_retrieved=int(row.get("findings_retrieved") or 0),
                    findings_dropped_freshness=int(
                        row.get("findings_dropped_freshness") or 0
                    ),
                    findings_dropped_scope=int(row.get("findings_dropped_scope") or 0),
                    findings_dropped_dedup=int(row.get("findings_dropped_dedup") or 0),
                    graph_version=str(
                        row.get("metrics_graph_version")
                        or row.get("graph_version")
                        or ""
                    ),
                )

            final_text = row.get("final_briefing") or ""
            run_at = row.get("run_at")
            created_at = (
                run_at.isoformat()
                if run_at is not None and hasattr(run_at, "isoformat")
                else datetime.now(timezone.utc).isoformat()
            )

            return BriefingResponse(
                run_id=str(row["id"]),
                thread_id=str(row.get("thread_id") or ""),
                status=str(row.get("status") or ""),
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


def _normalize_email(value: str) -> str:
    email = (value or "").strip().lower()
    if not email or "@" not in email or "." not in email.split("@")[-1]:
        raise HTTPException(status_code=400, detail="Invalid email")
    if len(email) > 320:
        raise HTTPException(status_code=400, detail="Invalid email")
    return email


@router.post("/auth/signup", response_model=AuthResponse)
def auth_signup(body: AuthCredentialsRequest) -> AuthResponse:
    """Create an account via Supabase Auth (email/password)."""
    email = _normalize_email(body.email)
    password = body.password or ""
    if len(password) < 6:
        raise HTTPException(
            status_code=400,
            detail="Password must be at least 6 characters",
        )
    session = signup_with_password(email, password)
    return _auth_response_from_session(session)


@router.post("/auth/login", response_model=AuthResponse)
def auth_login(body: AuthCredentialsRequest) -> AuthResponse:
    """Sign in via Supabase Auth (email/password)."""
    email = _normalize_email(body.email)
    password = body.password or ""
    if not password:
        raise HTTPException(status_code=400, detail="Password is required")
    session = login_with_password(email, password)
    return _auth_response_from_session(session)


def _status_and_node_from_checkpoint(graph_state: Any) -> tuple[str, Optional[str]]:
    status = "idle"
    if graph_state.next:
        if "hitl_node" in graph_state.next:
            status = "pending_hitl"
        else:
            status = "running"
    elif _is_pending_hitl(graph_state):
        status = "pending_hitl"
    node = _current_pipeline_node(graph_state) if status != "idle" else None
    return status, node


def _status_for_pipeline_node(node: str) -> str:
    return "pending_hitl" if node == "hitl_node" else "running"


@router.get("/agent/status", response_model=AgentStatusResponse)
def get_agent_status(
    thread_id: str = "run_001",
    _user: AuthUser = Depends(get_current_user),
) -> AgentStatusResponse:
    """Check the current status of the agent for a given thread."""
    try:
        config = {"configurable": {"thread_id": thread_id}}
        graph_state = graph.get_state(config)

        live = get_live_node(thread_id)
        if live:
            status = _status_for_pipeline_node(live)
            node = live
        else:
            ls_node = lookup_langsmith_pipeline_node(thread_id)
            if ls_node:
                status = _status_for_pipeline_node(ls_node)
                node = ls_node
            else:
                status, node = _status_and_node_from_checkpoint(graph_state)

        # Scope non-idle status to the authenticated user's run when known.
        values = getattr(graph_state, "values", None)
        if isinstance(values, dict):
            owner = str(values.get("user_id") or "")
            if owner and owner != _user.user_id and status != "idle":
                return AgentStatusResponse(status="idle", thread_id=thread_id)

        stage = pipeline_stage(node)
        return AgentStatusResponse(status=status, thread_id=thread_id, **stage)
    except Exception as exc:
        logger.exception("Failed to get agent status")
        raise HTTPException(status_code=500, detail=str(exc))


@router.get("/briefings", response_model=BriefingListResponse)
def list_briefings(
    limit: int = Query(10, ge=1, le=100),
    user: AuthUser = Depends(get_current_user),
) -> BriefingListResponse:
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
                                 AND bi.user_id = br.user_id
                           ) AS item_count
                    FROM briefing_runs br
                    WHERE br.user_id = %s
                    ORDER BY br.run_at DESC
                    LIMIT %s
                    """,
                    (user.user_id, limit),
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
def list_run_metrics(
    limit: int = Query(5, ge=1, le=50),
    user: AuthUser = Depends(get_current_user),
) -> RunMetricsListResponse:
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
                    WHERE m.user_id = %s
                    ORDER BY m.run_at DESC
                    LIMIT %s
                    """,
                    (user.user_id, limit),
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
    user: AuthUser = Depends(get_current_user),
) -> BriefingResponse:
    """Get briefing detail.

    Saved (completed/rejected) → briefing_runs join (no checkpoint / graph).
    pending_hitl → checkpointed LangGraph state via thread_id when no DB row.
    """
    try:
        # DB-first: avoid PostgresSaver get_state on every saved open (was ~7–8s).
        try:
            return _briefing_from_db(run_id, user_id=user.user_id)
        except HTTPException as db_exc:
            if db_exc.status_code != 404:
                raise
            if not thread_id:
                raise

        pending = _briefing_from_checkpoint(
            run_id, thread_id, user_id=user.user_id
        )
        if pending is not None:
            return pending
        raise HTTPException(status_code=404, detail="Briefing not found")
    except HTTPException:
        raise
    except Exception as exc:
        logger.exception("Failed to get briefing detail")
        raise HTTPException(status_code=500, detail=str(exc))


@router.post("/items/{item_id}/feedback", response_model=FeedbackResponse)
def submit_item_feedback(
    item_id: str,
    body: FeedbackRequest,
    user: AuthUser = Depends(get_current_user),
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
                        WHERE id = %s AND user_id = %s
                        """,
                        (str(item_uuid), user.user_id),
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
    user: AuthUser = Depends(get_current_user),
) -> RunResponse:
    """Resume the graph with 'approve' action for a given run."""
    return _resume_hitl(
        run_id, "approve", thread_id=thread_id, user_id=user.user_id
    )


@router.post("/briefings/{run_id}/reject", response_model=RunResponse)
def reject_briefing(
    run_id: str,
    thread_id: Optional[str] = Query(
        None,
        description="LangGraph thread_id from POST /run; required during pending_hitl.",
    ),
    user: AuthUser = Depends(get_current_user),
) -> RunResponse:
    """Resume the graph with 'reject' action for a given run."""
    return _resume_hitl(
        run_id, "reject", thread_id=thread_id, user_id=user.user_id
    )


def _resume_hitl(
    run_id: str,
    action: str,
    edits: dict | None = None,
    thread_id: Optional[str] = None,
    user_id: Optional[str] = None,
) -> RunResponse:
    """Helper to resume the graph from HITL interrupt.

    Matches scripts/test_hitl.py: graph.invoke(Command(resume=...), config).
    Do not pass a plain dict — LangGraph treats that as a SignalState update.
    """
    try:
        tid = thread_id or _thread_id_from_briefing_runs(run_id, user_id=user_id)
        if not tid:
            raise HTTPException(status_code=404, detail="Run not found")

        config = graph_invoke_config(tid, user_id=user_id or "")
        if user_id:
            try:
                graph_state = graph.get_state(config)
                values = getattr(graph_state, "values", None) or {}
                owner = str(values.get("user_id") or "")
                if owner and owner != str(user_id):
                    raise HTTPException(status_code=404, detail="Run not found")
            except HTTPException:
                raise
            except Exception:
                # If checkpoint lookup fails, fall through to invoke path.
                pass

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


_EMBEDDING_KEYS = frozenset(
    {"embedding", "embeddings", "vector", "vectors", "embedding_vector"}
)


def _strip_embeddings(value: Any) -> Any:
    """Recursively drop embedding / vector payloads from memory responses."""
    if isinstance(value, dict):
        return {
            k: _strip_embeddings(v)
            for k, v in value.items()
            if k not in _EMBEDDING_KEYS
        }
    if isinstance(value, list):
        return [_strip_embeddings(v) for v in value]
    return value


def _get_store():
    """Reuse graph PostgresStore — never open a second store."""
    from agent.graph import _postgres_store

    if _postgres_store is None:
        raise RuntimeError("PostgresStore unavailable")
    return _postgres_store


@router.get("/config", response_model=UserConfigResponse)
def get_config(
    user: AuthUser = Depends(get_current_user),
) -> UserConfigResponse:
    """Read existing user_configs (+ read-only graph_version / max findings)."""
    try:
        return _build_config_response(user.user_id)
    except HTTPException:
        raise
    except Exception as exc:
        logger.exception("Failed to load config")
        raise HTTPException(status_code=500, detail=str(exc)) from exc


def _resolve_config_user_uuid(conn, user_id: str) -> Any:
    """Require a real auth.users UUID from the validated JWT subject."""
    import uuid as uuid_mod

    raw = (user_id or "").strip()
    try:
        return uuid_mod.UUID(raw)
    except (ValueError, TypeError, AttributeError) as exc:
        raise HTTPException(
            status_code=401,
            detail="Authenticated user id is invalid",
        ) from exc


def _try_resolve_config_user_uuid(conn, user_id: str) -> Any | None:
    """Soft resolve for GET — invalid UUID means defaults, not a 500."""
    try:
        return _resolve_config_user_uuid(conn, user_id)
    except HTTPException:
        return None


def _row_dict_to_config_response(
    row: dict[str, Any] | None,
    *,
    display_user_id: str,
    from_defaults: bool,
) -> UserConfigResponse:
    import os

    from agent.nodes.config_loader import _DEFAULT_USER_CONFIG
    from agent.state import MAX_FINDINGS_PER_RUN

    if row is None:
        cfg = {**_DEFAULT_USER_CONFIG, "user_id": display_user_id}
        from_defaults = True
    else:
        cfg = {
            "user_id": str(row["user_id"])
            if row.get("user_id") is not None
            else display_user_id,
            "keywords": list(row["keywords"])
            if row.get("keywords") is not None
            else list(_DEFAULT_USER_CONFIG["keywords"]),
            "verticals": list(row["verticals"])
            if row.get("verticals") is not None
            else list(_DEFAULT_USER_CONFIG["verticals"]),
            "stage_filter": list(row["stage_filter"])
            if row.get("stage_filter") is not None
            else list(_DEFAULT_USER_CONFIG["stage_filter"]),
            "delivery_email": row["delivery_email"]
            if row.get("delivery_email") is not None
            else _DEFAULT_USER_CONFIG["delivery_email"],
            "schedule_freq": row["schedule_freq"]
            if row.get("schedule_freq") is not None
            else _DEFAULT_USER_CONFIG["schedule_freq"],
        }

    return UserConfigResponse(
        user_id=str(cfg.get("user_id") or display_user_id),
        keywords=list(cfg.get("keywords") or []),
        verticals=list(cfg.get("verticals") or []),
        stage_filter=list(cfg.get("stage_filter") or []),
        schedule_freq=str(cfg.get("schedule_freq") or "weekly"),
        delivery_email=str(cfg.get("delivery_email") or ""),
        graph_version=os.getenv("GRAPH_VERSION", "1.0"),
        max_findings_per_run=int(MAX_FINDINGS_PER_RUN),
        from_defaults=from_defaults,
    )


def _fetch_user_config_row_db(conn, user_uuid: Any) -> dict[str, Any] | None:
    """Read user_configs by auth UUID via the shared pool (not REST / user_001)."""
    with conn.cursor() as cur:
        cur.execute(
            """
            SELECT user_id, keywords, verticals, stage_filter,
                   schedule_freq, delivery_email
            FROM user_configs
            WHERE user_id = %s
            ORDER BY updated_at DESC NULLS LAST
            LIMIT 1
            """,
            (str(user_uuid),),
        )
        row = cur.fetchone()
    if not row:
        return None
    return dict(row) if not isinstance(row, dict) else row


def _build_config_response(user_id: str) -> UserConfigResponse:
    """Load config from Postgres using the same UUID key as PUT /config."""
    with pool.connection() as conn:
        user_uuid = _try_resolve_config_user_uuid(conn, user_id)
        if user_uuid is None:
            return _row_dict_to_config_response(
                None, display_user_id=user_id, from_defaults=True
            )
        row = _fetch_user_config_row_db(conn, user_uuid)
        return _row_dict_to_config_response(
            row,
            display_user_id=str(user_uuid),
            from_defaults=row is None,
        )


def _normalize_delivery_email(value: str) -> str:
    email = (value or "").strip()
    if not email or "@" not in email or "." not in email.split("@")[-1]:
        raise HTTPException(status_code=400, detail="Invalid delivery_email")
    if len(email) > 320:
        raise HTTPException(status_code=400, detail="Invalid delivery_email")
    return email


# Signal scope ends at Series B — reject Series C and unknown stages.
_ALLOWED_STAGE_FILTER = {
    "seed": "Seed",
    "series a": "Series A",
    "series_a": "Series A",
    "seriesa": "Series A",
    "series b": "Series B",
    "series_b": "Series B",
    "seriesb": "Series B",
}


def _normalize_stage_filter(values: list[str]) -> list[str]:
    if not values:
        raise HTTPException(
            status_code=400,
            detail="stage_filter must include at least one of: Seed, Series A, Series B",
        )
    normalized: list[str] = []
    seen: set[str] = set()
    for raw in values:
        key = str(raw or "").strip().lower().replace("-", " ")
        key = " ".join(key.split())
        canonical = _ALLOWED_STAGE_FILTER.get(key)
        if canonical is None:
            raise HTTPException(
                status_code=400,
                detail="stage_filter supports only Seed, Series A, and Series B",
            )
        if canonical not in seen:
            seen.add(canonical)
            normalized.append(canonical)
    return normalized


@router.put("/config", response_model=UserConfigResponse)
def update_config(
    body: UserConfigUpdateRequest,
    user: AuthUser = Depends(get_current_user),
) -> UserConfigResponse:
    """Update config / complete onboarding. Creates user_configs row when missing."""
    from agent.nodes.config_loader import _DEFAULT_USER_CONFIG

    has_any = any(
        [
            body.delivery_email is not None,
            body.keywords is not None,
            body.verticals is not None,
            body.stage_filter is not None,
            body.schedule_freq is not None,
        ]
    )
    if not has_any:
        raise HTTPException(status_code=400, detail="No config fields provided")

    email = (
        _normalize_delivery_email(body.delivery_email)
        if body.delivery_email is not None
        else None
    )

    try:
        with pool.connection() as conn:
            user_uuid = _resolve_config_user_uuid(conn, user.user_id)
            now = datetime.now(timezone.utc)
            existing = _fetch_user_config_row_db(conn, user_uuid)

            keywords = (
                list(body.keywords)
                if body.keywords is not None
                else (
                    list(existing["keywords"])
                    if existing and existing.get("keywords") is not None
                    else list(_DEFAULT_USER_CONFIG["keywords"])
                )
            )
            verticals = (
                list(body.verticals)
                if body.verticals is not None
                else (
                    list(existing["verticals"])
                    if existing and existing.get("verticals") is not None
                    else list(_DEFAULT_USER_CONFIG["verticals"])
                )
            )
            stage_filter = (
                _normalize_stage_filter(list(body.stage_filter))
                if body.stage_filter is not None
                else (
                    list(existing["stage_filter"])
                    if existing and existing.get("stage_filter") is not None
                    else list(_DEFAULT_USER_CONFIG["stage_filter"])
                )
            )
            schedule_freq = (
                str(body.schedule_freq)
                if body.schedule_freq is not None
                else (
                    str(existing["schedule_freq"])
                    if existing and existing.get("schedule_freq") is not None
                    else str(_DEFAULT_USER_CONFIG["schedule_freq"])
                )
            )
            delivery_email = (
                email
                if email is not None
                else (
                    str(existing["delivery_email"])
                    if existing and existing.get("delivery_email") is not None
                    else str(_DEFAULT_USER_CONFIG["delivery_email"])
                )
            )
            if not delivery_email:
                raise HTTPException(
                    status_code=400,
                    detail="delivery_email is required to create configuration",
                )

            with conn.cursor() as cur:
                cur.execute(
                    """
                    UPDATE user_configs
                    SET delivery_email = %s,
                        keywords = %s,
                        verticals = %s,
                        stage_filter = %s,
                        schedule_freq = %s,
                        updated_at = %s
                    WHERE user_id = %s
                    RETURNING user_id, keywords, verticals, stage_filter,
                              schedule_freq, delivery_email
                    """,
                    (
                        delivery_email,
                        keywords,
                        verticals,
                        stage_filter,
                        schedule_freq,
                        now,
                        str(user_uuid),
                    ),
                )
                updated = cur.fetchone()
                if updated is None:
                    cur.execute(
                        """
                        INSERT INTO user_configs (
                            user_id, keywords, verticals, stage_filter,
                            schedule_freq, delivery_email, created_at, updated_at
                        ) VALUES (
                            %s, %s, %s, %s, %s, %s, %s, %s
                        )
                        RETURNING user_id, keywords, verticals, stage_filter,
                                  schedule_freq, delivery_email
                        """,
                        (
                            str(user_uuid),
                            keywords,
                            verticals,
                            stage_filter,
                            schedule_freq,
                            delivery_email,
                            now,
                            now,
                        ),
                    )
                    updated = cur.fetchone()
                if updated is None:
                    raise RuntimeError(
                        "user_configs write returned no row — configuration not persisted"
                    )
            conn.commit()

        return _build_config_response(user.user_id)
    except HTTPException:
        raise
    except Exception as exc:
        logger.exception("Failed to update config")
        raise HTTPException(status_code=500, detail=str(exc)) from exc


def _episode_title(value: dict[str, Any], key: str) -> str:
    titles = value.get("item_titles") or []
    if isinstance(titles, list) and titles:
        first = str(titles[0]).strip()
        if first:
            return first
    run_id = str(value.get("run_id") or key or "").strip()
    if run_id:
        return f"Run {run_id[:8]}"
    return "Untitled episode"


def _episode_source(value: dict[str, Any]) -> Optional[str]:
    urls = value.get("source_urls") or []
    if not isinstance(urls, list) or not urls:
        return "episodic"
    # Derive a short source hint from the first URL host when present.
    try:
        from urllib.parse import urlparse

        host = urlparse(str(urls[0])).netloc or ""
        if host.startswith("www."):
            host = host[4:]
        if host:
            extra = len(urls) - 1
            return host if extra <= 0 else f"{host} (+{extra})"
    except Exception:
        pass
    return "episodic"


@router.get("/memory/semantic", response_model=SemanticMemoryResponse)
def get_semantic_memory(
    user: AuthUser = Depends(get_current_user),
) -> SemanticMemoryResponse:
    """Read-only semantic memory inspector (no embeddings)."""
    from agent.nodes.config_loader import _SEMANTIC_KEY

    try:
        store = _get_store()
        item = store.get(("user", user.user_id, "semantic"), _SEMANTIC_KEY)
        if item is None or not isinstance(getattr(item, "value", None), dict):
            return SemanticMemoryResponse(memory={}, updated_at=None, empty=True)

        memory = _strip_embeddings(item.value)
        if not isinstance(memory, dict):
            memory = {}

        updated_at_str = None
        created = getattr(item, "created_at", None)
        if created is not None:
            updated_at_str = (
                created.isoformat()
                if hasattr(created, "isoformat")
                else str(created)
            )

        # Empty when no meaningful list content
        has_content = any(
            isinstance(memory.get(k), list) and len(memory.get(k) or []) > 0
            for k in ("seen_urls", "seen_titles", "seen_company_dates")
        ) or any(
            v not in (None, "", [], {})
            for k, v in memory.items()
            if k not in ("seen_urls", "seen_titles", "seen_company_dates")
        )
        return SemanticMemoryResponse(
            memory=memory,
            updated_at=updated_at_str,
            empty=not has_content,
        )
    except HTTPException:
        raise
    except Exception as exc:
        logger.exception("Failed to load semantic memory")
        raise HTTPException(status_code=500, detail=str(exc)) from exc


@router.get("/memory/episodic", response_model=EpisodicMemoryResponse)
def get_episodic_memory(
    limit: int = Query(50, ge=1, le=200),
    user: AuthUser = Depends(get_current_user),
) -> EpisodicMemoryResponse:
    """Read-only episodic memory inspector (no embeddings)."""
    try:
        store = _get_store()
        items = list(store.search(("user", user.user_id, "episodic"), limit=limit))
        episodes: list[EpisodicMemoryEntry] = []
        for item in items:
            raw = item.value if isinstance(getattr(item, "value", None), dict) else {}
            value = _strip_embeddings(raw)
            if not isinstance(value, dict):
                value = {}
            key = str(getattr(item, "key", "") or value.get("run_id") or "")
            titles = value.get("item_titles") or []
            urls = value.get("source_urls") or []
            companies = value.get("company_names_normalized") or []
            episodes.append(
                EpisodicMemoryEntry(
                    key=key,
                    run_id=str(value.get("run_id") or key),
                    thread_id=str(value.get("thread_id") or ""),
                    title=_episode_title(value, key),
                    timestamp=(
                        str(value["timestamp"])
                        if value.get("timestamp") is not None
                        else None
                    ),
                    source=_episode_source(value),
                    confidence=None,
                    summary=(
                        str(value["briefing_summary"])
                        if value.get("briefing_summary") is not None
                        else None
                    ),
                    item_titles=[str(t) for t in titles] if isinstance(titles, list) else [],
                    source_urls=[str(u) for u in urls] if isinstance(urls, list) else [],
                    company_names_normalized=(
                        [str(c) for c in companies] if isinstance(companies, list) else []
                    ),
                )
            )
        # Newest first when timestamps exist
        episodes.sort(
            key=lambda e: e.timestamp or "",
            reverse=True,
        )
        return EpisodicMemoryResponse(episodes=episodes)
    except HTTPException:
        raise
    except Exception as exc:
        logger.exception("Failed to load episodic memory")
        raise HTTPException(status_code=500, detail=str(exc)) from exc


@router.get("/memory/procedural", response_model=ProceduralMemoryResponse)
def get_procedural_memory(
    user: AuthUser = Depends(get_current_user),
) -> ProceduralMemoryResponse:
    """Read-only procedural preference profile (no LLM, no embeddings)."""
    from agent.nodes.config_loader import _PROCEDURAL_KEY

    try:
        store = _get_store()
        item = store.get(("user", user.user_id, "procedural"), _PROCEDURAL_KEY)
        if item is None or not isinstance(getattr(item, "value", None), dict):
            return ProceduralMemoryResponse(preferences={}, updated_at=None, empty=True)

        prefs = _strip_embeddings(item.value)
        if not isinstance(prefs, dict):
            prefs = {}
        # Never expose wall-clock metadata invented for the API — only pass through
        # if the stored profile already carries an updated_at (currently it does not).
        updated_at = prefs.pop("last_updated", None) or prefs.pop("updated_at", None)
        updated_at_str = str(updated_at) if updated_at is not None else None
        # Prefer Store item created_at when available
        created = getattr(item, "created_at", None)
        if updated_at_str is None and created is not None:
            updated_at_str = (
                created.isoformat()
                if hasattr(created, "isoformat")
                else str(created)
            )

        empty = len(prefs) == 0
        return ProceduralMemoryResponse(
            preferences=prefs,
            updated_at=updated_at_str,
            empty=empty,
        )
    except HTTPException:
        raise
    except Exception as exc:
        logger.exception("Failed to load procedural memory")
        raise HTTPException(status_code=500, detail=str(exc)) from exc


@router.post("/run", response_model=RunResponse)
def run_pipeline(
    request: RunRequest | None = None,
    user: AuthUser = Depends(get_current_user),
) -> RunResponse:
    body = request or RunRequest()
    # Identity always comes from the validated JWT — never from the request body.
    body = body.model_copy(update={"user_id": user.user_id})
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
