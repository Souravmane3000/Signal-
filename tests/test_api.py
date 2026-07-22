"""Tests for the FastAPI layer (SIG-P2)."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

from fastapi.testclient import TestClient

from api.main import app
from api.schemas import RunRequest
from api.routes import execute_pipeline

client = TestClient(app, raise_server_exceptions=False)


def test_health_returns_ok():
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_run_success_completed():
    mock_state = {
        "run_id": "run-abc",
        "briefing_final": "## Signal Weekly Briefing\n\nFunding highlights.",
        "delivery_status": "sent",
        "run_duration_seconds": 12.5,
        "tokens_used": 1000,
        "estimated_cost_usd": 0.02,
        "findings_retrieved": 20,
        "findings_dropped_freshness": 2,
        "findings_dropped_scope": 1,
        "findings_dropped_dedup": 3,
        "graph_version": "1.0",
        "error": None,
    }
    mock_graph_state = MagicMock()
    mock_graph_state.next = ()

    with patch("agent.graph.graph") as mock_graph:
        mock_graph.invoke.return_value = mock_state
        mock_graph.get_state.return_value = mock_graph_state

        response = client.post("/run", json={})

    assert response.status_code == 200
    body = response.json()
    assert body["run_id"] == "run-abc"
    assert body["status"] == "completed"
    assert "Funding highlights" in body["briefing_summary"]
    assert body["delivery_status"] == "sent"
    assert body["runtime_metrics"]["tokens_used"] == 1000
    mock_graph.invoke.assert_called_once()


def test_run_pending_hitl():
    mock_state = {
        "run_id": "run-hitl",
        "briefing_draft": "Draft awaiting review.",
        "delivery_status": None,
        "graph_version": "1.0",
        "error": None,
    }
    mock_graph_state = MagicMock()
    mock_graph_state.next = ("hitl_node",)

    with patch("agent.graph.graph") as mock_graph:
        mock_graph.invoke.return_value = mock_state
        mock_graph.get_state.return_value = mock_graph_state

        response = client.post("/run", json={"run_type": "manual"})

    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "pending_hitl"
    assert body["run_id"] == "run-hitl"


def test_run_pipeline_error_returns_500():
    with patch("api.routes.execute_pipeline", side_effect=RuntimeError("boom")):
        response = client.post("/run", json={})

    assert response.status_code == 500
    assert "detail" in response.json()
    assert "stack" not in response.text.lower()


def test_run_invalid_request_returns_422():
    response = client.post("/run", json={"run_type": "invalid"})
    assert response.status_code == 422
    assert "detail" in response.json()


def test_execute_pipeline_value_error_returns_400():
    with patch(
        "api.routes.execute_pipeline",
        side_effect=ValueError("bad user id"),
    ):
        response = client.post("/run", json={})

    assert response.status_code == 400
    assert response.json()["detail"] == "bad user id"


def test_execute_pipeline_failed_status():
    mock_state = {
        "run_id": "run-fail",
        "briefing_final": "",
        "error": {"code": "SYNTHESIS_FAILED", "message": "synthesis error"},
        "graph_version": "1.0",
    }
    mock_graph_state = MagicMock()
    mock_graph_state.next = ()

    with patch("agent.graph.graph") as mock_graph:
        mock_graph.invoke.return_value = mock_state
        mock_graph.get_state.return_value = mock_graph_state

        result = execute_pipeline(RunRequest())

    assert result.status == "failed"
    assert result.error == {"code": "SYNTHESIS_FAILED", "message": "synthesis error"}
