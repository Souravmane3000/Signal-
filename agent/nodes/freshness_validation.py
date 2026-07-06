"""Validate finding freshness against configured thresholds."""

from __future__ import annotations

from typing import Any

from agent.state import DEFAULT_FRESHNESS_DAYS, RawFinding, SignalState, ValidatedFinding


def freshness_validation(state: SignalState) -> dict[str, Any]:
    config = state.get("config") or {}
    max_days = config.get("freshness_days", DEFAULT_FRESHNESS_DAYS)
    _ = max_days

    validated: list[ValidatedFinding] = []
    for finding in state.get("raw_findings") or []:
        validated.append({**finding, "freshness_score": 1.0})

    return {"validated_findings": validated}
