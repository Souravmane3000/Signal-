"""SIG-023 — Procedural Memory Updater tests (deterministic / DEC-007)."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

from agent.nodes.config_loader import _PROCEDURAL_KEY
from agent.nodes.procedural_memory_updater import (
    _SOURCE_WEIGHT_FLOOR,
    _build_updated_memory,
    procedural_memory_updater,
)
from agent.nodes.search_planner import search_planner


def _fb(
    *,
    feedback: str,
    category: str | None = None,
    source_name: str | None = None,
    entities: dict | None = None,
) -> dict:
    row: dict = {"feedback": feedback}
    if category is not None:
        row["category"] = category
    if source_name is not None:
        row["source_name"] = source_name
    if entities is not None:
        row["entities"] = entities
    return row


def test_below_threshold_no_update_no_store_write():
    """<5 feedback → return {}, no store.put."""
    feedback = [
        _fb(feedback="useful", category="funding", source_name="inc42"),
        _fb(feedback="useful", category="funding", source_name="inc42"),
        _fb(feedback="not_relevant", category="hiring", source_name="hn"),
        _fb(feedback="useful", category="accelerator", source_name="yc"),
    ]
    assert len(feedback) == 4

    mock_store = MagicMock()
    with patch(
        "agent.nodes.procedural_memory_updater.fetch_all_feedback_for_user",
        return_value=feedback,
    ), patch(
        "agent.nodes.procedural_memory_updater._get_postgres_store",
        return_value=mock_store,
    ):
        result = procedural_memory_updater({"user_id": "user_001"})

    assert result == {}
    mock_store.put.assert_not_called()


def test_exactly_five_triggers_update():
    """Exactly 5 signals → update fires, store.put once."""
    feedback = [
        _fb(feedback="useful", category="funding", source_name="inc42"),
        _fb(feedback="useful", category="funding", source_name="inc42"),
        _fb(feedback="useful", category="funding", source_name="inc42"),
        _fb(feedback="not_relevant", category="hiring", source_name="hn"),
        _fb(feedback="not_relevant", category="hiring", source_name="hn"),
    ]
    assert len(feedback) == 5

    mock_store = MagicMock()
    with patch(
        "agent.nodes.procedural_memory_updater.fetch_all_feedback_for_user",
        return_value=feedback,
    ), patch(
        "agent.nodes.procedural_memory_updater._get_postgres_store",
        return_value=mock_store,
    ):
        result = procedural_memory_updater(
            {
                "user_id": "user_001",
                "procedural_memory": {
                    "high_signal_categories": [],
                    "low_signal_categories": [],
                    "source_weights": {"tavily": 1.0, "hn": 0.7},
                    "query_boost_terms": ["Bengaluru"],
                    "query_suppress_terms": ["Infosys"],
                    "trusted_sources": ["inc42"],
                    "preferred_stage": ["seed"],
                    "min_confidence_threshold": 0.70,
                },
            }
        )

    assert result == {}
    mock_store.put.assert_called_once()
    namespace, key, value = mock_store.put.call_args.args
    assert namespace == ("user", "user_001", "procedural")
    assert key == "preferences"
    assert "funding" in value["high_signal_categories"]
    assert "hiring" in value["low_signal_categories"]
    assert "last_updated" not in value


def test_category_ratios_computed_correctly():
    """useful >60% → high; not_relevant >60% → low."""
    # funding: 3/4 useful = 0.75 > 0.60 → high
    # hiring: 3/4 not_relevant = 0.75 > 0.60 → low
    # pivot: 1/2 useful = 0.50 → neither
    feedback = [
        _fb(feedback="useful", category="funding", source_name="inc42"),
        _fb(feedback="useful", category="funding", source_name="inc42"),
        _fb(feedback="useful", category="funding", source_name="inc42"),
        _fb(feedback="not_relevant", category="funding", source_name="inc42"),
        _fb(feedback="not_relevant", category="hiring", source_name="hn"),
        _fb(feedback="not_relevant", category="hiring", source_name="hn"),
        _fb(feedback="not_relevant", category="hiring", source_name="hn"),
        _fb(feedback="useful", category="hiring", source_name="hn"),
        _fb(feedback="useful", category="pivot", source_name="yc"),
        _fb(feedback="not_relevant", category="pivot", source_name="yc"),
    ]
    updated = _build_updated_memory(
        feedback,
        {
            "source_weights": {},
            "query_boost_terms": [],
        },
    )
    assert updated["high_signal_categories"] == ["funding"]
    assert updated["low_signal_categories"] == ["hiring"]
    assert "pivot" not in updated["high_signal_categories"]
    assert "pivot" not in updated["low_signal_categories"]


def test_source_weight_floor_never_below_0_3():
    """All-not_relevant source still gets weight >= 0.3."""
    feedback = [
        _fb(feedback="not_relevant", category="hiring", source_name="hn"),
        _fb(feedback="not_relevant", category="hiring", source_name="hn"),
        _fb(feedback="not_relevant", category="hiring", source_name="hn"),
        _fb(feedback="not_relevant", category="hiring", source_name="hn"),
        _fb(feedback="useful", category="funding", source_name="inc42"),
    ]
    updated = _build_updated_memory(
        feedback,
        {"source_weights": {"tavily": 1.0, "hn": 0.7}, "query_boost_terms": []},
    )
    assert updated["source_weights"]["hn"] == _SOURCE_WEIGHT_FLOOR
    assert updated["source_weights"]["hn"] >= 0.3
    assert updated["source_weights"]["inc42"] == 1.0
    assert updated["source_weights"]["tavily"] == 1.0  # preserved


def test_query_boost_terms_from_useful_entities():
    feedback = [
        _fb(
            feedback="useful",
            category="funding",
            source_name="inc42",
            entities={"sector": "fintech", "location": "Bengaluru"},
        ),
        _fb(
            feedback="useful",
            category="funding",
            source_name="inc42",
            entities={"sector": "fintech", "location": "Mumbai"},
        ),
        _fb(
            feedback="useful",
            category="funding",
            source_name="inc42",
            entities={"sector": "fintech"},
        ),
        _fb(
            feedback="not_relevant",
            category="hiring",
            source_name="hn",
            entities={"sector": "should_not_appear"},
        ),
        _fb(feedback="useful", category="accelerator", source_name="yc"),
    ]
    updated = _build_updated_memory(
        feedback, {"source_weights": {}, "query_boost_terms": ["legacy"]}
    )
    assert updated["query_boost_terms"][0] == "fintech"
    assert "should_not_appear" not in updated["query_boost_terms"]
    assert "Bengaluru" in updated["query_boost_terms"]


def test_store_put_and_get_roundtrip():
    """store.put once; store.get returns updated profile."""
    feedback = [
        _fb(feedback="useful", category="funding", source_name="inc42"),
        _fb(feedback="useful", category="funding", source_name="inc42"),
        _fb(feedback="useful", category="funding", source_name="inc42"),
        _fb(feedback="useful", category="funding", source_name="inc42"),
        _fb(feedback="not_relevant", category="hiring", source_name="hn"),
    ]
    user_id = "sig023_test_user"
    namespace = ("user", user_id, "procedural")

    from agent.graph import _postgres_store as store

    try:
        with patch(
            "agent.nodes.procedural_memory_updater.fetch_all_feedback_for_user",
            return_value=feedback,
        ):
            procedural_memory_updater(
                {
                    "user_id": user_id,
                    "procedural_memory": {
                        "high_signal_categories": [],
                        "low_signal_categories": [],
                        "source_weights": {"tavily": 1.0},
                        "query_boost_terms": [],
                        "query_suppress_terms": [],
                        "trusted_sources": [],
                        "preferred_stage": ["seed"],
                        "min_confidence_threshold": 0.70,
                    },
                }
            )

        item = store.get(namespace, _PROCEDURAL_KEY)
        assert item is not None
        profile = item.value
        assert "funding" in profile["high_signal_categories"]
        assert "hiring" in profile["low_signal_categories"]
        assert profile["source_weights"]["hn"] >= 0.3
        assert "last_updated" not in profile
    finally:
        try:
            store.delete(namespace, _PROCEDURAL_KEY)
        except Exception:
            pass


def test_config_loader_reads_updated_memory_for_search_planner():
    """After updater write: config_loader → procedural_memory → search_planner."""
    user_id = "sig023_next_run_user"
    namespace = ("user", user_id, "procedural")
    feedback = [
        _fb(
            feedback="useful",
            category="funding",
            source_name="inc42",
            entities={"location": "ChennaiBoost"},
        ),
        _fb(
            feedback="useful",
            category="funding",
            source_name="inc42",
            entities={"location": "ChennaiBoost"},
        ),
        _fb(
            feedback="useful",
            category="funding",
            source_name="inc42",
            entities={"location": "ChennaiBoost"},
        ),
        _fb(feedback="not_relevant", category="hiring", source_name="hn"),
        _fb(feedback="not_relevant", category="hiring", source_name="hn"),
    ]

    from agent.graph import _postgres_store as store
    from agent.nodes.config_loader import config_loader

    try:
        with patch(
            "agent.nodes.procedural_memory_updater.fetch_all_feedback_for_user",
            return_value=feedback,
        ):
            procedural_memory_updater(
                {
                    "user_id": user_id,
                    "procedural_memory": {
                        "high_signal_categories": [],
                        "low_signal_categories": [],
                        "source_weights": {
                            "tavily": 1.0,
                            "yc": 1.0,
                            "hn": 0.7,
                            "google_news": 0.65,
                        },
                        "query_boost_terms": [],
                        "query_suppress_terms": [],
                        "trusted_sources": ["inc42"],
                        "preferred_stage": ["seed"],
                        "min_confidence_threshold": 0.70,
                    },
                }
            )

        with patch(
            "agent.nodes.config_loader._fetch_user_config_row",
            return_value=None,
        ):
            loaded = config_loader({"user_id": user_id})

        procedural = loaded["procedural_memory"]
        assert "funding" in procedural["high_signal_categories"]
        assert procedural["source_weights"]["hn"] >= 0.3
        assert "ChennaiBoost" in procedural["query_boost_terms"]

        planned = search_planner(loaded)
        assert "ChennaiBoost" in planned["query_plan"]["tavily"]
        assert planned["run_config_snapshot"]["procedural_memory"]["source_weights"][
            "hn"
        ] >= 0.3
    finally:
        try:
            store.delete(namespace, _PROCEDURAL_KEY)
        except Exception:
            pass


def test_identical_feedback_produces_identical_payload():
    """DEC-007 Gate 8: identical feedback → identical preference objects."""
    feedback = [
        _fb(
            feedback="useful",
            category="funding",
            source_name="inc42",
            entities={"sector": "fintech", "location": "Bengaluru"},
        ),
        _fb(
            feedback="useful",
            category="funding",
            source_name="inc42",
            entities={"sector": "fintech", "location": "Mumbai"},
        ),
        _fb(feedback="useful", category="funding", source_name="inc42"),
        _fb(feedback="not_relevant", category="hiring", source_name="hn"),
        _fb(feedback="not_relevant", category="hiring", source_name="hn"),
    ]
    base = {
        "high_signal_categories": [],
        "low_signal_categories": [],
        "source_weights": {"tavily": 1.0, "hn": 0.7, "yc": 1.0},
        "query_boost_terms": ["Bengaluru"],
        "query_suppress_terms": ["Infosys"],
        "trusted_sources": ["inc42"],
        "preferred_stage": ["seed"],
        "min_confidence_threshold": 0.70,
    }

    result_1 = _build_updated_memory(feedback, base)
    result_2 = _build_updated_memory(feedback, base)
    assert result_1 == result_2
    assert "last_updated" not in result_1
    assert "last_updated" not in result_2

    store_payloads: list[dict] = []
    mock_store = MagicMock()
    mock_store.put.side_effect = (
        lambda ns, key, value: store_payloads.append(dict(value))
    )
    state = {"user_id": "user_001", "procedural_memory": base}

    with patch(
        "agent.nodes.procedural_memory_updater.fetch_all_feedback_for_user",
        return_value=feedback,
    ), patch(
        "agent.nodes.procedural_memory_updater._get_postgres_store",
        return_value=mock_store,
    ):
        out_1 = procedural_memory_updater(state)
        out_2 = procedural_memory_updater(state)

    assert out_1 == out_2 == {}
    assert len(store_payloads) == 2
    assert store_payloads[0] == store_payloads[1]
    assert store_payloads[0] == result_1


def test_no_llm_imports_in_module():
    """DEC-007: module must not import OpenAI / embeddings clients."""
    import ast
    from pathlib import Path

    import agent.nodes.procedural_memory_updater as mod

    tree = ast.parse(Path(mod.__file__).read_text(encoding="utf-8"))
    forbidden_roots = {"openai", "langchain_openai"}
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                assert alias.name.split(".", 1)[0] not in forbidden_roots
        if isinstance(node, ast.ImportFrom) and node.module:
            assert node.module.split(".", 1)[0] not in forbidden_roots



if __name__ == "__main__":
    test_below_threshold_no_update_no_store_write()
    test_exactly_five_triggers_update()
    test_category_ratios_computed_correctly()
    test_source_weight_floor_never_below_0_3()
    test_query_boost_terms_from_useful_entities()
    test_store_put_and_get_roundtrip()
    test_config_loader_reads_updated_memory_for_search_planner()
    test_identical_feedback_produces_identical_payload()
    test_no_llm_imports_in_module()
    print("All procedural memory updater tests passed.")
