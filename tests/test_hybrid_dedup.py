from copy import deepcopy
from unittest.mock import patch

from agent.nodes.hybrid_dedup import (
    _HARD_DUP_THRESHOLD,
    _NEAR_DUP_FLOOR,
    _cosine_similarity,
    hybrid_dedup,
)
from tests.fixtures.sample_findings import SAMPLE_SCORED_FUNDING_FINDING


def _finding(
    title="Title",
    url="https://example.com/a",
    company="acme",
    date="2025-03-01",
    summary="Summary text for embedding input.",
):
    f = deepcopy(SAMPLE_SCORED_FUNDING_FINDING)
    f["title"] = title
    f["source_url"] = url
    f["summary"] = summary
    f["entities"] = {
        **f["entities"],
        "company_name_normalized": company,
        "announced_date": date,
    }
    return f


def _state(findings, memory=None, user_id="user_001"):
    return {
        "scored_findings": findings,
        "semantic_memory": memory or {},
        "user_id": user_id,
    }


def _unique_embeds(texts: list[str]) -> list[list[float]]:
    """Orthogonal-ish vectors so Stage 3 never drops in deterministic tests."""
    dim = 16
    out = []
    for i, text in enumerate(texts):
        vec = [0.0] * dim
        vec[i % dim] = 1.0
        # Slight per-text perturbation so identical texts still match if needed
        vec[(hash(text) % dim)] = max(vec[(hash(text) % dim)], 0.01)
        out.append(vec)
    return out


def _run(state, embed_fn=_unique_embeds):
    with patch("agent.nodes.hybrid_dedup._embed_texts", side_effect=embed_fn):
        with patch(
            "agent.nodes.hybrid_dedup._load_briefing_item_embeddings",
            return_value=[],
        ):
            with patch(
                "agent.nodes.hybrid_dedup._persist_embedding_to_store",
                return_value=None,
            ):
                with patch(
                    "agent.nodes.hybrid_dedup._load_store_embeddings",
                    return_value=[],
                ):
                    return hybrid_dedup(state)


# ── Stage ordering ────────────────────────────────────────────────────────────

def test_stage_0_catches_company_date_duplicate():
    first = _finding("Article A", "https://inc42.com/a", "sarvam ai", "2025-03-15")
    second = _finding("Article B", "https://yourstory.com/b", "sarvam ai", "2025-03-15")
    result = _run(_state([first, second]))
    assert len(result["new_findings"]) == 1
    assert result["findings_dropped_dedup"] == 1
    result2 = _run(_state([second], {"seen_company_dates": ["sarvam ai|2025-03-15"]}))
    assert result2["findings_dropped_dedup"] == 1


def test_stage_1_catches_url_duplicate():
    first = _finding("Article A", "https://inc42.com/x", "companyA", "2025-01-01")
    second = _finding("Different Title", "https://inc42.com/x", "companyB", "2025-02-01")
    result = _run(_state([first, second]))
    assert len(result["new_findings"]) == 1
    assert result["findings_dropped_dedup"] == 1


def test_stage_2_catches_title_duplicate():
    first = _finding("Startup X Raises $5M", "https://inc42.com/x", "companyA", "2025-01-01")
    second = _finding("startup x raises $5m", "https://yourstory.com/y", "companyB", "2025-02-01")
    result = _run(_state([first, second]))
    assert len(result["new_findings"]) == 1
    assert result["findings_dropped_dedup"] == 1


def test_stage_order_is_0_then_1_then_2():
    memory = {"seen_company_dates": ["acme|2025-03-01"]}
    f = _finding("New Title", "https://brand-new-url.com/z", "acme", "2025-03-01")
    result = _run(_state([f], memory))
    assert result["findings_dropped_dedup"] == 1
    assert result["new_findings"] == []


def test_first_match_wins():
    memory = {
        "seen_company_dates": ["acme|2025-03-01"],
        "seen_urls": ["https://inc42.com/a"],
    }
    f = _finding("Title", "https://inc42.com/a", "acme", "2025-03-01")
    result = _run(_state([f], memory))
    assert result["findings_dropped_dedup"] == 1


# ── duplicate_reason on dropped findings ─────────────────────────────────────

def test_stage_0_duplicate_reason_is_pre_filter():
    first = _finding("Article A", "https://inc42.com/a", "sarvam ai", "2025-03-15")
    second = _finding("Article B", "https://yourstory.com/b", "sarvam ai", "2025-03-15")
    _run(_state([first, second]))
    assert second["is_duplicate"] is True
    assert second["duplicate_reason"] == "pre_filter"


def test_stage_1_duplicate_reason_is_url_match():
    first = _finding("Article A", "https://inc42.com/x", "companyA", "2025-01-01")
    second = _finding("Different Title", "https://inc42.com/x", "companyB", "2025-02-01")
    _run(_state([first, second]))
    assert second["is_duplicate"] is True
    assert second["duplicate_reason"] == "url_match"


def test_stage_2_duplicate_reason_is_title_match():
    first = _finding("Startup X Raises $5M", "https://inc42.com/x", "companyA", "2025-01-01")
    second = _finding("startup x raises $5m", "https://yourstory.com/y", "companyB", "2025-02-01")
    _run(_state([first, second]))
    assert second["is_duplicate"] is True
    assert second["duplicate_reason"] == "title_match"


def test_first_match_wins_duplicate_reason():
    memory = {
        "seen_company_dates": ["acme|2025-03-01"],
        "seen_urls": ["https://inc42.com/a"],
    }
    f = _finding("Title", "https://inc42.com/a", "acme", "2025-03-01")
    _run(_state([f], memory))
    assert f["is_duplicate"] is True
    assert f["duplicate_reason"] == "pre_filter"


# ── Null / empty field handling ───────────────────────────────────────────────

def test_stage_0_skipped_when_company_missing():
    first = _finding("Article A", "https://inc42.com/a", "", "2025-03-01")
    second = _finding("Article B", "https://yourstory.com/b", "", "2025-03-01")
    result = _run(_state([first, second]))
    assert result["findings_dropped_dedup"] == 0
    assert len(result["new_findings"]) == 2


def test_stage_0_skipped_when_date_missing():
    first = _finding("Article A", "https://inc42.com/a", "acme", "")
    second = _finding("Article B", "https://yourstory.com/b", "acme", "")
    result = _run(_state([first, second]))
    assert result["findings_dropped_dedup"] == 0
    assert len(result["new_findings"]) == 2


# ── Preservation ──────────────────────────────────────────────────────────────

def test_all_fields_preserved_on_kept_finding():
    f = _finding()
    result = _run(_state([f]))
    kept = result["new_findings"][0]
    for key in f:
        assert key in kept
    assert kept["is_duplicate"] is False
    assert kept["duplicate_reason"] is None
    assert isinstance(kept.get("embedding"), list)
    assert len(kept["embedding"]) > 0


def test_count_of_all_findings_equals_kept_plus_dropped():
    findings = [
        _finding("A", "https://inc42.com/1", "co1", "2025-01-01"),
        _finding("B", "https://inc42.com/2", "co2", "2025-01-02"),
        _finding("C", "https://inc42.com/1", "co3", "2025-01-03"),
        _finding("D", "https://inc42.com/4", "co4", "2025-01-04"),
    ]
    result = _run(_state(findings))
    total = len(result["new_findings"]) + result["findings_dropped_dedup"]
    assert total == 4


# ── semantic_memory returned correctly ───────────────────────────────────────

def test_semantic_memory_has_all_three_keys():
    f = _finding()
    result = _run(_state([f]))
    mem = result["semantic_memory"]
    assert "seen_company_dates" in mem
    assert "seen_urls" in mem
    assert "seen_titles" in mem
    assert isinstance(mem["seen_company_dates"], list)
    assert isinstance(mem["seen_urls"], list)
    assert isinstance(mem["seen_titles"], list)


def test_semantic_memory_accumulates_from_prior_state():
    existing_url = "https://old-run.com/existing"
    memory = {"seen_urls": [existing_url], "seen_company_dates": [], "seen_titles": []}
    f = _finding("New Article", existing_url, "newco", "2025-05-01")
    result = _run(_state([f], memory))
    assert result["findings_dropped_dedup"] == 1
    assert existing_url in result["semantic_memory"]["seen_urls"]


def test_new_finding_url_added_to_memory():
    f = _finding("Test", "https://inc42.com/new", "newco", "2025-05-01")
    result = _run(_state([f]))
    assert "https://inc42.com/new" in result["semantic_memory"]["seen_urls"]


def test_new_finding_title_added_to_memory():
    f = _finding("Test Title Alpha", "https://inc42.com/tt", "co", "2025-05-01")
    result = _run(_state([f]))
    assert "test title alpha" in result["semantic_memory"]["seen_titles"]


def test_new_finding_company_date_added_to_memory():
    f = _finding("T", "https://inc42.com/tt", "fintech-co", "2025-06-01")
    result = _run(_state([f]))
    assert "fintech-co|2025-06-01" in result["semantic_memory"]["seen_company_dates"]


def test_duplicate_keys_not_added_to_memory():
    first = _finding("A", "https://inc42.com/1", "co1", "2025-01-01")
    second = _finding("A", "https://inc42.com/1", "co1", "2025-01-01")
    result = _run(_state([first, second]))
    assert result["semantic_memory"]["seen_urls"].count("https://inc42.com/1") == 1


def test_empty_findings_returns_empty():
    result = _run(_state([]))
    assert result["new_findings"] == []
    assert result["findings_dropped_dedup"] == 0
    assert isinstance(result["semantic_memory"], dict)


# ── Stage 3 — embedding similarity ───────────────────────────────────────────

def test_thresholds_are_locked():
    assert _HARD_DUP_THRESHOLD == 0.85
    assert _NEAR_DUP_FLOOR == 0.75


def test_stage_3_catches_fuzzy_duplicate_only():
    """Same theme, different URL/title/date → Stages 0–2 miss; Stage 3 drops."""
    first = _finding(
        "PayNova raises $8M Series A led by Elevation",
        "https://inc42.com/paynova-a",
        "paynova",
        "",  # Stage 0 skipped (no date)
        summary="PayNova Bengaluru fintech announced an $8 million Series A.",
    )
    second = _finding(
        "PayNova secures $8 million Series A from Elevation Capital",
        "https://yourstory.com/paynova-funding",
        "paynova",
        "",
        summary="PayNova, a Bengaluru fintech, closed an $8M Series A round.",
    )

    base = [1.0, 0.0, 0.0, 0.0]
    near_dup = [0.99, 0.1, 0.0, 0.0]  # cosine ~0.995 > 0.85
    assert _cosine_similarity(base, near_dup) > 0.85

    def embed_fn(texts):
        assert len(texts) == 2
        return [base, near_dup]

    result = _run(_state([first, second]), embed_fn=embed_fn)
    assert len(result["new_findings"]) == 1
    assert result["findings_dropped_dedup"] == 1
    assert second["is_duplicate"] is True
    assert second["duplicate_reason"] == "embedding_similarity"
    assert first["is_duplicate"] is False


def test_stage_3_near_duplicate_kept_with_flag():
    first = _finding("Alpha funding news", "https://a.com/1", "alpha", "", summary="A")
    second = _finding("Related alpha coverage", "https://b.com/2", "beta", "", summary="B")

    base = [1.0, 0.0, 0.0, 0.0]
    # Construct vector with cosine in [0.75, 0.85]
    near = [0.8, 0.6, 0.0, 0.0]
    sim = _cosine_similarity(base, near)
    assert 0.75 <= sim <= 0.85

    def embed_fn(texts):
        return [base, near]

    result = _run(_state([first, second]), embed_fn=embed_fn)
    assert len(result["new_findings"]) == 2
    assert result["findings_dropped_dedup"] == 0
    assert second.get("related_to_previous_coverage") is True
    assert second["is_duplicate"] is False


def test_stage_3_preserves_unrelated_articles():
    first = _finding("Fintech raise", "https://a.com/1", "finco", "2025-01-01", summary="fin")
    second = _finding("Climate startup hire", "https://b.com/2", "climco", "2025-02-01", summary="clim")

    def embed_fn(texts):
        return [[1.0, 0.0, 0.0, 0.0], [0.0, 1.0, 0.0, 0.0]]

    result = _run(_state([first, second]), embed_fn=embed_fn)
    assert len(result["new_findings"]) == 2
    assert result["findings_dropped_dedup"] == 0
    assert first["is_duplicate"] is False
    assert second["is_duplicate"] is False


def test_stage_3_not_reached_when_stage_0_matches():
    """Stage 0 must win before any embedding call for that finding."""
    memory = {"seen_company_dates": ["acme|2025-03-01"]}
    f = _finding("Anything", "https://unique.com/z", "acme", "2025-03-01")
    called = {"n": 0}

    def embed_fn(texts):
        called["n"] += 1
        return _unique_embeds(texts)

    result = _run(_state([f], memory), embed_fn=embed_fn)
    assert result["findings_dropped_dedup"] == 1
    assert f["duplicate_reason"] == "pre_filter"
    # No Stage-3 candidates → embed not called
    assert called["n"] == 0


def test_stage_3_persists_embedding_to_store_and_finding():
    from agent.graph import _postgres_store
    from agent.nodes.hybrid_dedup import _DEDUP_EMBEDDING_NS_SUFFIX

    user_id = "user_001"
    url = f"https://inc42.com/persist-{id(object())}"
    f = _finding("Persist Me", url, "persistco", "2025-07-01", summary="persist summary")
    namespace = ("user", user_id, _DEDUP_EMBEDDING_NS_SUFFIX)
    expected = [0.0, 1.0, 0.0, 0.0]

    def embed_fn(texts):
        return [expected]

    with patch("agent.nodes.hybrid_dedup._embed_texts", side_effect=embed_fn):
        with patch(
            "agent.nodes.hybrid_dedup._load_briefing_item_embeddings",
            return_value=[],
        ):
            with patch(
                "agent.nodes.hybrid_dedup._load_store_embeddings",
                return_value=[],
            ):
                result = hybrid_dedup(_state([f], user_id=user_id))

    assert len(result["new_findings"]) == 1
    kept = result["new_findings"][0]
    assert kept["embedding"] == expected
    item = _postgres_store.get(namespace, url)
    assert item is not None
    assert item.value.get("model") == "text-embedding-3-small"
    assert item.value.get("embedding") == expected
    _postgres_store.delete(namespace, url)


def test_hybrid_dedup_has_no_briefing_items_update():
    """Architecture alignment: Hybrid Dedup must not UPDATE briefing_items."""
    import agent.nodes.hybrid_dedup as mod
    import inspect

    source = inspect.getsource(mod)
    assert "UPDATE briefing_items" not in source
    assert "_write_briefing_items_embedding" not in source


if __name__ == "__main__":
    test_stage_0_catches_company_date_duplicate()
    test_stage_1_catches_url_duplicate()
    test_stage_2_catches_title_duplicate()
    test_stage_order_is_0_then_1_then_2()
    test_first_match_wins()
    test_stage_0_duplicate_reason_is_pre_filter()
    test_stage_1_duplicate_reason_is_url_match()
    test_stage_2_duplicate_reason_is_title_match()
    test_first_match_wins_duplicate_reason()
    test_stage_0_skipped_when_company_missing()
    test_stage_0_skipped_when_date_missing()
    test_all_fields_preserved_on_kept_finding()
    test_count_of_all_findings_equals_kept_plus_dropped()
    test_semantic_memory_has_all_three_keys()
    test_semantic_memory_accumulates_from_prior_state()
    test_new_finding_url_added_to_memory()
    test_new_finding_title_added_to_memory()
    test_new_finding_company_date_added_to_memory()
    test_duplicate_keys_not_added_to_memory()
    test_empty_findings_returns_empty()
    test_thresholds_are_locked()
    test_stage_3_catches_fuzzy_duplicate_only()
    test_stage_3_near_duplicate_kept_with_flag()
    test_stage_3_preserves_unrelated_articles()
    test_stage_3_not_reached_when_stage_0_matches()
    test_stage_3_persists_embedding_to_store_and_finding()
    test_hybrid_dedup_has_no_briefing_items_update()
    print("Hybrid dedup tests passed.")
