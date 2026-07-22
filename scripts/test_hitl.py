"""SIG-018 HITL + SIG-020A Delivery routing validation.

Uses graph.update_state(as_node=\"synthesis\") so the expensive research/LLM
pipeline is not re-run.

Episodic persistence assertions use the SIG-P2-002 PostgresStore
(namespace (\"user\", user_id, \"episodic\"), key=run_id).

SMTP is mocked so tests do not depend on live Gmail.
"""

from __future__ import annotations

import smtplib
from unittest.mock import MagicMock, patch
from uuid import uuid4

from langgraph.types import Command

from agent.graph import _postgres_store, graph
from agent.nodes.hitl import route_after_hitl

_EPISODIC_NS = ("user", "user_001", "episodic")


def _episode_in_store(run_id: str):
    """Return the PostgresStore episode for run_id, or None."""
    return _postgres_store.get(_EPISODIC_NS, run_id)


def _mock_smtp_success():
    mock_smtp = MagicMock()
    mock_cm = MagicMock()
    mock_cm.__enter__.return_value = mock_smtp
    mock_cm.__exit__.return_value = False
    return mock_cm, mock_smtp


def _seed_after_synthesis(thread_id: str, run_id: str) -> dict:
    """Place graph just after Synthesis with a minimal briefing payload."""
    config = {"configurable": {"thread_id": thread_id}}
    finding = {
        "title": "TestCo raises seed",
        "summary": "Test finding for HITL.",
        "source_url": f"https://example.com/{run_id}",
        "source_name": "inc42",
        "category": "funding",
        "confidence_score": 0.9,
        "entities": {
            "company_name_normalized": "testco",
            "announced_date": "2026-07-01",
        },
        "is_duplicate": False,
        "duplicate_reason": "",
    }
    values = {
        "run_id": run_id,
        "user_id": "user_001",
        "thread_id": thread_id,
        "run_type": "manual",
        "graph_version": "1.0",
        "briefing_draft": "## Signal Weekly Briefing\n\nTest draft.",
        "briefing_final": "## Signal Weekly Briefing\n\nTest final.",
        "briefing_items": [],
        "new_findings": [finding],
        "scored_findings": [finding],
        "raw_findings": [],
        "sources_queried": ["tavily"],
        "findings_retrieved": 1,
        "findings_dropped_freshness": 0,
        "findings_dropped_dedup": 0,
        "findings_dropped_scope": 0,
        "tokens_used": 0,
        "estimated_cost_usd": 0.0,
        "run_duration_seconds": 0.0,
        "run_config_snapshot": {},
        "error": None,
        "source_failures": {
            "tavily": False,
            "yc": False,
            "hn": False,
            "rss": False,
        },
        "semantic_memory": {},
        "procedural_memory": {},
        "query_plan": {},
        "user_config": {"delivery_email": "recipient@example.com"},
        "hitl_decision": None,
        "hitl_edits": None,
        "delivery_status": None,
    }
    graph.update_state(config, values, as_node="synthesis")
    return config


def test_route_after_hitl():
    assert route_after_hitl({"hitl_decision": "approve"}) == "episodic_memory_writer"
    assert route_after_hitl({"hitl_decision": "edit"}) == "episodic_memory_writer"
    assert route_after_hitl({"hitl_decision": "reject"}) == "discard_and_log"
    print("route_after_hitl unit test passed.")


def test_interrupt_after_synthesis():
    thread_id = f"hitl_interrupt_{uuid4().hex[:8]}"
    run_id = str(uuid4())
    config = _seed_after_synthesis(thread_id, run_id)

    result = graph.invoke(None, config)
    state = graph.get_state(config)

    assert state.next == ("hitl_node",), f"expected pause at hitl_node, got {state.next}"
    assert result.get("briefing_final", "").startswith("## Signal")
    interrupts = state.tasks[0].interrupts if state.tasks else ()
    assert interrupts, "expected interrupt payload on hitl task"
    print("Interrupt-after-synthesis test passed.")


def test_approve_writes_episodic_delivers_and_runs_metrics():
    thread_id = f"hitl_approve_{uuid4().hex[:8]}"
    run_id = str(uuid4())
    config = _seed_after_synthesis(thread_id, run_id)

    assert _episode_in_store(run_id) is None

    mock_cm, mock_smtp = _mock_smtp_success()
    graph.invoke(None, config)  # pause at HITL
    with patch("agent.nodes.delivery.smtplib.SMTP_SSL", return_value=mock_cm):
        final = graph.invoke(Command(resume="approve"), config)

    assert graph.get_state(config).next == ()
    assert final.get("hitl_decision") == "approve"
    assert final.get("delivery_status") == "sent"
    mock_smtp.sendmail.assert_called_once()

    item = _episode_in_store(run_id)
    assert item is not None, (
        "approve path must write episode to PostgresStore "
        f"namespace {_EPISODIC_NS} key={run_id}"
    )
    assert item.value.get("run_id") == run_id
    print("Approve-path delivery + PostgresStore test passed.")


def test_reject_skips_episodic_and_delivery():
    thread_id = f"hitl_reject_{uuid4().hex[:8]}"
    run_id = str(uuid4())
    config = _seed_after_synthesis(thread_id, run_id)

    mock_cm, mock_smtp = _mock_smtp_success()
    graph.invoke(None, config)
    with patch("agent.nodes.delivery.smtplib.SMTP_SSL", return_value=mock_cm) as mock_ssl:
        final = graph.invoke(Command(resume="reject"), config)

    assert graph.get_state(config).next == ()
    assert final.get("hitl_decision") == "reject"
    assert final.get("delivery_status") == "rejected"
    assert _episode_in_store(run_id) is None, (
        "DEC-004 violation: reject path left episode in PostgresStore"
    )
    mock_ssl.assert_not_called()
    mock_smtp.sendmail.assert_not_called()
    print("Reject-path DEC-004 (no delivery) test passed.")


def test_approve_delivery_failure_still_keeps_episode():
    """Wrong credentials / SMTP failure must not unwind episodic write (DEC-004)."""
    thread_id = f"hitl_deliv_fail_{uuid4().hex[:8]}"
    run_id = str(uuid4())
    config = _seed_after_synthesis(thread_id, run_id)

    mock_smtp = MagicMock()
    mock_smtp.login.side_effect = smtplib.SMTPAuthenticationError(535, b"bad")
    mock_cm = MagicMock()
    mock_cm.__enter__.return_value = mock_smtp
    mock_cm.__exit__.return_value = False

    graph.invoke(None, config)
    with patch("agent.nodes.delivery.smtplib.SMTP_SSL", return_value=mock_cm):
        with patch("agent.nodes.delivery.time.sleep"):
            final = graph.invoke(Command(resume="approve"), config)

    assert graph.get_state(config).next == ()
    assert final.get("delivery_status") == "failed"
    assert _episode_in_store(run_id) is not None
    print("Delivery-failure keeps episodic memory test passed.")


def test_graph_compiles_with_delivery_on_approve_path_only():
    nodes = set(graph.nodes.keys())
    assert "hitl_node" in nodes
    assert "discard_and_log" in nodes
    assert "episodic_memory_writer" in nodes
    assert "delivery" in nodes
    assert "run_metrics_writer" in nodes
    assert "synthesis" in nodes
    assert "hybrid_dedup" in nodes

    # Inspect compiled edges: reject path must not include delivery.
    g = graph.get_graph()
    edge_pairs = {(e.source, e.target) for e in g.edges}
    assert ("episodic_memory_writer", "delivery") in edge_pairs
    assert ("delivery", "run_metrics_writer") in edge_pairs
    assert ("discard_and_log", "run_metrics_writer") in edge_pairs
    assert ("discard_and_log", "delivery") not in edge_pairs
    assert ("episodic_memory_writer", "run_metrics_writer") not in edge_pairs
    print("Graph compile / delivery edge test passed.")


if __name__ == "__main__":
    test_route_after_hitl()
    test_graph_compiles_with_delivery_on_approve_path_only()
    test_interrupt_after_synthesis()
    test_approve_writes_episodic_delivers_and_runs_metrics()
    test_reject_skips_episodic_and_delivery()
    test_approve_delivery_failure_still_keeps_episode()
    print("All HITL + delivery tests passed.")
