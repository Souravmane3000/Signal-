"""Tests for the FastAPI layer (SIG-P2)."""

from __future__ import annotations

from unittest.mock import patch

from fastapi.testclient import TestClient
from tests.conftest import attach_default_auth

from agent.graph import GraphRunResult
from api.main import app
from api.schemas import RunRequest
from api.routes import execute_pipeline

client = TestClient(app, raise_server_exceptions=False)
attach_default_auth(client)


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
    with (
        patch("api.routes.get_live_node", return_value=None),
        patch("api.routes.lookup_langsmith_pipeline_node", return_value=None),
        patch("api.routes._briefing_run_row_for_thread", return_value=None),
        patch("api.routes.graph.get_state") as mock_get_state,
    ):
        snap = mock_get_state.return_value
        snap.next = ()
        snap.tasks = ()
        snap.values = {}
        response = client.get("/agent/status")

    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "idle"
    assert body["current_node"] is None
    assert body["current_label"] is None
    assert body["step_index"] is None
    assert body["step_total"] is None


def test_get_agent_status_running_current_node():
    with (
        patch("api.routes.get_live_node", return_value=None),
        patch("api.routes.lookup_langsmith_pipeline_node", return_value=None),
        patch("api.routes._briefing_run_row_for_thread", return_value=None),
        patch("api.routes.graph.get_state") as mock_get_state,
    ):
        snap = mock_get_state.return_value
        snap.next = ("tavily_search",)
        snap.tasks = ()
        snap.values = {}
        response = client.get("/agent/status")

    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "running"
    assert body["current_node"] == "tavily_search"
    assert body["current_label"] == "Searching the web"
    assert body["step_index"] == 3
    assert body["step_total"] == 18


def test_get_agent_status_pending_hitl():
    with (
        patch("api.routes.get_live_node", return_value=None),
        patch("api.routes.lookup_langsmith_pipeline_node", return_value=None),
        patch("api.routes._briefing_run_row_for_thread", return_value=None),
        patch("api.routes.graph.get_state") as mock_get_state,
    ):
        snap = mock_get_state.return_value
        snap.next = ("hitl_node",)
        snap.tasks = ()
        snap.values = {}
        response = client.get("/agent/status")

    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "pending_hitl"
    assert body["current_node"] == "hitl_node"
    assert body["current_label"] == "Awaiting your review"
    assert body["step_index"] == 14
    assert body["step_total"] == 18


def test_get_agent_status_live_map_overrides_empty_next():
    with (
        patch("api.routes.get_live_node", return_value="tavily_search"),
        patch("api.routes.lookup_langsmith_pipeline_node", return_value=None),
        patch("api.routes._briefing_run_row_for_thread", return_value=None),
        patch("api.routes.graph.get_state") as mock_get_state,
    ):
        snap = mock_get_state.return_value
        snap.next = ()
        snap.tasks = ()
        snap.values = {}
        response = client.get("/agent/status")

    mock_get_state.assert_not_called()

    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "running"
    assert body["current_node"] == "tavily_search"
    assert body["current_label"] == "Searching the web"
    assert body["step_index"] == 3
    assert body["step_total"] == 18


def test_get_agent_status_live_hitl_overrides_empty_next():
    with (
        patch("api.routes.get_live_node", return_value="hitl_node"),
        patch("api.routes.lookup_langsmith_pipeline_node", return_value=None),
        patch("api.routes._briefing_run_row_for_thread", return_value=None),
        patch("api.routes.graph.get_state") as mock_get_state,
    ):
        snap = mock_get_state.return_value
        snap.next = ()
        snap.tasks = ()
        snap.values = {}
        response = client.get("/agent/status")

    mock_get_state.assert_not_called()

    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "pending_hitl"
    assert body["current_node"] == "hitl_node"
    assert body["current_label"] == "Awaiting your review"


def test_get_agent_status_langsmith_child_overrides_empty_next():
    with (
        patch("api.routes.get_live_node", return_value=None),
        patch(
            "api.routes.lookup_langsmith_pipeline_node",
            return_value="entity_extraction",
        ),
        patch("api.routes._briefing_run_row_for_thread", return_value=None),
        patch("api.routes.graph.get_state") as mock_get_state,
    ):
        snap = mock_get_state.return_value
        snap.next = ()
        snap.tasks = ()
        snap.values = {}
        response = client.get("/agent/status")

    mock_get_state.assert_not_called()

    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "running"
    assert body["current_node"] == "entity_extraction"
    assert body["current_label"] == "Extracting entities"


def test_get_agent_status_completed_db_row_skips_checkpoint():
    from tests.conftest import TEST_USER_ID

    with (
        patch("api.routes.get_live_node", return_value=None),
        patch("api.routes.lookup_langsmith_pipeline_node", return_value=None),
        patch(
            "api.routes._briefing_run_row_for_thread",
            return_value={"user_id": TEST_USER_ID, "status": "completed"},
        ),
        patch("api.routes.graph.get_state") as mock_get_state,
    ):
        response = client.get("/agent/status?thread_id=run_done")

    mock_get_state.assert_not_called()
    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "idle"
    assert body["current_node"] is None


def test_get_agent_status_other_user_thread_idle():
    with (
        patch("api.routes.get_live_node", return_value="entity_extraction"),
        patch(
            "api.routes._briefing_run_row_for_thread",
            return_value={"user_id": "bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbbb", "status": "running"},
        ),
        patch("api.routes.graph.get_state") as mock_get_state,
    ):
        response = client.get("/agent/status?thread_id=run_other")

    mock_get_state.assert_not_called()
    assert response.status_code == 200
    assert response.json()["status"] == "idle"


def test_pipeline_progress_handler_sets_live_node():
    from agent.graph import (
        PipelineProgressHandler,
        clear_live_node,
        get_live_node,
    )

    tid = "run_cursor_cb"
    clear_live_node(tid)
    handler = PipelineProgressHandler(tid)
    handler.on_chain_start({}, {}, name="LangGraph")
    assert get_live_node(tid) is None
    handler.on_chain_start({}, {}, name="tavily_search")
    assert get_live_node(tid) == "tavily_search"
    handler.on_chain_start({}, {}, name="RunnableSequence")
    assert get_live_node(tid) == "tavily_search"
    clear_live_node(tid)
    assert get_live_node(tid) is None


def test_graph_invoke_config_includes_langsmith_metadata():
    from agent.graph import PipelineProgressHandler, graph, graph_invoke_config

    assert graph.name == "signal-pipeline"
    cfg = graph_invoke_config("run_abc", run_type="manual", user_id="u1")
    assert cfg["run_name"] == "signal-pipeline"
    assert cfg["configurable"]["thread_id"] == "run_abc"
    assert cfg["metadata"]["thread_id"] == "run_abc"
    assert cfg["metadata"]["run_type"] == "manual"
    assert cfg["metadata"]["user_id"] == "u1"
    handlers = getattr(cfg["callbacks"], "handlers", None) or list(cfg["callbacks"])
    assert any(isinstance(cb, PipelineProgressHandler) for cb in handlers)



def test_list_briefings_grouped_count_query():
    from pathlib import Path

    src = Path("api/routes.py").read_text(encoding="utf-8")
    start = src.index("def list_briefings")
    end = src.index("\n@router.", start + 1)
    body = src[start:end]
    assert "WITH recent AS" in body
    assert "GROUP BY r.id" in body
    assert "SELECT count(*)" not in body


def test_list_briefings_graceful_degradation():
    with patch("api.routes.pool.connection") as mock_conn:
        mock_conn.side_effect = Exception("relation briefing_runs does not exist")
        response = client.get("/briefings")

    assert response.status_code == 200
    assert response.json()["briefings"] == []


def test_get_briefing_pending_hitl_from_checkpoint():
    """During pending_hitl, serve draft via thread_id → graph.get_state."""
    from fastapi import HTTPException

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

    with (
        patch(
            "api.routes._briefing_from_db",
            side_effect=HTTPException(status_code=404, detail="Briefing not found"),
        ),
        patch("api.routes.graph.get_state", return_value=mock_state) as get_state,
    ):
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


def test_get_saved_briefing_skips_checkpoint_even_with_thread_id():
    """Completed briefings must not call graph.get_state (SIG-033)."""
    from datetime import datetime, timezone

    run_id = "22222222-2222-2222-2222-222222222222"
    run_at = datetime(2026, 7, 23, 12, 0, tzinfo=timezone.utc)
    combined = {
        "id": run_id,
        "thread_id": "run_done",
        "status": "completed",
        "run_at": run_at,
        "final_briefing": "## Final persisted briefing",
        "graph_version": "1.0",
        "run_duration_seconds": 9.0,
        "tokens_used": 100,
        "estimated_cost_usd": 0.05,
        "findings_retrieved": 8,
        "findings_dropped_freshness": 1,
        "findings_dropped_scope": 0,
        "findings_dropped_dedup": 2,
        "metrics_graph_version": "1.0",
        "items": [
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
        ],
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
            self._shared["sql"] = sql
            assert "FROM briefing_runs" in sql
            assert "json_agg" in sql or "LEFT JOIN LATERAL" in sql
            assert "agent_run_metrics" in sql
            assert "briefing_items" in sql

        def fetchone(self):
            return combined

        def fetchall(self):
            return []

    class FakeConn:
        def __enter__(self):
            self._shared = {"calls": 0, "sql": ""}
            return self

        def __exit__(self, *args):
            return False

        def cursor(self):
            return FakeCursor(self._shared)

    with (
        patch("api.routes.pool.connection", return_value=FakeConn()),
        patch("api.routes.graph.get_state") as get_state,
    ):
        response = client.get(
            f"/briefings/{run_id}?thread_id=run_should_be_ignored"
        )

    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "completed"
    assert body["briefing_items"][0]["title"] == "Persisted item"
    get_state.assert_not_called()


def test_get_briefing_from_db_uses_schema_columns():
    """After HITL, load via briefing_runs.id / briefing_run_id — not run_id."""
    from datetime import datetime, timezone

    run_id = "22222222-2222-2222-2222-222222222222"
    run_at = datetime(2026, 7, 23, 12, 0, tzinfo=timezone.utc)

    combined = {
        "id": run_id,
        "thread_id": "run_done",
        "status": "completed",
        "run_at": run_at,
        "final_briefing": "## Final persisted briefing",
        "graph_version": "1.0",
        "run_duration_seconds": 9.0,
        "tokens_used": 100,
        "estimated_cost_usd": 0.05,
        "findings_retrieved": 8,
        "findings_dropped_freshness": 1,
        "findings_dropped_scope": 0,
        "findings_dropped_dedup": 2,
        "metrics_graph_version": "1.0",
        "items": [
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
        ],
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
            assert "FROM briefing_runs" in sql
            assert "br.id" in sql.replace(" ", "") or "WHERE id" in sql
            assert "briefing_run_id" in sql
            assert "agent_run_metrics" in sql

        def fetchone(self):
            assert self._shared["calls"] == 1
            return combined

        def fetchall(self):
            return []

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


def test_frontend_saved_briefing_omits_thread_id():
    """Configuration of showBriefingDetail must not attach thread_id for saved opens."""
    from pathlib import Path

    html = Path("frontend/index.html").read_text(encoding="utf-8")
    assert "async function showBriefingDetail" in html
    # Extract the function body loosely
    start = html.index("async function showBriefingDetail")
    end = html.index("function renderBriefingDetail", start)
    body = html[start:end]
    assert "pending_hitl" in body
    assert "apiFetch(`/briefings/${runId}`)" in body or 'apiFetch(`/briefings/${runId}`)' in body
    assert "thread_id=${encodeURIComponent" not in body


def test_frontend_pipeline_stage_replaces_run_overlay():
    from pathlib import Path

    html = Path("frontend/index.html").read_text(encoding="utf-8")
    assert 'id="pipeline-stage"' in html
    start = html.index("function updateStatus")
    end = html.index("async function triggerRun", start)
    body = html[start:end]
    assert "showPipelineStage" in body
    assert "loadingOverlay.classList.remove" not in body
    assert "config_loader" not in body
    assert "Starting pipeline" not in body
    assert "Step ${index} of" not in html
    assert "http://localhost:8080" in html
    assert 'id="api-host-chip"' in html
    show_start = html.index("function showPipelineStage")
    show_body = html[show_start:start]
    assert "current_node" in show_body
    trigger = html[html.index("async function triggerRun") : html.index("async function fetchBriefings")]
    assert "thread_id: threadId" in trigger
    assert "newRunThreadId" in trigger
    assert "loadingOverlay.classList.remove" not in trigger


def test_frontend_responsiveness_shell_and_swr():
    from pathlib import Path

    html = Path("frontend/index.html").read_text(encoding="utf-8")
    assert "Running Intelligence Pipeline" not in html
    assert 'id="loading-overlay-label"' in html
    assert "Loading briefing…" in html
    assert "const POLL_IDLE_MS = 20000" in html
    assert "pollInFlight" in html
    assert "visibilitychange" in html
    assert "document.visibilityState" in html
    assert "scheduleWarmPrefetch" in html
    assert "requestIdleCallback" in html
    assert "loadDashboardMarkdown" in html
    assert "trustHint: true" in html
    assert "setAuthLoading(false)" in html
    route = html[html.index("async function routeAfterAuth") : html.index("async function enterAuthenticatedApp")]
    assert "if (!trustHint)" in route
    enter = html[html.index("async function enterAuthenticatedApp") : html.index("async function submitAuth")]
    assert "await pollStatus()" not in enter
    assert "await refreshDashboard()" not in enter
    assert "bindPollVisibility()" in enter
    set_view = html[html.index("function setView") : html.index("function toggleSidebar")]
    assert "silent: state.briefings.length > 0" in set_view
    assert "silent: state.runMetrics.length > 0" in set_view
    assert "silent: !!state.userConfig" in set_view
    poll = html[html.index("async function pollStatus") : html.index("async function fetchLatestBriefingForThread")]
    assert "await showHITLById" not in poll
    assert "setTimeout" in poll
    assert "function setReadOverlayVisible" in html
    show_detail = html[html.index("async function showBriefingDetail") : html.index("function renderBriefingDetail")]
    assert "setReadOverlayVisible(true)" in show_detail
    assert "Running Intelligence Pipeline" not in show_detail
    assert "cdn.tailwindcss.com" not in html
    assert 'href="tailwind.built.css"' in html
    assert "@phosphor-icons/web" in html and "defer" in html
    assert "fonts.googleapis.com/css2?family=Inter" in html
    assert "@import url('https://fonts.googleapis.com" not in html


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
    cfg = invoke.call_args[0][1]
    assert cfg["configurable"]["thread_id"] == thread_id
    assert cfg["run_name"] == "signal-pipeline"
    assert cfg["metadata"]["thread_id"] == thread_id
    assert cfg["callbacks"]


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
    cfg = invoke.call_args[0][1]
    assert cfg["configurable"]["thread_id"] == thread_id
    assert cfg["run_name"] == "signal-pipeline"
    assert cfg["callbacks"]
