"""Plan search queries across configured sources."""

from __future__ import annotations

from typing import Any

from agent.state import SearchQuery, SignalState, SUPPORTED_SOURCES


def search_planner(state: SignalState) -> dict[str, Any]:
    config = state.get("config") or {}
    topic = config.get("topic", "")

    plan: list[SearchQuery] = []
    for idx, source in enumerate(SUPPORTED_SOURCES):
        if topic:
            plan.append({"query": topic, "source": source, "priority": idx})

    return {"search_plan": plan}
