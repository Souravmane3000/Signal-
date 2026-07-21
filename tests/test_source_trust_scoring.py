from copy import deepcopy

from agent.nodes.source_trust_scoring import source_trust_scoring
from tests.fixtures.sample_findings import SAMPLE_SCORED_FUNDING_FINDING


def _finding(confidence: float, title: str) -> dict:
    finding = deepcopy(SAMPLE_SCORED_FUNDING_FINDING)
    finding["confidence_score"] = confidence
    finding["title"] = title
    return finding


def test_sorts_by_confidence_descending():
    state = {
        "scored_findings": [
            _finding(0.60, "low"),
            _finding(0.95, "high"),
            _finding(0.80, "mid"),
        ]
    }
    result = source_trust_scoring(state)
    scores = [f["confidence_score"] for f in result["scored_findings"]]
    assert scores == [0.95, 0.80, 0.60]
    assert [f["title"] for f in result["scored_findings"]] == ["high", "mid", "low"]


def test_count_unchanged():
    findings = [
        _finding(0.50, "a"),
        _finding(0.90, "b"),
        _finding(0.70, "c"),
    ]
    result = source_trust_scoring({"scored_findings": findings})
    assert len(result["scored_findings"]) == len(findings)


def test_fields_preserved():
    original = _finding(0.85, "preserve-me")
    original_snapshot = deepcopy(original)
    result = source_trust_scoring({"scored_findings": [original]})
    kept = result["scored_findings"][0]
    assert kept == original_snapshot
    assert set(kept.keys()) == set(original_snapshot.keys())


def test_stable_ordering_for_equal_confidence():
    state = {
        "scored_findings": [
            _finding(0.80, "first"),
            _finding(0.80, "second"),
            _finding(0.90, "top"),
            _finding(0.80, "third"),
        ]
    }
    result = source_trust_scoring(state)
    titles = [f["title"] for f in result["scored_findings"]]
    assert titles == ["top", "first", "second", "third"]


def test_empty_input():
    result = source_trust_scoring({"scored_findings": []})
    assert result["scored_findings"] == []


if __name__ == "__main__":
    test_sorts_by_confidence_descending()
    test_count_unchanged()
    test_fields_preserved()
    test_stable_ordering_for_equal_confidence()
    test_empty_input()
    print("Source trust scoring test passed.")
