"""Hybrid deduplication across validated findings."""

from __future__ import annotations

from typing import Any

from agent.state import DEDUP_SIMILARITY_THRESHOLD, SignalState, ValidatedFinding


def hybrid_dedup(state: SignalState) -> dict[str, Any]:
    _ = DEDUP_SIMILARITY_THRESHOLD
    seen_urls: set[str] = set()
    deduped: list[ValidatedFinding] = []

    for finding in state.get("validated_findings") or []:
        url = finding.get("url", "")
        if url and url in seen_urls:
            continue
        if url:
            seen_urls.add(url)
        deduped.append(finding)

    return {"deduped_findings": deduped}
