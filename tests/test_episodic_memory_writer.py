from agent.nodes.episodic_memory_writer import (
    EPISODIC_MEMORY_STORE,
    episodic_memory_writer,
)


def _clear_store():
    EPISODIC_MEMORY_STORE.clear()


def _state(**overrides):
    base = {
        "run_id": "test_run_001",
        "thread_id": "thread_001",
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


def test_returns_empty_dict():
    _clear_store()
    result = episodic_memory_writer(_state())
    assert result == {}


def test_store_length_increases_by_one():
    _clear_store()
    assert len(EPISODIC_MEMORY_STORE) == 0
    episodic_memory_writer(_state())
    assert len(EPISODIC_MEMORY_STORE) == 1
    episodic_memory_writer(_state(run_id="test_run_002"))
    assert len(EPISODIC_MEMORY_STORE) == 2


def test_episode_schema_complete():
    _clear_store()
    episodic_memory_writer(_state())
    episode = EPISODIC_MEMORY_STORE[0]
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
    assert episode["run_id"] == "test_run_001"
    assert episode["thread_id"] == "thread_001"
    assert episode["item_titles"] == ["Test funding round"]
    assert episode["source_urls"] == ["http://test.com"]
    assert episode["company_names_normalized"] == ["testco"]
    assert episode["briefing_summary"] == "Test briefing content"
    assert isinstance(episode["timestamp"], str)
    assert len(episode["timestamp"]) > 0


def test_briefing_summary_truncated_to_200():
    _clear_store()
    long_briefing = "A" * 350
    episodic_memory_writer(_state(briefing_final=long_briefing))
    summary = EPISODIC_MEMORY_STORE[0]["briefing_summary"]
    assert len(summary) == 200
    assert summary == "A" * 200


def test_company_names_skips_missing():
    _clear_store()
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
    episodic_memory_writer(_state(new_findings=findings))
    assert EPISODIC_MEMORY_STORE[0]["company_names_normalized"] == ["acme"]


def test_empty_new_findings():
    _clear_store()
    episodic_memory_writer(_state(new_findings=[]))
    episode = EPISODIC_MEMORY_STORE[0]
    assert episode["item_titles"] == []
    assert episode["source_urls"] == []
    assert episode["company_names_normalized"] == []


def test_does_not_modify_state():
    _clear_store()
    state = _state()
    original_keys = set(state.keys())
    episodic_memory_writer(state)
    assert set(state.keys()) == original_keys
    assert state["briefing_final"] == "Test briefing content"


if __name__ == "__main__":
    test_returns_empty_dict()
    test_store_length_increases_by_one()
    test_episode_schema_complete()
    test_briefing_summary_truncated_to_200()
    test_company_names_skips_missing()
    test_empty_new_findings()
    test_does_not_modify_state()
    print("Episodic memory writer tests passed.")
