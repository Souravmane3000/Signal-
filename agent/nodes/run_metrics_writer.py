"""Run Metrics Writer — Phase 2 Supabase persistence (SIG-021B).

Side-effect only: INSERT agent_run_metrics + UPDATE briefing_runs.graph_version.
Does not modify SignalState. Does not call an LLM. Does not write memory.
"""

from __future__ import annotations

import json
import uuid
from typing import Any

from agent.state import SignalState

# Dev fallback when state.user_id is still the Phase-1 string (e.g. "user_001")
# before FastAPI/auth wires real auth.users UUIDs into state.
_FALLBACK_AUTH_EMAIL = "signal-builder@local.test"


def _get_pool():
    """Reuse the ConnectionPool from SIG-P2-002 — do not open a second connection."""
    from agent.graph import _pool

    if _pool is None:
        raise RuntimeError(
            "Postgres ConnectionPool unavailable (SIG-P2-002 not complete)."
        )
    return _pool


def _as_uuid(value: str, *, field: str) -> uuid.UUID:
    try:
        return uuid.UUID(str(value))
    except (ValueError, TypeError, AttributeError) as exc:
        raise ValueError(f"{field} must be a UUID, got {value!r}") from exc


def _resolve_user_id(conn, state: SignalState) -> uuid.UUID:
    raw = (state.get("user_id") or "").strip()
    if raw:
        try:
            return uuid.UUID(raw)
        except ValueError:
            pass
    row = conn.execute(
        "SELECT id FROM auth.users WHERE email = %s LIMIT 1",
        (_FALLBACK_AUTH_EMAIL,),
    ).fetchone()
    if row:
        raw_id = row["id"] if isinstance(row, dict) else row[0]
        if raw_id:
            return raw_id if isinstance(raw_id, uuid.UUID) else uuid.UUID(str(raw_id))
    raise RuntimeError(
        "user_id must be an auth.users UUID for agent_run_metrics INSERT "
        f"(SIG-021B). Got {raw!r}; no fallback user {_FALLBACK_AUTH_EMAIL!r}."
    )


def _run_status(state: SignalState) -> str:
    delivery = state.get("delivery_status")
    if delivery == "rejected":
        return "rejected"
    if state.get("error"):
        return "failed"
    if delivery == "failed":
        return "failed"
    return "completed"


def _build_metrics(state: SignalState) -> dict[str, Any]:
    source_failures = state.get("source_failures")
    if source_failures is None:
        raise RuntimeError(
            'state["source_failures"] missing — research pipeline state error '
            "(SIG-021 stop condition)."
        )
    graph_version = state.get("graph_version")
    if graph_version is None:
        raise RuntimeError(
            'state["graph_version"] missing — config loader error '
            "(SIG-021 stop condition)."
        )
    return {
        "run_id": state.get("run_id", ""),
        "graph_version": graph_version,
        "sources_queried": list(state.get("sources_queried") or []),
        "findings_retrieved": int(state.get("findings_retrieved") or 0),
        "findings_dropped_freshness": int(
            state.get("findings_dropped_freshness") or 0
        ),
        "findings_dropped_scope": int(state.get("findings_dropped_scope") or 0),
        "findings_dropped_dedup": int(state.get("findings_dropped_dedup") or 0),
        "findings_in_briefing": len(state.get("new_findings") or []),
        "tokens_used": int(state.get("tokens_used") or 0),
        "estimated_cost_usd": float(state.get("estimated_cost_usd") or 0.0),
        "run_duration_seconds": float(state.get("run_duration_seconds") or 0.0),
        "source_health": dict(source_failures),
    }


def _persist_metrics(state: SignalState, metrics: dict[str, Any]) -> None:
    """INSERT agent_run_metrics and UPDATE briefing_runs.graph_version.

    Uses the shared pool. Does not swallow DB errors.
    """
    pool = _get_pool()
    run_id = _as_uuid(metrics["run_id"], field="run_id")
    status = _run_status(state)
    was_approved = status != "rejected"
    thread_id = state.get("thread_id") or ""
    final_briefing = state.get("briefing_final") or ""
    run_config = state.get("run_config_snapshot") or {}

    with pool.connection() as conn:
        user_id = _resolve_user_id(conn, state)
        # Ensure parent briefing_runs row exists (FK), then stamp graph_version.
        conn.execute(
            """
            INSERT INTO briefing_runs (
                id, user_id, status, graph_version, thread_id,
                final_briefing, was_approved, run_config
            ) VALUES (
                %s, %s, %s, %s, %s, %s, %s, %s::jsonb
            )
            ON CONFLICT (id) DO UPDATE SET
                graph_version = EXCLUDED.graph_version,
                status = EXCLUDED.status,
                thread_id = EXCLUDED.thread_id,
                final_briefing = EXCLUDED.final_briefing,
                was_approved = EXCLUDED.was_approved,
                run_config = EXCLUDED.run_config
            """,
            (
                str(run_id),
                str(user_id),
                status,
                metrics["graph_version"],
                thread_id,
                final_briefing,
                was_approved,
                json.dumps(run_config),
            ),
        )
        conn.execute(
            """
            UPDATE briefing_runs
            SET graph_version = %s
            WHERE id = %s
            """,
            (metrics["graph_version"], str(run_id)),
        )
        conn.execute(
            """
            INSERT INTO agent_run_metrics (
                briefing_run_id,
                user_id,
                sources_queried,
                findings_retrieved,
                findings_dropped_freshness,
                findings_dropped_scope,
                findings_dropped_dedup,
                findings_in_briefing,
                tokens_used,
                estimated_cost_usd,
                run_duration_seconds,
                graph_version,
                source_health
            ) VALUES (
                %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s::jsonb
            )
            """,
            (
                str(run_id),
                str(user_id),
                metrics["sources_queried"],
                metrics["findings_retrieved"],
                metrics["findings_dropped_freshness"],
                metrics["findings_dropped_scope"],
                metrics["findings_dropped_dedup"],
                metrics["findings_in_briefing"],
                metrics["tokens_used"],
                metrics["estimated_cost_usd"],
                metrics["run_duration_seconds"],
                metrics["graph_version"],
                json.dumps(metrics["source_health"]),
            ),
        )
        conn.commit()


def run_metrics_writer(state: SignalState) -> dict:
    metrics = _build_metrics(state)
    source_health = metrics["source_health"]

    for source, failed in source_health.items():
        if failed:
            print(f"WARNING: {source} failed this run")

    try:
        _persist_metrics(state, metrics)
    except Exception as exc:
        print(f"ERROR: run_metrics_writer persistence failed: {exc}")
        # Do not swallow — SIG-021B stop condition / surface node failure.
        raise

    print(
        f"Run metrics written for run {metrics['run_id']} "
        f"(graph_version={metrics['graph_version']})"
    )
    return {}
