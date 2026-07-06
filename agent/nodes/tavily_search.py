"""Tavily web search node."""

from __future__ import annotations

from typing import Any

from agent.state import RawFinding, SignalState


def tavily_search(state: SignalState) -> dict[str, Any]:
    # TODO: implement Tavily API integration
    _ = state
    return {"raw_findings": []}
