"""Stale-connection retry must resume from checkpoint, not replay initial_state."""

from unittest.mock import MagicMock, patch

from langgraph.types import Command
from psycopg import OperationalError

from agent.graph import (
    _invoke_with_stale_conn_retry,
    _recovery_input,
)


def test_recovery_input_uses_none_when_checkpoint_exists():
    """Mid-run failure: resume with None so completed nodes are not re-executed."""
    config = {"configurable": {"thread_id": "t_recovery"}}
    initial = {"run_id": "r1", "raw_findings": []}
    snap = MagicMock()
    snap.values = {"run_id": "r1", "briefing_draft": "partial"}
    snap.next = ("delivery",)
    snap.tasks = ()

    with patch("agent.graph.graph.get_state", return_value=snap):
        assert _recovery_input(initial, config) is None


def test_recovery_input_keeps_command_when_interrupt_still_pending():
    """HITL Command must be re-sent if OperationalError hit before resume applied."""
    config = {"configurable": {"thread_id": "t_hitl"}}
    cmd = Command(resume="approve")
    task = MagicMock()
    task.interrupts = (MagicMock(),)
    snap = MagicMock()
    snap.values = {"run_id": "r1"}
    snap.next = ("hitl_node",)
    snap.tasks = (task,)

    with patch("agent.graph.graph.get_state", return_value=snap):
        assert _recovery_input(cmd, config) is cmd


def test_recovery_input_uses_none_after_interrupt_cleared():
    """Past HITL: checkpoint resume with None — do not re-send Command."""
    config = {"configurable": {"thread_id": "t_past_hitl"}}
    cmd = Command(resume="approve")
    snap = MagicMock()
    snap.values = {"run_id": "r1", "hitl_decision": "approve"}
    snap.next = ("delivery",)
    snap.tasks = ()

    with patch("agent.graph.graph.get_state", return_value=snap):
        assert _recovery_input(cmd, config) is None


def test_recovery_input_replays_original_only_when_no_checkpoint():
    """Pre-first-checkpoint failure: original input is the only valid retry."""
    config = {"configurable": {"thread_id": "t_empty"}}
    initial = {"run_id": "r1"}
    snap = MagicMock()
    snap.values = {}
    snap.next = ()
    snap.tasks = ()

    with patch("agent.graph.graph.get_state", return_value=snap):
        assert _recovery_input(initial, config) is initial


def test_stale_conn_retry_resumes_from_checkpoint_not_initial_state():
    """Proof: second invoke receives None, never the original initial_state."""
    config = {"configurable": {"thread_id": "t_retry_proof"}}
    initial = {
        "run_id": "duplicate-risk",
        "raw_findings": [{"title": "would be re-fetched"}],
        "tokens_used": 0,
    }
    snap = MagicMock()
    snap.values = {
        "run_id": "duplicate-risk",
        "tokens_used": 1200,
        "briefing_draft": "## already synthesized",
    }
    snap.next = ("hitl_node",)
    snap.tasks = ()

    final = {"run_id": "duplicate-risk", "briefing_final": "done"}

    with (
        patch("agent.graph._ensure_pool_healthy"),
        patch("agent.graph.graph.get_state", return_value=snap),
        patch(
            "agent.graph.graph.invoke",
            side_effect=[OperationalError("SSL SYSCALL error: EOF detected"), final],
        ) as invoke,
    ):
        result = _invoke_with_stale_conn_retry(initial, config)

    assert result is final
    assert invoke.call_count == 2
    assert invoke.call_args_list[0].args[0] is initial
    assert invoke.call_args_list[1].args[0] is None
    assert invoke.call_args_list[1].args[1] == config
    # Explicit anti-replay proof
    assert invoke.call_args_list[1].args[0] is not initial


def test_stale_conn_retry_resends_command_only_while_interrupt_pending():
    config = {"configurable": {"thread_id": "t_cmd_retry"}}
    cmd = Command(resume="approve")
    task = MagicMock()
    task.interrupts = (MagicMock(),)
    snap = MagicMock()
    snap.values = {"run_id": "r1"}
    snap.next = ("hitl_node",)
    snap.tasks = (task,)
    final = {"run_id": "r1", "delivery_status": "sent"}

    with (
        patch("agent.graph._ensure_pool_healthy"),
        patch("agent.graph.graph.get_state", return_value=snap),
        patch(
            "agent.graph.graph.invoke",
            side_effect=[OperationalError("connection is bad"), final],
        ) as invoke,
    ):
        result = _invoke_with_stale_conn_retry(cmd, config)

    assert result is final
    assert invoke.call_args_list[1].args[0] is cmd


def test_invoke_clears_live_node_when_graph_returns():
    from agent.graph import clear_live_node, get_live_node, set_live_node

    config = {"configurable": {"thread_id": "t_live_clear"}}
    set_live_node("t_live_clear", "tavily_search")
    assert get_live_node("t_live_clear") == "tavily_search"
    with (
        patch("agent.graph._ensure_pool_healthy"),
        patch("agent.graph.graph.invoke", return_value={"run_id": "r1"}),
    ):
        _invoke_with_stale_conn_retry(None, config)
    assert get_live_node("t_live_clear") is None
    clear_live_node("t_live_clear")
