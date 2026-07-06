"""Synthesize final output from deduped findings and entities."""

from __future__ import annotations

from typing import Any

from agent.state import SignalState, SynthesisOutput


def synthesis(state: SignalState) -> dict[str, Any]:
    findings = state.get("deduped_findings") or []
    entities = state.get("entities") or []

    output: SynthesisOutput = {
        "summary": "",
        "key_entities": [e.get("name", "") for e in entities if e.get("name")],
        "sources": [f.get("url", "") for f in findings if f.get("url")],
        "confidence": 0.0,
    }
    return {"synthesis": output}
