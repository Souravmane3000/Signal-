"""SIG-022 — Feedback store + collector tests."""

from __future__ import annotations

from io import StringIO
from unittest.mock import patch
from uuid import uuid4

from agent.graph import pool
from agent.memory.feedback_store import (
    fetch_all_feedback_for_user,
    insert_feedback,
)
from agent.nodes.feedback_collector import feedback_collector


def _cleanup_user_feedback(user_key: str = "user_001") -> None:
    """Delete feedback rows belonging to the resolved auth user."""
    rows = fetch_all_feedback_for_user(user_key)
    if not rows:
        return
    ids = [str(r["id"]) for r in rows]
    with pool.connection() as conn:
        conn.execute(
            "DELETE FROM user_feedback WHERE id = ANY(%s::uuid[])",
            (ids,),
        )
        conn.commit()


def test_insert_and_fetch_feedback():
    _cleanup_user_feedback()
    try:
        inserted = insert_feedback(
            user_id="user_001",
            feedback="useful",
            category="funding",
            source_name="inc42",
            reason="great_find",
        )
        assert inserted["feedback"] == "useful"
        assert inserted["category"] == "funding"
        assert inserted["source_name"] == "inc42"
        assert inserted["reason"] == "great_find"
        assert inserted["created_at"] is not None

        rows = fetch_all_feedback_for_user("user_001")
        assert isinstance(rows, list)
        assert len(rows) >= 1
        assert any(str(r["id"]) == str(inserted["id"]) for r in rows)
    finally:
        _cleanup_user_feedback()


def test_fetch_all_feedback_for_user_returns_list():
    rows = fetch_all_feedback_for_user("user_001")
    assert isinstance(rows, list)


def test_insert_rejects_invalid_feedback_type():
    try:
        insert_feedback(user_id="user_001", feedback="maybe")
        raised = False
    except ValueError:
        raised = True
    assert raised


def test_insert_not_relevant_with_reason():
    _cleanup_user_feedback()
    try:
        row = insert_feedback(
            user_id="user_001",
            feedback="not_relevant",
            category="hiring",
            source_name="hn",
            reason="wrong_stage",
        )
        assert row["feedback"] == "not_relevant"
        assert row["reason"] == "wrong_stage"
    finally:
        _cleanup_user_feedback()


def test_collector_noop_without_pending_feedback():
    state = {"user_id": "user_001", "run_id": str(uuid4())}
    original = dict(state)
    result = feedback_collector(state)
    assert result == {}
    assert state == original


def test_collector_persists_pending_feedback():
    _cleanup_user_feedback()
    state = {
        "user_id": "user_001",
        "run_id": str(uuid4()),
        "pending_feedback": [
            {
                "feedback": "useful",
                "category": "funding",
                "source_name": "techcrunch",
                "reason": "great_find",
            },
            {
                "feedback": "not_relevant",
                "category": "ecosystem_trend",
                "source_name": "rss_other",
                "reason": "too_generic",
            },
        ],
    }
    original_keys = set(state.keys())
    try:
        with patch("sys.stdout", new_callable=StringIO):
            result = feedback_collector(state)
        assert result == {}
        assert set(state.keys()) == original_keys
        rows = fetch_all_feedback_for_user("user_001")
        assert len(rows) == 2
        values = {r["feedback"] for r in rows}
        assert values == {"useful", "not_relevant"}
    finally:
        _cleanup_user_feedback()


def test_collector_does_not_touch_memory_namespaces():
    """Collector must not write PostgresStore memory namespaces."""
    from agent.graph import _postgres_store

    ns = ("user", "user_001", "procedural")
    before = list(_postgres_store.search(ns, limit=100))
    state = {
        "user_id": "user_001",
        "pending_feedback": [
            {"feedback": "useful", "category": "funding", "source_name": "yc"}
        ],
    }
    try:
        with patch("sys.stdout", new_callable=StringIO):
            feedback_collector(state)
        after = list(_postgres_store.search(ns, limit=100))
        assert len(after) == len(before)
    finally:
        _cleanup_user_feedback()


def test_collector_surfaces_persistence_failure():
    state = {
        "user_id": "user_001",
        "pending_feedback": [{"feedback": "useful", "category": "funding"}],
    }
    with patch(
        "agent.nodes.feedback_collector.insert_feedback",
        side_effect=RuntimeError("db down"),
    ):
        try:
            with patch("sys.stdout", new_callable=StringIO):
                feedback_collector(state)
            raised = False
        except RuntimeError as exc:
            raised = True
            assert "db down" in str(exc)
    assert raised


def test_graph_unchanged_no_feedback_node_wired():
    from agent.graph import graph

    assert "feedback_collector" not in graph.nodes
    g = graph.get_graph()
    edges = {(e.source, e.target) for e in g.edges}
    assert ("run_metrics_writer", "__end__") in edges


if __name__ == "__main__":
    test_fetch_all_feedback_for_user_returns_list()
    test_insert_rejects_invalid_feedback_type()
    test_insert_and_fetch_feedback()
    test_insert_not_relevant_with_reason()
    test_collector_noop_without_pending_feedback()
    test_collector_persists_pending_feedback()
    test_collector_does_not_touch_memory_namespaces()
    test_collector_surfaces_persistence_failure()
    test_graph_unchanged_no_feedback_node_wired()
    print("Feedback collector / store tests passed.")
