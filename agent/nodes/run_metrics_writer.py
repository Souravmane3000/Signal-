"""Run Metrics Writer — Phase 2 Supabase persistence (SIG-021B).

Side-effect only: INSERT briefing_runs, briefing_items, agent_run_metrics.
Does not modify SignalState. Does not call an LLM. Does not write memory.
"""

from __future__ import annotations

import json
import logging
import os
import uuid
from typing import Any

from agent.state import SignalState

logger = logging.getLogger(__name__)

# Dev fallback when state.user_id is still the Phase-1 string (e.g. "user_001")
# before FastAPI/auth wires real auth.users UUIDs into state.
_FALLBACK_AUTH_EMAIL = "signal-builder@local.test"


def _get_pool():
    """Reuse the ConnectionPool from SIG-P2-002 — do not open a second connection."""
    from agent.graph import pool

    if pool is None:
        raise RuntimeError(
            "Postgres ConnectionPool unavailable (SIG-P2-002 not complete)."
        )
    return pool


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
        "findings_in_briefing": len(state.get("briefing_items") or []),
        "tokens_used": int(state.get("tokens_used") or 0),
        "estimated_cost_usd": float(state.get("estimated_cost_usd") or 0.0),
        "run_duration_seconds": float(state.get("run_duration_seconds") or 0.0),
        "source_health": dict(source_failures),
    }


def _pgvector_literal(embedding: Any) -> str | None:
    """Format a float list for Postgres vector(1536); None if unavailable."""
    if not isinstance(embedding, (list, tuple)) or not embedding:
        return None
    try:
        return "[" + ",".join(str(float(x)) for x in embedding) + "]"
    except (TypeError, ValueError):
        return None


def _embedding_lookup(state: SignalState) -> dict[tuple[str, str], Any]:
    """Map (title, source_url) → embedding from new_findings (hybrid_dedup)."""
    lookup: dict[tuple[str, str], Any] = {}
    for finding in state.get("new_findings") or []:
        if not isinstance(finding, dict):
            continue
        key = (str(finding.get("title") or ""), str(finding.get("source_url") or ""))
        if finding.get("embedding") is not None:
            lookup[key] = finding["embedding"]
    return lookup


def _persist_briefing_items(conn, state: SignalState, run_id: uuid.UUID, user_id: uuid.UUID) -> int:
    """INSERT one briefing_items row per state briefing_item. Returns row count.

    Owns the DB write for findings after HITL. Synthesis only populates graph
    state; hybrid_dedup preserves embeddings on new_findings for this INSERT.
    """
    items = state.get("briefing_items") or []
    embeddings = _embedding_lookup(state)

    # Idempotent on metrics re-run for the same briefing_run_id.
    conn.execute(
        "DELETE FROM briefing_items WHERE briefing_run_id = %s",
        (str(run_id),),
    )

    written = 0
    for item in items:
        if not isinstance(item, dict):
            continue
        title = str(item.get("title") or "")
        source_url = str(item.get("source_url") or "")
        emb = item.get("embedding")
        if emb is None:
            emb = embeddings.get((title, source_url))
        emb_literal = _pgvector_literal(emb)

        item_id = item.get("id") or str(uuid.uuid4())
        try:
            item_uuid = str(uuid.UUID(str(item_id)))
        except (ValueError, TypeError, AttributeError):
            item_uuid = str(uuid.uuid4())

        entities = item.get("entities")
        if not isinstance(entities, dict):
            entities = {}

        conn.execute(
            """
            INSERT INTO briefing_items (
                id, briefing_run_id, user_id,
                title, summary, source_url, source_name,
                category, confidence_score, entities, embedding
            ) VALUES (
                %s, %s, %s,
                %s, %s, %s, %s,
                %s, %s, %s::jsonb, %s::vector
            )
            """,
            (
                item_uuid,
                str(run_id),
                str(user_id),
                title,
                str(item.get("summary") or ""),
                source_url,
                str(item.get("source_name") or ""),
                str(item.get("category") or ""),
                float(item.get("confidence_score") or 0.0),
                json.dumps(entities),
                emb_literal,
            ),
        )
        written += 1
    return written


def _persist_metrics(state: SignalState, metrics: dict[str, Any]) -> None:
    """INSERT briefing_runs, briefing_items, and agent_run_metrics.

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
        items_written = _persist_briefing_items(conn, state, run_id, user_id)
        # Idempotent metrics: one row per briefing_run_id (delete+replace).
        conn.execute(
            "DELETE FROM agent_run_metrics WHERE briefing_run_id = %s",
            (str(run_id),),
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
        print(f"briefing_items written: {items_written} for run {run_id}")


def finalize_run_duration(run_id: str | None, duration_seconds: float) -> None:
    """Patch agent_run_metrics after the outer runtime timer finishes.

    run_metrics_writer may persist before execute_graph / HITL resume knows the
    true elapsed wall time for the invoke segment(s). This updates the row in
    place — does not insert a duplicate.
    """
    if not run_id:
        return
    try:
        run_uuid = _as_uuid(run_id, field="run_id")
    except ValueError:
        return
    if duration_seconds < 0:
        return

    pool = _get_pool()
    with pool.connection() as conn:
        conn.execute(
            """
            UPDATE agent_run_metrics
            SET run_duration_seconds = %s
            WHERE briefing_run_id = %s
            """,
            (float(duration_seconds), str(run_uuid)),
        )
        conn.commit()


def run_metrics_writer(state: SignalState) -> dict:
    # TEMP DEBUG SIG-024C
    logger.warning(
        "[SIG-024C DEBUG] BEFORE run_metrics_writer state.keys=%s pid=%s",
        sorted(state.keys()) if hasattr(state, "keys") else type(state),
        os.getpid(),
    )
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
