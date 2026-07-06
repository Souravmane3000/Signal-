"""Score source trust for validated findings."""

from __future__ import annotations

from typing import Any

from agent.state import SignalState, TRUST_SCORE_THRESHOLD, ValidatedFinding


def source_trust_scoring(state: SignalState) -> dict[str, Any]:
    scored: list[ValidatedFinding] = []
    for finding in state.get("validated_findings") or []:
        trust = 1.0 if finding.get("source") in ("yc", "hn_algolia") else 0.7
        if trust >= TRUST_SCORE_THRESHOLD:
            scored.append({**finding, "trust_score": trust})

    return {"validated_findings": scored}
