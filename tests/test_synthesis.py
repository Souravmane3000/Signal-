from copy import deepcopy
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

from agent.nodes.synthesis import _EMPTY_BRIEFING, _build_briefing_items, _build_context, synthesis
from agent.state import ErrorCode
from tests.fixtures.sample_findings import SAMPLE_SCORED_FUNDING_FINDING


def _finding(**overrides):
    f = deepcopy(SAMPLE_SCORED_FUNDING_FINDING)
    f.update(overrides)
    return f


def _state(findings, tokens_used=0, estimated_cost_usd=0.0):
    return {
        "new_findings": findings,
        "tokens_used": tokens_used,
        "estimated_cost_usd": estimated_cost_usd,
    }


def _mock_response(content="## Signal Weekly Briefing\n", total_tokens=300):
    choice = SimpleNamespace(message=SimpleNamespace(content=content))
    usage = SimpleNamespace(total_tokens=total_tokens)
    return SimpleNamespace(choices=[choice], usage=usage)


# ── Empty findings path ───────────────────────────────────────────────────────

def test_empty_findings_returns_no_llm_call():
    result = synthesis(_state([]))
    assert result["briefing_draft"] == _EMPTY_BRIEFING
    assert result["briefing_final"] == _EMPTY_BRIEFING
    assert result["briefing_items"] == []
    # tokens_used and estimated_cost_usd must NOT appear (no LLM call)
    assert "tokens_used" not in result
    assert "estimated_cost_usd" not in result


def test_empty_findings_no_openai_call():
    with patch("agent.nodes.synthesis.OpenAI") as mock_openai_cls:
        synthesis(_state([]))
    mock_openai_cls.assert_not_called()


# ── Full path with mocked OpenAI ──────────────────────────────────────────────

def test_briefing_draft_and_final_populated():
    fake_text = "## Signal Weekly Briefing\n### Executive Summary\nTest."
    with patch("agent.nodes.synthesis.OpenAI") as mock_openai_cls:
        mock_client = MagicMock()
        mock_openai_cls.return_value = mock_client
        mock_client.chat.completions.create.return_value = _mock_response(fake_text, 200)
        result = synthesis(_state([_finding()]))
    assert result["briefing_draft"] == fake_text
    assert result["briefing_final"] == fake_text


def test_briefing_draft_equals_briefing_final():
    with patch("agent.nodes.synthesis.OpenAI") as mock_openai_cls:
        mock_client = MagicMock()
        mock_openai_cls.return_value = mock_client
        mock_client.chat.completions.create.return_value = _mock_response()
        result = synthesis(_state([_finding()]))
    assert result["briefing_draft"] == result["briefing_final"]


def test_briefing_items_count_matches_findings():
    findings = [_finding(title=f"Finding {i}", source_url=f"https://ex.com/{i}") for i in range(4)]
    with patch("agent.nodes.synthesis.OpenAI") as mock_openai_cls:
        mock_client = MagicMock()
        mock_openai_cls.return_value = mock_client
        mock_client.chat.completions.create.return_value = _mock_response(total_tokens=500)
        result = synthesis(_state(findings))
    assert len(result["briefing_items"]) == 4


def test_briefing_item_fields_correct():
    f = _finding()
    with patch("agent.nodes.synthesis.OpenAI") as mock_openai_cls:
        mock_client = MagicMock()
        mock_openai_cls.return_value = mock_client
        mock_client.chat.completions.create.return_value = _mock_response()
        result = synthesis(_state([f]))
    item = result["briefing_items"][0]
    assert "id" in item
    assert item["title"] == f["title"]
    assert item["summary"] == f["summary"]
    assert item["source_url"] == f["source_url"]
    assert item["source_name"] == f["source_name"]
    assert item["category"] == f["category"]
    assert item["confidence_score"] == f["confidence_score"]
    assert item["entities"] == f["entities"]


def test_briefing_item_ids_unique():
    findings = [_finding(title=f"F{i}", source_url=f"https://ex.com/{i}") for i in range(5)]
    with patch("agent.nodes.synthesis.OpenAI") as mock_openai_cls:
        mock_client = MagicMock()
        mock_openai_cls.return_value = mock_client
        mock_client.chat.completions.create.return_value = _mock_response()
        result = synthesis(_state(findings))
    ids = [item["id"] for item in result["briefing_items"]]
    assert len(ids) == len(set(ids))


def test_tokens_and_cost_accumulated():
    with patch("agent.nodes.synthesis.OpenAI") as mock_openai_cls:
        mock_client = MagicMock()
        mock_openai_cls.return_value = mock_client
        mock_client.chat.completions.create.return_value = _mock_response(total_tokens=400)
        result = synthesis(_state([_finding()], tokens_used=100, estimated_cost_usd=0.001))
    assert result["tokens_used"] == 500
    assert abs(result["estimated_cost_usd"] - (0.001 + 400 * 0.000005)) < 1e-9


def test_model_temperature_maxtokens():
    """Verify gpt-4o is called with temperature=0.3 and max_tokens=1500."""
    with patch("agent.nodes.synthesis.OpenAI") as mock_openai_cls:
        mock_client = MagicMock()
        mock_openai_cls.return_value = mock_client
        mock_client.chat.completions.create.return_value = _mock_response()
        synthesis(_state([_finding()]))
    call_kwargs = mock_client.chat.completions.create.call_args
    assert call_kwargs.kwargs["model"] == "gpt-4o"
    assert call_kwargs.kwargs["temperature"] == 0.3
    assert call_kwargs.kwargs["max_tokens"] == 1500


def test_single_llm_call():
    with patch("agent.nodes.synthesis.OpenAI") as mock_openai_cls:
        mock_client = MagicMock()
        mock_openai_cls.return_value = mock_client
        mock_client.chat.completions.create.return_value = _mock_response()
        synthesis(_state([_finding()]))
    assert mock_client.chat.completions.create.call_count == 1


# ── Error path — retry then SYNTHESIS_FAILED ─────────────────────────────────

def test_synthesis_failed_after_two_attempts():
    with patch("agent.nodes.synthesis.OpenAI") as mock_openai_cls:
        mock_client = MagicMock()
        mock_openai_cls.return_value = mock_client
        mock_client.chat.completions.create.side_effect = RuntimeError("API down")
        result = synthesis(_state([_finding()]))
    assert "error" in result
    assert result["error"]["code"] == ErrorCode.SYNTHESIS_FAILED
    assert mock_client.chat.completions.create.call_count == 2


def test_succeeds_on_second_attempt():
    fake_text = "## Signal Weekly Briefing\nRetried successfully."
    with patch("agent.nodes.synthesis.OpenAI") as mock_openai_cls:
        mock_client = MagicMock()
        mock_openai_cls.return_value = mock_client
        mock_client.chat.completions.create.side_effect = [
            RuntimeError("transient"),
            _mock_response(fake_text),
        ]
        result = synthesis(_state([_finding()]))
    assert result["briefing_draft"] == fake_text
    assert mock_client.chat.completions.create.call_count == 2


# ── Context builder ───────────────────────────────────────────────────────────

def test_context_includes_category_title_source_confidence_summary():
    f = _finding(category="funding", title="PayNova Raises $8M", source_name="inc42", confidence_score=0.90)
    ctx = _build_context([f])
    assert "[FUNDING]" in ctx
    assert "PayNova Raises $8M" in ctx
    assert "inc42" in ctx
    assert "0.90" in ctx
    assert f["summary"] in ctx


# ── BriefingItem builder ──────────────────────────────────────────────────────

def test_build_briefing_items_returns_one_per_finding():
    findings = [_finding(title=f"T{i}", source_url=f"https://ex.com/{i}") for i in range(3)]
    items = _build_briefing_items(findings)
    assert len(items) == 3
    for item in items:
        assert "id" in item
        assert "title" in item


if __name__ == "__main__":
    test_empty_findings_returns_no_llm_call()
    test_empty_findings_no_openai_call()
    test_briefing_draft_and_final_populated()
    test_briefing_draft_equals_briefing_final()
    test_briefing_items_count_matches_findings()
    test_briefing_item_fields_correct()
    test_briefing_item_ids_unique()
    test_tokens_and_cost_accumulated()
    test_model_temperature_maxtokens()
    test_single_llm_call()
    test_synthesis_failed_after_two_attempts()
    test_succeeds_on_second_attempt()
    test_context_includes_category_title_source_confidence_summary()
    test_build_briefing_items_returns_one_per_finding()
    print("Synthesis tests passed.")
