from uuid import uuid4

from agent.graph import _postgres_store
from agent.nodes.episodic_memory_writer import episodic_memory_writer

_USER_ID = "user_001"
_EPISODIC_NS = ("user", _USER_ID, "episodic")


def _state(**overrides):
    base = {
        "run_id": f"test_run_{uuid4().hex[:8]}",
        "thread_id": "thread_001",
        "user_id": _USER_ID,
        "new_findings": [
            {
                "title": "Test funding round",
                "source_url": "http://test.com",
                "entities": {"company_name_normalized": "testco"},
            }
        ],
        "briefing_final": "Test briefing content",
    }
    base.update(overrides)
    return base


def _get_episode(run_id: str):
    return _postgres_store.get(_EPISODIC_NS, run_id)


def _cleanup(run_id: str):
    try:
        _postgres_store.delete(_EPISODIC_NS, run_id)
    except Exception:
        pass


def test_returns_empty_dict():
    state = _state()
    try:
        result = episodic_memory_writer(state)
        assert result == {}
    finally:
        _cleanup(state["run_id"])


def test_store_put_writes_episode():
    state = _state()
    run_id = state["run_id"]
    try:
        assert _get_episode(run_id) is None
        episodic_memory_writer(state)
        item = _get_episode(run_id)
        assert item is not None
        assert item.value["run_id"] == run_id
    finally:
        _cleanup(run_id)


def test_second_run_writes_separate_key():
    first = _state()
    second = _state()
    try:
        episodic_memory_writer(first)
        episodic_memory_writer(second)
        assert _get_episode(first["run_id"]) is not None
        assert _get_episode(second["run_id"]) is not None
        assert first["run_id"] != second["run_id"]
    finally:
        _cleanup(first["run_id"])
        _cleanup(second["run_id"])


def test_episode_schema_complete():
    state = _state(run_id=f"schema_{uuid4().hex[:8]}")
    try:
        episodic_memory_writer(state)
        episode = _get_episode(state["run_id"]).value
        required = {
            "run_id",
            "thread_id",
            "timestamp",
            "item_titles",
            "source_urls",
            "company_names_normalized",
            "briefing_summary",
        }
        assert required.issubset(episode.keys())
        assert episode["run_id"] == state["run_id"]
        assert episode["thread_id"] == "thread_001"
        assert episode["item_titles"] == ["Test funding round"]
        assert episode["source_urls"] == ["http://test.com"]
        assert episode["company_names_normalized"] == ["testco"]
        assert episode["briefing_summary"] == "Test briefing content"
        assert isinstance(episode["timestamp"], str)
        assert len(episode["timestamp"]) > 0
    finally:
        _cleanup(state["run_id"])


def test_briefing_summary_truncated_to_200():
    state = _state(briefing_final="A" * 350)
    try:
        episodic_memory_writer(state)
        summary = _get_episode(state["run_id"]).value["briefing_summary"]
        assert len(summary) == 200
        assert summary == "A" * 200
    finally:
        _cleanup(state["run_id"])


def test_company_names_skips_missing():
    findings = [
        {
            "title": "Has company",
            "source_url": "http://a.com",
            "entities": {"company_name_normalized": "acme"},
        },
        {
            "title": "No company",
            "source_url": "http://b.com",
            "entities": {"company_name_normalized": None},
        },
        {
            "title": "Empty company",
            "source_url": "http://c.com",
            "entities": {"company_name_normalized": ""},
        },
    ]
    state = _state(new_findings=findings)
    try:
        episodic_memory_writer(state)
        assert _get_episode(state["run_id"]).value["company_names_normalized"] == ["acme"]
    finally:
        _cleanup(state["run_id"])


def test_empty_new_findings():
    state = _state(new_findings=[])
    try:
        episodic_memory_writer(state)
        episode = _get_episode(state["run_id"]).value
        assert episode["item_titles"] == []
        assert episode["source_urls"] == []
        assert episode["company_names_normalized"] == []
    finally:
        _cleanup(state["run_id"])


def test_does_not_modify_state():
    state = _state()
    original_keys = set(state.keys())
    try:
        episodic_memory_writer(state)
        assert set(state.keys()) == original_keys
        assert state["briefing_final"] == "Test briefing content"
    finally:
        _cleanup(state["run_id"])


def test_namespace_is_user_user_id_episodic():
    state = _state()
    try:
        episodic_memory_writer(state)
        item = _postgres_store.get(("user", _USER_ID, "episodic"), state["run_id"])
        assert item is not None
        assert _postgres_store.get(("user", "other_user", "episodic"), state["run_id"]) is None
    finally:
        _cleanup(state["run_id"])


if __name__ == "__main__":
    test_returns_empty_dict()
    test_store_put_writes_episode()
    test_second_run_writes_separate_key()
    test_episode_schema_complete()
    test_briefing_summary_truncated_to_200()
    test_company_names_skips_missing()
    test_empty_new_findings()
    test_does_not_modify_state()
    test_namespace_is_user_user_id_episodic()
    print("Episodic memory writer tests passed.")
