"""Reject-path node — discard briefing without writing episodic memory (DEC-004)."""

from agent.state import SignalState


def discard_and_log(state: SignalState) -> dict:
    run_id = state.get("run_id", "")
    print(
        f"Briefing rejected for run {run_id} — discarding findings; "
        "episodic memory will not be written (DEC-004)."
    )
    return {"delivery_status": "rejected"}
