"""Integration test: POST /run through the real shared execution path."""

from __future__ import annotations

import os
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient

from agent.graph import execute_graph, graph
from api.main import app

pytestmark = pytest.mark.skipif(
    not os.getenv("DATABASE_URL"),
    reason="DATABASE_URL required for real graph execution",
)

client = TestClient(app, raise_server_exceptions=False)


def _seed_after_synthesis(thread_id: str, run_id: str) -> dict:
    """Place graph just after Synthesis (same pattern as scripts/test_hitl.py)."""
    config = {"configurable": {"thread_id": thread_id}}
    finding = {
        "title": "TestCo raises seed",
        "summary": "Test finding for API integration.",
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
        "briefing_draft": "## Signal Weekly Briefing\n\nIntegration test draft.",
        "briefing_final": "## Signal Weekly Briefing\n\nIntegration test final.",
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


def test_post_run_executes_real_graph_via_shared_entry_point(monkeypatch):
    """POST /run -> execute_graph -> graph.invoke -> HTTP response (no mocked invoke)."""
    thread_id = f"api_int_{uuid4().hex[:8]}"
    run_id = str(uuid4())
    _seed_after_synthesis(thread_id, run_id)

    calls: list[dict] = []
    real_execute_graph = execute_graph

    def recording_execute_graph(**kwargs):
        calls.append(kwargs)
        if kwargs.get("thread_id") == thread_id:
            return real_execute_graph(thread_id=thread_id, resume=True)
        return real_execute_graph(**kwargs)

    monkeypatch.setattr("api.routes.execute_graph", recording_execute_graph)

    response = client.post("/run", json={"thread_id": thread_id})

    assert response.status_code == 200
    body = response.json()

    assert calls, "expected POST /run to call the shared execute_graph entry point"
    assert calls[0]["thread_id"] == thread_id
    assert body["run_id"] == run_id
    assert body["status"] == "pending_hitl"
    assert "Integration test" in body["briefing_summary"]
    assert body["runtime_metrics"] is not None
    assert body["runtime_metrics"]["graph_version"] == "1.0"
