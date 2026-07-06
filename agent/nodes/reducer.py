"""Merge raw findings from parallel search nodes."""

from __future__ import annotations

from typing import Any

from agent.state import RawFinding, SignalState


def reducer(state: SignalState) -> dict[str, Any]:
    findings: list[RawFinding] = list(state.get("raw_findings") or [])
    return {"raw_findings": findings}
