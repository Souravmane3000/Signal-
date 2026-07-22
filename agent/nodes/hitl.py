"""HITL interrupt node — pauses after Synthesis for human approve/edit/reject."""

from __future__ import annotations

from typing import Any

from langgraph.types import interrupt

from agent.state import SignalState

_VALID_DECISIONS = frozenset({"approve", "edit", "reject"})


def hitl_node(state: SignalState) -> dict:
    """Pause for human review of the synthesized briefing.

    Uses LangGraph ``interrupt()``. On resume, the resume value is the decision
    (``approve`` | ``edit`` | ``reject``), optionally wrapped as
    ``{"action": ..., "edits": ...}``.
    """
    payload = {
        "briefing_draft": state.get("briefing_draft", ""),
        "briefing_final": state.get("briefing_final", ""),
        "briefing_items": state.get("briefing_items", []),
        "run_id": state.get("run_id", ""),
    }

    decision_raw: Any = interrupt(payload)

    edits = None
    if isinstance(decision_raw, dict):
        action = decision_raw.get("action") or decision_raw.get("decision")
        edits = decision_raw.get("edits")
    else:
        action = decision_raw

    if action not in _VALID_DECISIONS:
        raise ValueError(
            f"Invalid HITL decision: {action!r}. "
            "Expected one of: approve, edit, reject."
        )

    update: dict = {"hitl_decision": action}

    if action == "edit":
        if edits is not None:
            update["hitl_edits"] = edits
        if isinstance(edits, dict) and "briefing_final" in edits:
            update["briefing_final"] = edits["briefing_final"]

    return update


def route_after_hitl(state: SignalState) -> str:
    """DEC-004: Approve/Edit → episodic memory; Reject → discard (no episodic write)."""
    decision = state.get("hitl_decision")
    if decision in ("approve", "edit"):
        return "episodic_memory_writer"
    return "discard_and_log"
