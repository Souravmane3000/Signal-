"""Tests for Config Loader — Phase 1 contract + Phase 2 Supabase/Store reads."""

from __future__ import annotations

import os
from unittest.mock import MagicMock, patch

from agent.nodes.config_loader import (
    _DEFAULT_PROCEDURAL_MEMORY,
    _DEFAULT_USER_CONFIG,
    _PROCEDURAL_KEY,
    _SEMANTIC_KEY,
    config_loader,
)

EXPECTED_KEYS = {
    "user_config",
    "user_id",
    "thread_id",
    "run_type",
    "graph_version",
    "semantic_memory",
    "procedural_memory",
    "source_failures",
}


def test_config_loader_fallback_defaults():
    """No user_configs row → Phase 1 defaults; empty semantic; default procedural."""
    result = config_loader({})

    assert set(result.keys()) == EXPECTED_KEYS
    assert result["user_id"] == "user_001"
    assert result["thread_id"].startswith("run_")
    assert result["run_type"] == "manual"
    assert result["graph_version"] == os.getenv("GRAPH_VERSION", "1.0")
    assert result["source_failures"] == {
        "tavily": False,
        "yc": False,
        "hn": False,
        "rss": False,
    }
    assert result["semantic_memory"] == {}
    assert "high_signal_categories" in result["procedural_memory"]
    assert result["user_config"]["keywords"] == _DEFAULT_USER_CONFIG["keywords"]
    print("Config loader fallback test passed.")


def test_config_loader_uses_state_user_id():
    result = config_loader({"user_id": "user_001"})
    assert result["user_id"] == "user_001"
    assert set(result.keys()) == EXPECTED_KEYS
    print("Config loader state user_id test passed.")


def test_config_loader_loads_row_when_present():
    fake_row = {
        "user_id": "user_001",
        "keywords": ["custom keyword"],
        "verticals": ["AI"],
        "stage_filter": ["seed"],
        "delivery_email": "founder@example.com",
        "schedule_freq": "daily",
    }
    mock_response = MagicMock()
    mock_response.raise_for_status = MagicMock()
    mock_response.json.return_value = [fake_row]

    with patch("agent.nodes.config_loader.httpx.get", return_value=mock_response) as mocked:
        result = config_loader({"user_id": "user_001"})

    mocked.assert_called_once()
    assert result["user_config"]["keywords"] == ["custom keyword"]
    assert result["user_config"]["delivery_email"] == "founder@example.com"
    assert result["user_config"]["schedule_freq"] == "daily"
    assert result["user_id"] == "user_001"
    print("Config loader row-present test passed.")


def test_config_loader_supabase_error_falls_back():
    with patch(
        "agent.nodes.config_loader.httpx.get",
        side_effect=RuntimeError("network down"),
    ):
        result = config_loader({"user_id": "user_001"})

    assert result["user_config"]["keywords"] == _DEFAULT_USER_CONFIG["keywords"]
    assert result["semantic_memory"] == {}
    print("Config loader supabase-error fallback test passed.")


def test_config_loader_loads_memory_from_store():
    from agent.graph import _postgres_store as store

    user_id = "user_001"
    procedural = {
        **_DEFAULT_PROCEDURAL_MEMORY,
        "query_boost_terms": ["StoreLoadedBoost"],
    }
    semantic = {"seen_urls": ["https://example.com/a"], "seen_titles": ["Alpha"]}

    store.put(("user", user_id, "procedural"), _PROCEDURAL_KEY, procedural)
    store.put(("user", user_id, "semantic"), _SEMANTIC_KEY, semantic)
    try:
        with patch(
            "agent.nodes.config_loader._fetch_user_config_row",
            return_value=None,
        ):
            result = config_loader({"user_id": user_id})

        assert result["procedural_memory"]["query_boost_terms"] == ["StoreLoadedBoost"]
        assert result["semantic_memory"]["seen_urls"] == ["https://example.com/a"]
    finally:
        store.delete(("user", user_id, "procedural"), _PROCEDURAL_KEY)
        store.delete(("user", user_id, "semantic"), _SEMANTIC_KEY)

    print("Config loader store-memory test passed.")


def test_config_loader_does_not_write_memory():
    from agent.graph import _postgres_store as store

    user_id = "sig002b_nowrite_user"
    before = store.search(("user", user_id, "procedural"), limit=10)
    before_sem = store.search(("user", user_id, "semantic"), limit=10)

    with patch(
        "agent.nodes.config_loader._fetch_user_config_row",
        return_value=None,
    ):
        config_loader({"user_id": user_id})

    after = store.search(("user", user_id, "procedural"), limit=10)
    after_sem = store.search(("user", user_id, "semantic"), limit=10)
    assert len(after) == len(before)
    assert len(after_sem) == len(before_sem)
    print("Config loader no-write test passed.")


def test_config_loader_missing_env_fails_fast():
    real_getenv = os.getenv

    def fake_getenv(key, default=None):
        if key in ("SUPABASE_URL", "SUPABASE_SERVICE_KEY"):
            return None
        return real_getenv(key, default)

    with patch("agent.nodes.config_loader.load_dotenv"):
        with patch("agent.nodes.config_loader.os.getenv", side_effect=fake_getenv):
            try:
                config_loader({})
                raise AssertionError("expected RuntimeError for missing Supabase env")
            except RuntimeError as exc:
                assert "SUPABASE" in str(exc)
    print("Config loader missing-env fail-fast test passed.")


def test_config_loader_preserves_thread_id():
    tid = "run_custom_123"
    result = config_loader({"thread_id": tid})
    assert result["thread_id"] == tid
    print("Config loader preserve thread_id test passed.")


if __name__ == "__main__":
    test_config_loader_fallback_defaults()
    test_config_loader_uses_state_user_id()
    test_config_loader_loads_row_when_present()
    test_config_loader_supabase_error_falls_back()
    test_config_loader_loads_memory_from_store()
    test_config_loader_does_not_write_memory()
    test_config_loader_missing_env_fails_fast()
    test_config_loader_preserves_thread_id()
    print("All config loader tests passed.")
