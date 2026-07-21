"""Deterministic unit tests for SIG-011 Entity Extraction (mocked OpenAI)."""

from __future__ import annotations

import json
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

from agent.nodes import entity_extraction as ee
from agent.nodes.entity_extraction import EntityDataModel, entity_extraction
from agent.state import ALLOWED_CATEGORIES, SOURCE_TRUST
from tests.fixtures.sample_findings import SAMPLE_FUNDING_FINDING

VALID_EXTRACTION = {
    "company_name": "PayNova",
    "company_name_normalized": "paynova",
    "founder_name": None,
    "investor_names": ["Elevation Capital"],
    "investor_names_normalized": ["elevation capital"],
    "funding_amount_usd": 8000000,
    "funding_stage": "series_a",
    "sector": "fintech",
    "location": "Bengaluru",
    "announced_date": "2025-03-10",
    "category": "funding",
}


def _mock_completion(content: str, total_tokens: int = 100):
    return SimpleNamespace(
        choices=[SimpleNamespace(message=SimpleNamespace(content=content))],
        usage=SimpleNamespace(total_tokens=total_tokens),
    )


def _base_finding(**overrides):
    finding = {**SAMPLE_FUNDING_FINDING, "freshness_penalized": False}
    finding.update(overrides)
    return finding


@patch("agent.nodes.entity_extraction.OpenAI")
def test_valid_extraction(mock_openai_cls):
    client = MagicMock()
    mock_openai_cls.return_value = client
    client.chat.completions.create.return_value = _mock_completion(
        json.dumps(VALID_EXTRACTION), total_tokens=120
    )

    result = entity_extraction({"raw_findings": [_base_finding()]})

    assert "scored_findings" in result
    assert len(result["scored_findings"]) == 1
    finding = result["scored_findings"][0]
    assert finding["category"] in ALLOWED_CATEGORIES
    assert finding["entities"]["funding_amount_usd"] == 8000000
    assert finding["entities"]["company_name"] == "PayNova"
    assert "category" not in finding["entities"]
    assert finding["is_duplicate"] is False
    assert finding["duplicate_reason"] is None
    client.chat.completions.create.assert_called_once()
    call_kwargs = client.chat.completions.create.call_args.kwargs
    assert call_kwargs["model"] == "gpt-4o-mini"
    assert call_kwargs["temperature"] == 0
    assert call_kwargs["max_tokens"] == 400


@patch("agent.nodes.entity_extraction.OpenAI")
def test_invalid_category_fallback(mock_openai_cls):
    client = MagicMock()
    mock_openai_cls.return_value = client
    payload = {**VALID_EXTRACTION, "category": "ipo_rumor"}
    client.chat.completions.create.return_value = _mock_completion(json.dumps(payload))

    result = entity_extraction({"raw_findings": [_base_finding()]})

    assert len(result["scored_findings"]) == 1
    assert result["scored_findings"][0]["category"] == "funding"


@patch("agent.nodes.entity_extraction.OpenAI")
def test_json_parsing_failure_skips_finding(mock_openai_cls):
    client = MagicMock()
    mock_openai_cls.return_value = client
    client.chat.completions.create.return_value = _mock_completion(
        "not-json {{{", total_tokens=50
    )

    result = entity_extraction({"raw_findings": [_base_finding()]})

    assert result["scored_findings"] == []
    assert result["tokens_used"] == 50


@patch("agent.nodes.entity_extraction.OpenAI")
def test_malformed_output_skipped_by_pydantic(mock_openai_cls):
    client = MagicMock()
    mock_openai_cls.return_value = client
    payload = {**VALID_EXTRACTION, "funding_amount_usd": "eight million"}
    client.chat.completions.create.return_value = _mock_completion(json.dumps(payload))

    result = entity_extraction({"raw_findings": [_base_finding()]})

    assert result["scored_findings"] == []


@patch("agent.nodes.entity_extraction.OpenAI")
def test_confidence_and_source_trust_scoring(mock_openai_cls):
    client = MagicMock()
    mock_openai_cls.return_value = client
    client.chat.completions.create.return_value = _mock_completion(
        json.dumps(VALID_EXTRACTION)
    )

    result = entity_extraction(
        {"raw_findings": [_base_finding(freshness_penalized=False)]}
    )
    finding = result["scored_findings"][0]
    expected_trust = SOURCE_TRUST["inc42"]
    assert finding["source_trust_score"] == expected_trust
    assert finding["freshness_penalty_applied"] is False
    assert finding["confidence_score"] == expected_trust


@patch("agent.nodes.entity_extraction.OpenAI")
def test_freshness_penalty(mock_openai_cls):
    client = MagicMock()
    mock_openai_cls.return_value = client
    client.chat.completions.create.return_value = _mock_completion(
        json.dumps(VALID_EXTRACTION)
    )

    result = entity_extraction(
        {"raw_findings": [_base_finding(freshness_penalized=True)]}
    )
    finding = result["scored_findings"][0]
    expected_trust = SOURCE_TRUST["inc42"]
    assert finding["freshness_penalty_applied"] is True
    assert finding["confidence_score"] == max(0.0, expected_trust - 0.10)


@patch("agent.nodes.entity_extraction.OpenAI")
def test_tokens_accumulated(mock_openai_cls):
    client = MagicMock()
    mock_openai_cls.return_value = client
    client.chat.completions.create.side_effect = [
        _mock_completion(json.dumps(VALID_EXTRACTION), total_tokens=100),
        _mock_completion(json.dumps(VALID_EXTRACTION), total_tokens=150),
    ]

    findings = [
        _base_finding(title="A"),
        _base_finding(title="B"),
    ]
    result = entity_extraction({"raw_findings": findings})

    assert result["tokens_used"] == 250
    assert abs(result["estimated_cost_usd"] - (250 * 0.000000150)) < 1e-12
    assert len(result["scored_findings"]) == 2


@patch("agent.nodes.entity_extraction.OpenAI")
def test_max_findings_guardrail(mock_openai_cls):
    client = MagicMock()
    mock_openai_cls.return_value = client
    client.chat.completions.create.return_value = _mock_completion(
        json.dumps(VALID_EXTRACTION), total_tokens=10
    )

    findings = [_base_finding(title=f"Finding {i}") for i in range(5)]
    with patch.object(ee, "MAX_FINDINGS_PER_RUN", 2):
        result = entity_extraction({"raw_findings": findings})

    assert len(result["scored_findings"]) == 2
    assert client.chat.completions.create.call_count == 2


@patch("agent.nodes.entity_extraction.OpenAI")
def test_cost_guardrail(mock_openai_cls):
    client = MagicMock()
    mock_openai_cls.return_value = client
    # First call alone exceeds a tiny cost ceiling; second finding must not be called.
    client.chat.completions.create.return_value = _mock_completion(
        json.dumps(VALID_EXTRACTION), total_tokens=1_000_000
    )

    findings = [_base_finding(title="A"), _base_finding(title="B")]
    with patch.object(ee, "MAX_RUN_COST_USD", 0.0001):
        result = entity_extraction({"raw_findings": findings})

    assert client.chat.completions.create.call_count == 1
    assert len(result["scored_findings"]) == 1
    assert result["estimated_cost_usd"] >= 0.0001


def test_prompt_loaded_from_file_not_inlined():
    prompt = ee._load_prompt()
    assert "entity extraction system for Indian startup news" in prompt
    assert "Return ONLY valid JSON" in prompt
    with open(ee.__file__, encoding="utf-8") as handle:
        source = handle.read()
    assert "You are an entity extraction system" not in source


def test_entity_data_model_rejects_bad_types():
    try:
        EntityDataModel.model_validate(
            {**VALID_EXTRACTION, "funding_amount_usd": "bad"}
        )
        assert False, "expected ValidationError"
    except Exception as exc:
        assert exc.__class__.__name__ == "ValidationError"


def test_imports():
    assert entity_extraction is not None
    assert "funding" in ALLOWED_CATEGORIES


if __name__ == "__main__":
    test_imports()
    test_prompt_loaded_from_file_not_inlined()
    test_entity_data_model_rejects_bad_types()
    test_valid_extraction()
    test_invalid_category_fallback()
    test_json_parsing_failure_skips_finding()
    test_malformed_output_skipped_by_pydantic()
    test_confidence_and_source_trust_scoring()
    test_freshness_penalty()
    test_tokens_accumulated()
    test_max_findings_guardrail()
    test_cost_guardrail()
    print("All entity extraction tests passed.")
