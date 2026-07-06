"""Run metrics writer — Phase 1 stub (Week 1)."""

from __future__ import annotations

from typing import Any

from agent.state import SignalState


def run_metrics_writer(state: SignalState) -> dict[str, Any]:
    findings = state.get("deduped_findings") or []
    metrics = {
        "finding_count": len(findings),
        "entity_count": len(state.get("entities") or []),
        "error_count": len(state.get("errors") or []),
    }
    return {"metrics": metrics}
