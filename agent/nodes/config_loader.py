"""Config Loader — Phase 2: Supabase user_configs + PostgresStore memory reads."""

from __future__ import annotations

import os
from datetime import datetime, timezone
from typing import Any, Optional

import httpx
from dotenv import load_dotenv

from agent.state import SignalState

# Phase 1 defaults — used when no user_configs row exists (onboarding incomplete).
_DEFAULT_USER_CONFIG: dict[str, Any] = {
    "user_id": "user_001",
    "keywords": [
        "Indian startup",
        "funding India",
        "seed round India",
        "Series A India",
    ],
    "verticals": ["AI", "fintech", "healthtech", "B2B SaaS", "climate", "edtech"],
    "stage_filter": ["seed", "series_a", "series_b"],
    "delivery_email": "test@example.com",
    "schedule_freq": "weekly",
}

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

# Matches SIG procedural-memory updater: store.put(..., key="preferences", ...)
_PROCEDURAL_KEY = "preferences"
_SEMANTIC_KEY = "memory"


def _require_supabase_env() -> tuple[str, str]:
    """Fail fast if Supabase credentials are missing (SIG-002B stop condition)."""
    url = os.getenv("SUPABASE_URL")
    key = os.getenv("SUPABASE_SERVICE_KEY")
    if not url or not key:
        raise RuntimeError(
            "SUPABASE_URL or SUPABASE_SERVICE_KEY missing from .env. "
            "SIG-002B stop condition: cannot load user_configs."
        )
    return url.rstrip("/"), key


def _get_postgres_store():
    """Reuse the PostgresStore created in SIG-P2-002. Do not open a second store."""
    try:
        from agent.graph import _postgres_store
    except Exception as exc:  # pragma: no cover - import/wiring failure
        raise RuntimeError(
            "PostgresStore unavailable (SIG-P2-002 not complete). "
            "SIG-002B stop condition."
        ) from exc
    if _postgres_store is None:
        raise RuntimeError(
            "PostgresStore unavailable (SIG-P2-002 not complete). "
            "SIG-002B stop condition."
        )
    return _postgres_store


def _fetch_user_config_row(user_id: str, supabase_url: str, service_key: str) -> Optional[dict]:
    """Read user_configs via Supabase REST. Returns None if absent or on read error."""
    headers = {
        "apikey": service_key,
        "Authorization": f"Bearer {service_key}",
        "Accept": "application/json",
    }
    try:
        response = httpx.get(
            f"{supabase_url}/rest/v1/user_configs",
            params={"user_id": f"eq.{user_id}", "select": "*"},
            headers=headers,
            timeout=10.0,
        )
        response.raise_for_status()
        rows = response.json()
        if not rows:
            return None
        return rows[0]
    except Exception:
        # Missing row, type mismatch, network blip — fall back to defaults.
        return None


def _row_to_user_config(row: dict, fallback_user_id: str) -> dict[str, Any]:
    """Map a user_configs row onto the Phase 1 user_config dict shape."""
    return {
        "user_id": str(row["user_id"]) if row.get("user_id") is not None else fallback_user_id,
        "keywords": list(row["keywords"])
        if row.get("keywords") is not None
        else list(_DEFAULT_USER_CONFIG["keywords"]),
        "verticals": list(row["verticals"])
        if row.get("verticals") is not None
        else list(_DEFAULT_USER_CONFIG["verticals"]),
        "stage_filter": list(row["stage_filter"])
        if row.get("stage_filter") is not None
        else list(_DEFAULT_USER_CONFIG["stage_filter"]),
        "delivery_email": row["delivery_email"]
        if row.get("delivery_email") is not None
        else _DEFAULT_USER_CONFIG["delivery_email"],
        "schedule_freq": row["schedule_freq"]
        if row.get("schedule_freq") is not None
        else _DEFAULT_USER_CONFIG["schedule_freq"],
    }


def _load_store_dict(store, namespace: tuple[str, ...], key: str) -> Optional[dict]:
    """Return the dict value at namespace/key, or None if missing/invalid."""
    item = store.get(namespace, key)
    if item is None:
        return None
    value = item.value
    if isinstance(value, dict):
        return value
    return None


def config_loader(state: SignalState) -> dict:
    load_dotenv()

    supabase_url, service_key = _require_supabase_env()
    store = _get_postgres_store()

    user_id = state.get("user_id") or _DEFAULT_USER_CONFIG["user_id"]

    row = _fetch_user_config_row(user_id, supabase_url, service_key)
    if row is not None:
        user_config = _row_to_user_config(row, user_id)
        user_id = user_config["user_id"]
    else:
        user_config = {**_DEFAULT_USER_CONFIG, "user_id": user_id}

    procedural_memory = _load_store_dict(
        store, ("user", user_id, "procedural"), _PROCEDURAL_KEY
    )
    if procedural_memory is None:
        procedural_memory = dict(_DEFAULT_PROCEDURAL_MEMORY)

    semantic_memory = _load_store_dict(
        store, ("user", user_id, "semantic"), _SEMANTIC_KEY
    )
    if semantic_memory is None:
        semantic_memory = {}

    return {
        "user_config": user_config,
        "user_id": user_id,
        "thread_id": "run_" + str(int(datetime.now(timezone.utc).timestamp())),
        "run_type": "manual",
        "graph_version": os.getenv("GRAPH_VERSION", "1.0"),
        "semantic_memory": semantic_memory,
        "procedural_memory": procedural_memory,
        "source_failures": {
            "tavily": False,
            "yc": False,
            "hn": False,
            "rss": False,
        },
    }
