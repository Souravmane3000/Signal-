"""SIG-021B — Run Metrics Writer Postgres persistence tests."""

from __future__ import annotations

from io import StringIO
from unittest.mock import patch
from uuid import uuid4

from agent.graph import pool
from agent.nodes.run_metrics_writer import run_metrics_writer


def _state(**overrides):
    base = {
        "run_id": str(uuid4()),
        "user_id": "user_001",  # Phase-1 string; writer resolves via fallback auth user
        "thread_id": "thread_metrics_test",
        "graph_version": "1.0",
        "sources_queried": ["tavily", "yc"],
        "findings_retrieved": 20,
        "findings_dropped_freshness": 3,
        "findings_dropped_scope": 2,
        "findings_dropped_dedup": 1,
        "new_findings": [
            {
                "title": "Alpha raises seed",
                "summary": "Alpha raised $2M",
                "source_url": "https://example.com/a",
                "source_name": "tavily",
                "category": "funding",
                "confidence_score": 0.9,
                "entities": {"company": "Alpha"},
            },
            {
                "title": "Beta hires CTO",
                "summary": "Beta announced a CTO hire",
                "source_url": "https://example.com/b",
                "source_name": "hn",
                "category": "hiring",
                "confidence_score": 0.7,
                "entities": {"company": "Beta"},
            },
        ],
        "briefing_items": [
            {
                "id": str(uuid4()),
                "title": "Alpha raises seed",
                "summary": "Alpha raised $2M",
                "source_url": "https://example.com/a",
                "source_name": "tavily",
                "category": "funding",
                "confidence_score": 0.9,
                "entities": {"company": "Alpha"},
            },
            {
                "id": str(uuid4()),
                "title": "Beta hires CTO",
                "summary": "Beta announced a CTO hire",
                "source_url": "https://example.com/b",
                "source_name": "hn",
                "category": "hiring",
                "confidence_score": 0.7,
                "entities": {"company": "Beta"},
            },
        ],
        "tokens_used": 5000,
        "estimated_cost_usd": 0.05,
        "run_duration_seconds": 12.5,
        "briefing_final": "Test briefing",
        "run_config_snapshot": {},
        "delivery_status": "sent",
        "error": None,
        "source_failures": {
            "tavily": False,
            "yc": True,
            "hn": False,
            "rss": False,
        },
    }
    base.update(overrides)
    return base


def _cleanup(run_id: str) -> None:
    with pool.connection() as conn:
        conn.execute(
            "DELETE FROM agent_run_metrics WHERE briefing_run_id = %s::uuid",
            (run_id,),
        )
        conn.execute(
            "DELETE FROM briefing_items WHERE briefing_run_id = %s::uuid",
            (run_id,),
        )
        conn.execute(
            "DELETE FROM briefing_runs WHERE id = %s::uuid",
            (run_id,),
        )
        conn.commit()


def test_returns_empty_dict():
    state = _state()
    try:
        with patch("sys.stdout", new_callable=StringIO):
            result = run_metrics_writer(state)
        assert result == {}
    finally:
        _cleanup(state["run_id"])


def test_does_not_modify_state():
    state = _state()
    original = dict(state)
    try:
        with patch("sys.stdout", new_callable=StringIO):
            run_metrics_writer(state)
        assert state == original
    finally:
        _cleanup(state["run_id"])


def test_warning_for_failed_sources():
    state = _state()
    buf = StringIO()
    try:
        with patch("sys.stdout", buf):
            run_metrics_writer(state)
        output = buf.getvalue()
        assert "WARNING: yc failed this run" in output
        assert "WARNING: tavily failed this run" not in output
    finally:
        _cleanup(state["run_id"])


def test_inserts_agent_run_metrics_row():
    state = _state()
    run_id = state["run_id"]
    try:
        with patch("sys.stdout", new_callable=StringIO):
            run_metrics_writer(state)

        with pool.connection() as conn:
            row = conn.execute(
                """
                SELECT graph_version, source_health,
                       findings_retrieved, findings_dropped_freshness,
                       findings_dropped_scope, findings_dropped_dedup,
                       findings_in_briefing, tokens_used,
                       estimated_cost_usd, run_duration_seconds,
                       sources_queried
                FROM agent_run_metrics
                WHERE briefing_run_id = %s::uuid
                ORDER BY run_at DESC
                LIMIT 1
                """,
                (run_id,),
            ).fetchone()

        assert row is not None
        assert row["graph_version"] == "1.0"
        health = row["source_health"]
        if isinstance(health, str):
            import json

            health = json.loads(health)
        assert health["yc"] is True
        assert health["tavily"] is False
        assert row["findings_retrieved"] == 20
        assert row["findings_dropped_freshness"] == 3
        assert row["findings_dropped_scope"] == 2
        assert row["findings_dropped_dedup"] == 1
        assert row["findings_in_briefing"] == 2
        assert row["tokens_used"] == 5000
        assert abs(float(row["estimated_cost_usd"]) - 0.05) < 1e-9
        assert abs(float(row["run_duration_seconds"]) - 12.5) < 1e-9
        assert list(row["sources_queried"]) == ["tavily", "yc"]
    finally:
        _cleanup(run_id)


def test_inserts_briefing_items_rows():
    state = _state()
    run_id = state["run_id"]
    try:
        with patch("sys.stdout", new_callable=StringIO):
            run_metrics_writer(state)

        with pool.connection() as conn:
            rows = conn.execute(
                """
                SELECT id, title, summary, source_url, source_name,
                       category, confidence_score, entities, embedding
                FROM briefing_items
                WHERE briefing_run_id = %s::uuid
                ORDER BY title
                """,
                (run_id,),
            ).fetchall()

        assert len(rows) == 2
        titles = {row["title"] for row in rows}
        assert titles == {"Alpha raises seed", "Beta hires CTO"}
        alpha = next(r for r in rows if r["title"] == "Alpha raises seed")
        assert alpha["summary"] == "Alpha raised $2M"
        assert alpha["source_name"] == "tavily"
        assert alpha["category"] == "funding"
        assert abs(float(alpha["confidence_score"]) - 0.9) < 1e-9
        assert alpha["entities"]["company"] == "Alpha"
        expected_ids = {item["id"] for item in state["briefing_items"]}
        assert {str(row["id"]) for row in rows} == expected_ids
        beta = next(r for r in rows if r["title"] == "Beta hires CTO")
        assert beta["source_url"] == "https://example.com/b"
    finally:
        _cleanup(run_id)


def test_updates_briefing_runs_graph_version():
    state = _state(graph_version="2.1-test")
    run_id = state["run_id"]
    try:
        with patch("sys.stdout", new_callable=StringIO):
            run_metrics_writer(state)
        with pool.connection() as conn:
            row = conn.execute(
                "SELECT graph_version, status FROM briefing_runs WHERE id = %s::uuid",
                (run_id,),
            ).fetchone()
        assert row is not None
        assert row["graph_version"] == "2.1-test"
        assert row["status"] == "completed"
    finally:
        _cleanup(run_id)


def test_reject_path_status_is_rejected():
    state = _state(delivery_status="rejected")
    run_id = state["run_id"]
    try:
        with patch("sys.stdout", new_callable=StringIO):
            run_metrics_writer(state)
        with pool.connection() as conn:
            status = conn.execute(
                "SELECT status FROM briefing_runs WHERE id = %s::uuid",
                (run_id,),
            ).fetchone()["status"]
            metrics_count = conn.execute(
                "SELECT count(*) AS n FROM agent_run_metrics WHERE briefing_run_id = %s::uuid",
                (run_id,),
            ).fetchone()["n"]
        assert status == "rejected"
        assert metrics_count == 1
    finally:
        _cleanup(run_id)


def test_select_latest_graph_version_and_source_health():
    """Acceptance: SELECT graph_version, source_health ... LIMIT 1 works."""
    state = _state(graph_version="1.0-select-check")
    run_id = state["run_id"]
    try:
        with patch("sys.stdout", new_callable=StringIO):
            run_metrics_writer(state)
        with pool.connection() as conn:
            row = conn.execute(
                """
                SELECT graph_version, source_health
                FROM agent_run_metrics
                ORDER BY run_at DESC
                LIMIT 1
                """
            ).fetchone()
        assert row["graph_version"] == "1.0-select-check"
        assert row["source_health"] is not None
    finally:
        _cleanup(run_id)


def test_persistence_failure_is_not_swallowed():
    state = _state()
    with patch(
        "agent.nodes.run_metrics_writer._persist_metrics",
        side_effect=RuntimeError("db down"),
    ):
        try:
            with patch("sys.stdout", new_callable=StringIO):
                run_metrics_writer(state)
            raised = False
        except RuntimeError as exc:
            raised = True
            assert "db down" in str(exc)
    assert raised


def test_missing_source_failures_raises():
    state = _state()
    del state["source_failures"]
    try:
        run_metrics_writer(state)
        raised = False
    except RuntimeError:
        raised = True
    assert raised


def test_findings_in_briefing_uses_briefing_items_not_new_findings():
    """Empty briefing_items must count as 0 even when new_findings is non-empty."""
    from agent.nodes.run_metrics_writer import _build_metrics

    state = _state(
        briefing_items=[],
        new_findings=[{"title": "orphan"}, {"title": "orphan2"}],
    )
    metrics = _build_metrics(state)
    assert metrics["findings_in_briefing"] == 0


def test_finalize_run_duration_patches_metrics_row():
    from agent.nodes.run_metrics_writer import finalize_run_duration

    state = _state(run_duration_seconds=0.0)
    run_id = state["run_id"]
    try:
        with patch("sys.stdout", new_callable=StringIO):
            run_metrics_writer(state)
        finalize_run_duration(run_id, 42.5)
        with pool.connection() as conn:
            row = conn.execute(
                """
                SELECT run_duration_seconds, findings_in_briefing
                FROM agent_run_metrics
                WHERE briefing_run_id = %s::uuid
                """,
                (run_id,),
            ).fetchone()
            items = conn.execute(
                "SELECT count(*) AS n FROM briefing_items WHERE briefing_run_id = %s::uuid",
                (run_id,),
            ).fetchone()["n"]
        assert abs(float(row["run_duration_seconds"]) - 42.5) < 1e-9
        assert row["findings_in_briefing"] == 2
        assert items == 2
    finally:
        _cleanup(run_id)


def test_metrics_writer_is_idempotent():
    state = _state()
    run_id = state["run_id"]
    try:
        with patch("sys.stdout", new_callable=StringIO):
            run_metrics_writer(state)
            run_metrics_writer(state)
        with pool.connection() as conn:
            metrics_n = conn.execute(
                "SELECT count(*) AS n FROM agent_run_metrics WHERE briefing_run_id = %s::uuid",
                (run_id,),
            ).fetchone()["n"]
            items_n = conn.execute(
                "SELECT count(*) AS n FROM briefing_items WHERE briefing_run_id = %s::uuid",
                (run_id,),
            ).fetchone()["n"]
        assert metrics_n == 1
        assert items_n == 2
    finally:
        _cleanup(run_id)


if __name__ == "__main__":
    test_returns_empty_dict()
    test_does_not_modify_state()
    test_warning_for_failed_sources()
    test_inserts_agent_run_metrics_row()
    test_inserts_briefing_items_rows()
    test_updates_briefing_runs_graph_version()
    test_reject_path_status_is_rejected()
    test_select_latest_graph_version_and_source_health()
    test_persistence_failure_is_not_swallowed()
    test_missing_source_failures_raises()
    test_findings_in_briefing_uses_briefing_items_not_new_findings()
    test_finalize_run_duration_patches_metrics_row()
    test_metrics_writer_is_idempotent()
    print("Run metrics writer tests passed.")
