"""Feedback Collector — persist human feedback only (SIG-022).

Does not analyze feedback. Does not update procedural/semantic/episodic memory.
Does not call an LLM. Does not mutate SignalState fields.
"""

from __future__ import annotations

from agent.memory.feedback_store import insert_feedback
from agent.state import SignalState


def feedback_collector(state: SignalState) -> dict:
    """Persist optional pending_feedback entries into user_feedback.

    Expected pending_feedback item shape (schema-aligned):
      {
        "briefing_item_id": optional uuid str,
        "category": optional str,
        "source_name": optional str,
        "feedback": "useful" | "not_relevant",
        "reason": optional reason str,
      }

    If pending_feedback is absent or empty, this is a no-op.
    """
    pending = state.get("pending_feedback") or []
    if not pending:
        return {}

    user_id = state.get("user_id") or ""
    for entry in pending:
        if not isinstance(entry, dict):
            raise TypeError(
                f"pending_feedback entries must be dicts, got {type(entry).__name__}"
            )
        feedback_value = entry.get("feedback")
        if not feedback_value:
            raise ValueError("pending_feedback entry missing required 'feedback' field")
        try:
            insert_feedback(
                user_id=user_id,
                feedback=str(feedback_value),
                briefing_item_id=entry.get("briefing_item_id"),
                category=entry.get("category"),
                source_name=entry.get("source_name"),
                reason=entry.get("reason"),
            )
        except Exception as exc:
            print(f"ERROR: feedback_collector persistence failed: {exc}")
            # Do not swallow — surface node failure (SIG-022).
            raise

    print(f"Feedback collector wrote {len(pending)} item(s) for user {user_id}")
    return {}
