"""Procedural Memory Updater — deterministic feedback aggregation (SIG-023 / DEC-007).

No LLM. No embeddings. No prompt rewriting.
Minimum 5 feedback signals before any Store write.
Source weights floored at 0.3.
"""

from __future__ import annotations

from collections import Counter
from typing import Any

from agent.memory.feedback_store import fetch_all_feedback_for_user
from agent.state import SignalState

_PROCEDURAL_KEY = "preferences"
_MIN_FEEDBACK_SIGNALS = 5
_RATIO_THRESHOLD = 0.60
_SOURCE_WEIGHT_FLOOR = 0.3
_MAX_BOOST_TERMS = 10

# Entity fields counted into query_boost_terms (deterministic string extraction only).
_ENTITY_TERM_FIELDS = (
    "company_name",
    "company_name_normalized",
    "sector",
    "location",
    "founder_name",
)

_DEFAULT_PROCEDURAL_MEMORY: dict[str, Any] = {
    "high_signal_categories": ["funding", "accelerator"],
    "low_signal_categories": [],
    "trusted_sources": ["inc42", "yc"],
    "preferred_stage": ["seed", "series_a"],
    "query_boost_terms": ["Bengaluru", "B2B SaaS"],
    "query_suppress_terms": ["Infosys", "Wipro", "IT services"],
    "source_weights": {
        "tavily": 1.0,
        "yc": 1.0,
        "hn": 0.7,
        "google_news": 0.65,
    },
    "min_confidence_threshold": 0.70,
}


def _get_postgres_store():
    """Reuse the PostgresStore from SIG-P2-002. Do not open a second store."""
    from agent.graph import _postgres_store

    if _postgres_store is None:
        raise RuntimeError("PostgresStore unavailable (SIG-P2-002 not complete).")
    return _postgres_store


def _category_ratios(feedback_rows: list[dict]) -> tuple[list[str], list[str]]:
    """Compute high/low signal categories from useful / not_relevant ratios."""
    totals: Counter[str] = Counter()
    useful: Counter[str] = Counter()
    not_relevant: Counter[str] = Counter()

    for row in feedback_rows:
        category = row.get("category")
        if not category:
            continue
        key = str(category)
        totals[key] += 1
        fb = row.get("feedback")
        if fb == "useful":
            useful[key] += 1
        elif fb == "not_relevant":
            not_relevant[key] += 1

    high: list[str] = []
    low: list[str] = []
    for category, total in totals.items():
        if total <= 0:
            continue
        useful_ratio = useful[category] / total
        not_relevant_ratio = not_relevant[category] / total
        if useful_ratio > _RATIO_THRESHOLD:
            high.append(category)
        if not_relevant_ratio > _RATIO_THRESHOLD:
            low.append(category)

    return sorted(high), sorted(low)


def _source_weights(
    feedback_rows: list[dict], base_weights: dict[str, float]
) -> dict[str, float]:
    """Per-source useful ratio, floored at 0.3 (DEC-007)."""
    totals: Counter[str] = Counter()
    useful: Counter[str] = Counter()

    for row in feedback_rows:
        source = row.get("source_name")
        if not source:
            continue
        key = str(source)
        totals[key] += 1
        if row.get("feedback") == "useful":
            useful[key] += 1

    updated = {k: float(v) for k, v in base_weights.items()}
    for source in sorted(totals.keys()):
        total = totals[source]
        ratio = useful[source] / total if total > 0 else 0.0
        weight = max(_SOURCE_WEIGHT_FLOOR, ratio)
        if weight < _SOURCE_WEIGHT_FLOOR:
            raise RuntimeError(
                f"DEC-007 violation: source weight {weight} < {_SOURCE_WEIGHT_FLOOR}"
            )
        updated[source] = weight
    # Stable key order for identical payloads across runs.
    return {k: updated[k] for k in sorted(updated.keys())}


def _entity_terms_from_row(row: dict) -> list[str]:
    """Extract plain string terms from an optional entities dict on a feedback row."""
    entities = row.get("entities")
    if not isinstance(entities, dict):
        return []
    terms: list[str] = []
    for field in _ENTITY_TERM_FIELDS:
        value = entities.get(field)
        if isinstance(value, str) and value.strip():
            terms.append(value.strip())
    investor_names = entities.get("investor_names") or []
    if isinstance(investor_names, list):
        for name in investor_names:
            if isinstance(name, str) and name.strip():
                terms.append(name.strip())
    return terms


def _query_boost_terms(
    feedback_rows: list[dict], existing: list[str]
) -> list[str]:
    """Count terms from useful feedback entities; fall back to existing list."""
    counts: Counter[str] = Counter()
    for row in feedback_rows:
        if row.get("feedback") != "useful":
            continue
        for term in _entity_terms_from_row(row):
            counts[term] += 1

    if not counts:
        return list(existing)

    # Rank by count desc, then term asc — deterministic ties (no wall-clock / random).
    ranked = sorted(counts.keys(), key=lambda t: (-counts[t], t))
    return ranked[:_MAX_BOOST_TERMS]


def _build_updated_memory(
    feedback_rows: list[dict], base: dict[str, Any]
) -> dict[str, Any]:
    high, low = _category_ratios(feedback_rows)
    base_weights = dict(base.get("source_weights") or {})
    weights = _source_weights(feedback_rows, base_weights)
    boost = _query_boost_terms(
        feedback_rows, list(base.get("query_boost_terms") or [])
    )

    updated = dict(base)
    # Preference payload is pure aggregation — no wall-clock / UUID metadata.
    updated.pop("last_updated", None)
    updated["high_signal_categories"] = high
    updated["low_signal_categories"] = low
    updated["source_weights"] = weights
    updated["query_boost_terms"] = boost
    return updated


def procedural_memory_updater(state: SignalState) -> dict:
    """Aggregate user feedback into procedural memory when ≥5 signals exist.

    Side-effect: store.put under ("user", user_id, "procedural") / preferences.
    Returns {} always (no SignalState field writes required for next-run contract —
    Config Loader reads the Store on the subsequent run).
    """
    user_id = state.get("user_id") or "user_001"
    all_feedback = fetch_all_feedback_for_user(user_id)

    if len(all_feedback) < _MIN_FEEDBACK_SIGNALS:
        print(
            f"Procedural memory: {len(all_feedback)} signals "
            f"(need {_MIN_FEEDBACK_SIGNALS}) — no update"
        )
        return {}

    base = state.get("procedural_memory") or {}
    if not isinstance(base, dict) or not base:
        base = dict(_DEFAULT_PROCEDURAL_MEMORY)

    updated = _build_updated_memory(all_feedback, base)

    for _source, weight in updated["source_weights"].items():
        if float(weight) < _SOURCE_WEIGHT_FLOOR:
            raise RuntimeError(
                f"DEC-007 violation: source weight {weight} below floor "
                f"{_SOURCE_WEIGHT_FLOOR}"
            )

    store = _get_postgres_store()
    namespace = ("user", user_id, "procedural")
    store.put(namespace, _PROCEDURAL_KEY, updated)

    print(
        f"Procedural memory updated for user {user_id}: "
        f"{len(all_feedback)} signals, "
        f"high={updated['high_signal_categories']}, "
        f"low={updated['low_signal_categories']}"
    )
    return {}
