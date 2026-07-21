from copy import deepcopy

from agent.nodes.hybrid_dedup import hybrid_dedup
from tests.fixtures.sample_findings import SAMPLE_SCORED_FUNDING_FINDING


def _finding(title="Title", url="https://example.com/a", company="acme", date="2025-03-01"):
    f = deepcopy(SAMPLE_SCORED_FUNDING_FINDING)
    f["title"] = title
    f["source_url"] = url
    f["entities"] = {
        **f["entities"],
        "company_name_normalized": company,
        "announced_date": date,
    }
    return f


def _state(findings, memory=None):
    return {
        "scored_findings": findings,
        "semantic_memory": memory or {},
    }


# ── Stage ordering ────────────────────────────────────────────────────────────

def test_stage_0_catches_company_date_duplicate():
    first = _finding("Article A", "https://inc42.com/a", "sarvam ai", "2025-03-15")
    second = _finding("Article B", "https://yourstory.com/b", "sarvam ai", "2025-03-15")
    result = hybrid_dedup(_state([first, second]))
    assert len(result["new_findings"]) == 1
    assert result["findings_dropped_dedup"] == 1
    dropped = [f for f in [second] if f["source_url"] not in [r["source_url"] for r in result["new_findings"]]]
    # The second one should have been caught by pre_filter
    # Verify via a fresh single-finding run to confirm stage 0 label
    result2 = hybrid_dedup(_state([second], {"seen_company_dates": ["sarvam ai|2025-03-15"]}))
    assert result2["findings_dropped_dedup"] == 1


def test_stage_1_catches_url_duplicate():
    first = _finding("Article A", "https://inc42.com/x", "companyA", "2025-01-01")
    # Same URL, different company+date so stage 0 skips
    second = _finding("Different Title", "https://inc42.com/x", "companyB", "2025-02-01")
    result = hybrid_dedup(_state([first, second]))
    assert len(result["new_findings"]) == 1
    assert result["findings_dropped_dedup"] == 1


def test_stage_2_catches_title_duplicate():
    first = _finding("Startup X Raises $5M", "https://inc42.com/x", "companyA", "2025-01-01")
    # Same title (case-insensitive), different URL, different company+date
    second = _finding("startup x raises $5m", "https://yourstory.com/y", "companyB", "2025-02-01")
    result = hybrid_dedup(_state([first, second]))
    assert len(result["new_findings"]) == 1
    assert result["findings_dropped_dedup"] == 1


def test_stage_order_is_0_then_1_then_2():
    """A finding matched by pre_filter should never reach stage 1 or 2 checks."""
    memory = {"seen_company_dates": ["acme|2025-03-01"]}
    f = _finding("New Title", "https://brand-new-url.com/z", "acme", "2025-03-01")
    result = hybrid_dedup(_state([f], memory))
    # Caught by stage 0 despite unique URL and title
    assert result["findings_dropped_dedup"] == 1
    assert result["new_findings"] == []


def test_first_match_wins():
    """When multiple stages would match, duplicate_reason is from the earliest stage."""
    memory = {
        "seen_company_dates": ["acme|2025-03-01"],
        "seen_urls": ["https://inc42.com/a"],
    }
    f = _finding("Title", "https://inc42.com/a", "acme", "2025-03-01")
    result = hybrid_dedup(_state([f], memory))
    assert result["findings_dropped_dedup"] == 1


# ── duplicate_reason on dropped findings ─────────────────────────────────────

def test_stage_0_duplicate_reason_is_pre_filter():
    first = _finding("Article A", "https://inc42.com/a", "sarvam ai", "2025-03-15")
    second = _finding("Article B", "https://yourstory.com/b", "sarvam ai", "2025-03-15")
    hybrid_dedup(_state([first, second]))
    assert second["is_duplicate"] is True
    assert second["duplicate_reason"] == "pre_filter"


def test_stage_1_duplicate_reason_is_url_match():
    first = _finding("Article A", "https://inc42.com/x", "companyA", "2025-01-01")
    second = _finding("Different Title", "https://inc42.com/x", "companyB", "2025-02-01")
    hybrid_dedup(_state([first, second]))
    assert second["is_duplicate"] is True
    assert second["duplicate_reason"] == "url_match"


def test_stage_2_duplicate_reason_is_title_match():
    first = _finding("Startup X Raises $5M", "https://inc42.com/x", "companyA", "2025-01-01")
    second = _finding("startup x raises $5m", "https://yourstory.com/y", "companyB", "2025-02-01")
    hybrid_dedup(_state([first, second]))
    assert second["is_duplicate"] is True
    assert second["duplicate_reason"] == "title_match"


def test_first_match_wins_duplicate_reason():
    """Stage 0 match sets pre_filter; stage 1 match on the same finding must not overwrite it."""
    memory = {
        "seen_company_dates": ["acme|2025-03-01"],
        "seen_urls": ["https://inc42.com/a"],
    }
    f = _finding("Title", "https://inc42.com/a", "acme", "2025-03-01")
    hybrid_dedup(_state([f], memory))
    assert f["is_duplicate"] is True
    # Stage 0 fires first; reason must be pre_filter, not url_match
    assert f["duplicate_reason"] == "pre_filter"


# ── Null / empty field handling ───────────────────────────────────────────────

def test_stage_0_skipped_when_company_missing():
    first = _finding("Article A", "https://inc42.com/a", "", "2025-03-01")
    second = _finding("Article B", "https://yourstory.com/b", "", "2025-03-01")
    # Both have no company — stage 0 skipped; no URL overlap, different titles → both kept
    result = hybrid_dedup(_state([first, second]))
    assert result["findings_dropped_dedup"] == 0
    assert len(result["new_findings"]) == 2


def test_stage_0_skipped_when_date_missing():
    first = _finding("Article A", "https://inc42.com/a", "acme", "")
    second = _finding("Article B", "https://yourstory.com/b", "acme", "")
    result = hybrid_dedup(_state([first, second]))
    assert result["findings_dropped_dedup"] == 0
    assert len(result["new_findings"]) == 2


# ── Preservation ──────────────────────────────────────────────────────────────

def test_all_fields_preserved_on_kept_finding():
    f = _finding()
    result = hybrid_dedup(_state([f]))
    kept = result["new_findings"][0]
    # All original top-level keys must be present
    for key in f:
        assert key in kept
    # is_duplicate and duplicate_reason must be set correctly
    assert kept["is_duplicate"] is False
    assert kept["duplicate_reason"] is None


def test_count_of_all_findings_equals_kept_plus_dropped():
    findings = [
        _finding("A", "https://inc42.com/1", "co1", "2025-01-01"),
        _finding("B", "https://inc42.com/2", "co2", "2025-01-02"),
        _finding("C", "https://inc42.com/1", "co3", "2025-01-03"),  # URL dup of first
        _finding("D", "https://inc42.com/4", "co4", "2025-01-04"),
    ]
    result = hybrid_dedup(_state(findings))
    total = len(result["new_findings"]) + result["findings_dropped_dedup"]
    assert total == 4


# ── semantic_memory returned correctly ───────────────────────────────────────

def test_semantic_memory_has_all_three_keys():
    f = _finding()
    result = hybrid_dedup(_state([f]))
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
    result = hybrid_dedup(_state([f], memory))
    assert result["findings_dropped_dedup"] == 1
    # Existing URL should still be in output memory
    assert existing_url in result["semantic_memory"]["seen_urls"]


def test_new_finding_url_added_to_memory():
    f = _finding("Test", "https://inc42.com/new", "newco", "2025-05-01")
    result = hybrid_dedup(_state([f]))
    assert "https://inc42.com/new" in result["semantic_memory"]["seen_urls"]


def test_new_finding_title_added_to_memory():
    f = _finding("Test Title Alpha", "https://inc42.com/tt", "co", "2025-05-01")
    result = hybrid_dedup(_state([f]))
    assert "test title alpha" in result["semantic_memory"]["seen_titles"]


def test_new_finding_company_date_added_to_memory():
    f = _finding("T", "https://inc42.com/tt", "fintech-co", "2025-06-01")
    result = hybrid_dedup(_state([f]))
    assert "fintech-co|2025-06-01" in result["semantic_memory"]["seen_company_dates"]


def test_duplicate_keys_not_added_to_memory():
    first = _finding("A", "https://inc42.com/1", "co1", "2025-01-01")
    second = _finding("A", "https://inc42.com/1", "co1", "2025-01-01")  # exact dup
    result = hybrid_dedup(_state([first, second]))
    # Only 1 unique URL should be in seen_urls
    assert result["semantic_memory"]["seen_urls"].count("https://inc42.com/1") == 1


# ── Empty input ───────────────────────────────────────────────────────────────

def test_empty_findings_returns_empty():
    result = hybrid_dedup(_state([]))
    assert result["new_findings"] == []
    assert result["findings_dropped_dedup"] == 0
    assert isinstance(result["semantic_memory"], dict)


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
    print("Hybrid dedup tests passed.")
