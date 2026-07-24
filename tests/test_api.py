"""Tests for the FastAPI layer (SIG-P2)."""

from __future__ import annotations

from unittest.mock import patch

from fastapi.testclient import TestClient

from agent.graph import GraphRunResult
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

    with patch("api.routes.execute_graph") as mock_execute:
        mock_execute.return_value = GraphRunResult(
            state=mock_state,
            checkpoint_next=(),
        )

        response = client.post("/run", json={})

    assert response.status_code == 200
    body = response.json()
    assert body["run_id"] == "run-abc"
    assert body["status"] == "completed"
    assert "Funding highlights" in body["briefing_summary"]
    assert body["delivery_status"] == "sent"
    assert body["runtime_metrics"]["tokens_used"] == 1000
    mock_execute.assert_called_once()


def test_run_pending_hitl():
    mock_state = {
        "run_id": "run-hitl",
        "briefing_draft": "Draft awaiting review.",
        "delivery_status": None,
        "graph_version": "1.0",
        "error": None,
    }

    with patch("api.routes.execute_graph") as mock_execute:
        mock_execute.return_value = GraphRunResult(
            state=mock_state,
            checkpoint_next=("hitl_node",),
        )

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

    with patch("api.routes.execute_graph") as mock_execute:
        mock_execute.return_value = GraphRunResult(
            state=mock_state,
            checkpoint_next=(),
        )

        result = execute_pipeline(RunRequest())

    assert result.status == "failed"
    assert result.error == {"code": "SYNTHESIS_FAILED", "message": "synthesis error"}


def test_get_agent_status_idle():
    with patch("api.routes.graph.get_state") as mock_get_state:
        mock_get_state.return_value.next = ()
        response = client.get("/agent/status")

    assert response.status_code == 200
    assert response.json()["status"] == "idle"


def test_get_agent_status_pending_hitl():
    with patch("api.routes.graph.get_state") as mock_get_state:
        mock_get_state.return_value.next = ("hitl_node",)
        response = client.get("/agent/status")

    assert response.status_code == 200
    assert response.json()["status"] == "pending_hitl"


def test_list_briefings_graceful_degradation():
    with patch("api.routes.pool.connection") as mock_conn:
        mock_conn.side_effect = Exception("relation briefing_runs does not exist")
        response = client.get("/briefings")

    assert response.status_code == 200
    assert response.json()["briefings"] == []


def test_get_briefing_pending_hitl_from_checkpoint():
    """During pending_hitl, serve draft via thread_id → graph.get_state."""
    run_id = "11111111-1111-1111-1111-111111111111"
    thread_id = "run_pending_test"

    mock_state = type(
        "Snap",
        (),
        {
            "next": ("hitl_node",),
            "tasks": (),
            "created_at": None,
            "values": {
                "run_id": run_id,
                "thread_id": thread_id,
                "briefing_draft": "## Draft for HITL review",
                "briefing_final": "## Draft for HITL review",
                "briefing_items": [
                    {
                        "id": "item-1",
                        "title": "TestCo raises seed",
                        "summary": "Summary",
                        "source_url": "https://example.com/a",
                        "source_name": "inc42",
                        "category": "funding",
                        "confidence_score": 0.9,
                        "entities": {"company_name_normalized": "testco"},
                    }
                ],
                "graph_version": "1.0",
                "run_duration_seconds": 1.0,
                "tokens_used": 10,
                "estimated_cost_usd": 0.01,
                "findings_retrieved": 5,
                "findings_dropped_freshness": 0,
                "findings_dropped_scope": 0,
                "findings_dropped_dedup": 0,
            },
        },
    )()

    with patch("api.routes.graph.get_state", return_value=mock_state) as get_state:
        response = client.get(f"/briefings/{run_id}?thread_id={thread_id}")

    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "pending_hitl"
    assert body["run_id"] == run_id
    assert body["thread_id"] == thread_id
    assert "HITL review" in body["briefing_draft"]
    assert len(body["briefing_items"]) == 1
    assert body["briefing_items"][0]["title"] == "TestCo raises seed"
    get_state.assert_called_once_with({"configurable": {"thread_id": thread_id}})


def test_get_briefing_pending_hitl_without_thread_id_falls_back_to_db():
    """Without thread_id, pending checkpoint path is skipped (no reverse lookup)."""
    from fastapi import HTTPException

    run_id = "11111111-1111-1111-1111-111111111111"

    with (
        patch("api.routes.graph.get_state") as get_state,
        patch(
            "api.routes._briefing_from_db",
            side_effect=HTTPException(status_code=404, detail="Briefing not found"),
        ),
    ):
        response = client.get(f"/briefings/{run_id}")

    assert response.status_code == 404
    get_state.assert_not_called()


def test_get_briefing_from_db_uses_schema_columns():
    """After HITL, load via briefing_runs.id / briefing_run_id — not run_id."""
    from datetime import datetime, timezone

    run_id = "22222222-2222-2222-2222-222222222222"
    run_at = datetime(2026, 7, 23, 12, 0, tzinfo=timezone.utc)

    run_row = {
        "id": run_id,
        "thread_id": "run_done",
        "status": "completed",
        "run_at": run_at,
        "final_briefing": "## Final persisted briefing",
        "graph_version": "1.0",
    }
    item_rows = [
        {
            "id": "item-db-1",
            "title": "Persisted item",
            "summary": "From DB",
            "source_url": "https://example.com/b",
            "source_name": "yc",
            "category": "funding",
            "confidence_score": 0.95,
            "entities": {},
        }
    ]
    metrics_row = {
        "run_duration_seconds": 9.0,
        "tokens_used": 100,
        "estimated_cost_usd": 0.05,
        "findings_retrieved": 8,
        "findings_dropped_freshness": 1,
        "findings_dropped_scope": 0,
        "findings_dropped_dedup": 2,
        "graph_version": "1.0",
    }

    class FakeCursor:
        def __init__(self, shared):
            self._shared = shared

        def __enter__(self):
            return self

        def __exit__(self, *args):
            return False

        def execute(self, sql, params=None):
            self._shared["calls"] += 1
            # Reject nonexistent column references from the old contract
            assert "WHERE run_id" not in sql
            assert "WHERE run_id =" not in sql.replace(" ", "")
            assert "created_at" not in sql
            assert "briefing_draft" not in sql
            assert "briefing_final" not in sql
            if "FROM briefing_runs" in sql:
                assert "WHERE id" in sql
            if "FROM briefing_items" in sql:
                assert "briefing_run_id" in sql
            if "FROM agent_run_metrics" in sql:
                assert "briefing_run_id" in sql

        def fetchone(self):
            n = self._shared["calls"]
            if n == 1:
                return run_row
            if n == 3:
                return metrics_row
            return None

        def fetchall(self):
            return item_rows

    class FakeConn:
        def __enter__(self):
            self._shared = {"calls": 0}
            return self

        def __exit__(self, *args):
            return False

        def cursor(self):
            return FakeCursor(self._shared)

    with patch("api.routes.pool.connection", return_value=FakeConn()):
        response = client.get(f"/briefings/{run_id}")

    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "completed"
    assert body["run_id"] == run_id
    assert body["briefing_final"] == "## Final persisted briefing"
    assert body["briefing_draft"] == "## Final persisted briefing"
    assert body["briefing_items"][0]["title"] == "Persisted item"
    assert body["runtime_metrics"]["tokens_used"] == 100


def test_resume_hitl_uses_thread_id_query_param():
    """Approve must use thread_id from the runtime contract during pending_hitl."""
    from langgraph.types import Command

    run_id = "33333333-3333-3333-3333-333333333333"
    thread_id = "run_resume_test"

    final_state = {
        "run_id": run_id,
        "thread_id": thread_id,
        "briefing_final": "Approved briefing",
        "delivery_status": "sent",
        "graph_version": "1.0",
        "error": None,
    }
    mock_after = type("Snap", (), {"next": ()})()

    with (
        patch("api.routes._thread_id_from_briefing_runs") as from_db,
        patch("api.routes.graph.invoke", return_value=final_state) as invoke,
        patch("api.routes.graph.get_state", return_value=mock_after),
        patch("api.routes.graph.update_state"),
        patch("api.routes.finalize_run_duration"),
    ):
        response = client.post(f"/briefings/{run_id}/approve?thread_id={thread_id}")

    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "completed"
    assert body["delivery_status"] == "sent"
    from_db.assert_not_called()
    invoke.assert_called_once()
    cmd = invoke.call_args[0][0]
    assert isinstance(cmd, Command)
    assert cmd.resume == "approve"
    assert invoke.call_args[0][1] == {"configurable": {"thread_id": thread_id}}


def test_resume_hitl_reject_uses_command_resume():
    """Reject must use Command(resume=...) matching scripts/test_hitl.py."""
    from langgraph.types import Command

    run_id = "44444444-4444-4444-4444-444444444444"
    thread_id = "run_reject_test"

    final_state = {
        "run_id": run_id,
        "thread_id": thread_id,
        "briefing_final": "Rejected",
        "delivery_status": "rejected",
        "hitl_decision": "reject",
        "graph_version": "1.0",
        "error": None,
    }
    mock_after = type("Snap", (), {"next": ()})()

    with (
        patch("api.routes.graph.invoke", return_value=final_state) as invoke,
        patch("api.routes.graph.get_state", return_value=mock_after),
        patch("api.routes.graph.update_state"),
        patch("api.routes.finalize_run_duration"),
    ):
        response = client.post(f"/briefings/{run_id}/reject?thread_id={thread_id}")

    assert response.status_code == 200
    assert response.json()["delivery_status"] == "rejected"
    cmd = invoke.call_args[0][0]
    assert isinstance(cmd, Command)
    assert cmd.resume == "reject"
