"""Sample findings for unit and integration tests (Session 0.5)."""

from __future__ import annotations

from agent.state import RawFinding, ValidatedFinding

SAMPLE_RAW_FINDINGS: list[RawFinding] = [
    {
        "id": "finding-001",
        "title": "Acme Corp raises Series B",
        "url": "https://example.com/acme-series-b",
        "snippet": "Acme Corp announced a $50M Series B led by Example Ventures.",
        "source": "tavily",
        "published_at": "2026-06-01T00:00:00Z",
    },
    {
        "id": "finding-002",
        "title": "Show HN: New developer tool for LLM agents",
        "url": "https://news.ycombinator.com/item?id=123456",
        "snippet": "We built an open-source framework for orchestrating research agents.",
        "source": "hn_algolia",
        "published_at": "2026-06-10T12:00:00Z",
    },
]

SAMPLE_VALIDATED_FINDINGS: list[ValidatedFinding] = [
    {
        **SAMPLE_RAW_FINDINGS[0],
        "freshness_score": 0.95,
        "trust_score": 0.7,
        "entities": ["Acme Corp", "Example Ventures"],
        "in_scope": True,
    },
    {
        **SAMPLE_RAW_FINDINGS[1],
        "freshness_score": 0.99,
        "trust_score": 1.0,
        "entities": [],
        "in_scope": True,
    },
]
