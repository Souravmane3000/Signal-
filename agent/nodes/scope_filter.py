"""Filter findings to configured scope."""

from __future__ import annotations

from typing import Any

from agent.state import SignalState, ValidatedFinding


def scope_filter(state: SignalState) -> dict[str, Any]:
    config = state.get("config") or {}
    scope_keywords: list[str] = config.get("scope_keywords") or []

    filtered: list[ValidatedFinding] = []
    for finding in state.get("validated_findings") or []:
        in_scope = True
        if scope_keywords:
            text = f"{finding.get('title', '')} {finding.get('snippet', '')}".lower()
            in_scope = any(kw.lower() in text for kw in scope_keywords)
        filtered.append({**finding, "in_scope": in_scope})

    return {"validated_findings": filtered}
