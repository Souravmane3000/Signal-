from agent.nodes.scope_filter import scope_filter
from tests.fixtures.sample_findings import (
    SAMPLE_OUT_OF_SCOPE_FINDING,
    SAMPLE_SCORED_FUNDING_FINDING,
)


def make_finding(location=None, amount=None, stage=None):
    return {
        **SAMPLE_SCORED_FUNDING_FINDING,
        "entities": {
            **SAMPLE_SCORED_FUNDING_FINDING["entities"],
            "location": location,
            "funding_amount_usd": amount,
            "funding_stage": stage,
        },
    }


def test_scope_filter():
    state = {
        "scored_findings": [
            SAMPLE_OUT_OF_SCOPE_FINDING,  # DROP - US location
            make_finding(location="Bengaluru", amount=5000000),  # KEEP
            make_finding(location=None, amount=5000000),  # KEEP - null location
            make_finding(location="Mumbai", amount=200000000),  # DROP - too large
            make_finding(location="Delhi", stage="series_c"),  # DROP - wrong stage
            make_finding(location=None, amount=None, stage=None),  # KEEP - all null
        ]
    }
    result = scope_filter(state)
    assert result["findings_dropped_scope"] == 3
    assert len(result["scored_findings"]) == 3
    print("Scope filter test passed.")


def test_boundary_amounts_inclusive():
    """$500K and $50M inclusive must be retained."""
    state = {
        "scored_findings": [
            make_finding(location="Bengaluru", amount=500_000, stage="seed"),
            make_finding(location="Mumbai", amount=50_000_000, stage="series_b"),
            make_finding(location="Delhi", amount=499_999, stage="seed"),
            make_finding(location="Pune", amount=50_000_001, stage="series_a"),
        ]
    }
    result = scope_filter(state)
    assert result["findings_dropped_scope"] == 2
    assert len(result["scored_findings"]) == 2
    amounts = [
        f["entities"]["funding_amount_usd"] for f in result["scored_findings"]
    ]
    assert 500_000 in amounts
    assert 50_000_000 in amounts


def test_series_c_plus_and_non_indian_rejected():
    state = {
        "scored_findings": [
            make_finding(location="Bengaluru", amount=5_000_000, stage="series_c"),
            make_finding(location="Mumbai", amount=5_000_000, stage="series_d"),
            make_finding(location="Delhi", amount=5_000_000, stage="ipo"),
            make_finding(location="San Francisco", amount=5_000_000, stage="seed"),
            make_finding(location="Singapore", amount=5_000_000, stage="series_a"),
            make_finding(location="Bengaluru", amount=5_000_000, stage="series_a"),
        ]
    }
    result = scope_filter(state)
    assert result["findings_dropped_scope"] == 5
    assert len(result["scored_findings"]) == 1
    assert result["scored_findings"][0]["entities"]["location"] == "Bengaluru"


def test_missing_data_retained():
    state = {
        "scored_findings": [
            make_finding(location=None, amount=5_000_000, stage="seed"),
            make_finding(location="Bengaluru", amount=None, stage="seed"),
            make_finding(location="Bengaluru", amount=5_000_000, stage=None),
            make_finding(location=None, amount=None, stage=None),
        ]
    }
    result = scope_filter(state)
    assert result["findings_dropped_scope"] == 0
    assert len(result["scored_findings"]) == 4


def test_findings_not_mutated():
    finding = make_finding(location="Bengaluru", amount=5_000_000, stage="series_a")
    original_keys = set(finding.keys())
    result = scope_filter({"scored_findings": [finding]})
    kept = result["scored_findings"][0]
    assert set(kept.keys()) == original_keys
    assert "scope_decision" not in kept
    assert "scope_reason" not in kept
    assert "scope_penalty" not in kept


if __name__ == "__main__":
    test_scope_filter()
    test_boundary_amounts_inclusive()
    test_series_c_plus_and_non_indian_rejected()
    test_missing_data_retained()
    test_findings_not_mutated()
