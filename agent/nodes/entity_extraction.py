import json
import os
from pathlib import Path

from dotenv import load_dotenv
from langsmith.wrappers import wrap_openai
from openai import OpenAI
from pydantic import BaseModel, ValidationError

from agent.state import (
    ALLOWED_CATEGORIES,
    MAX_FINDINGS_PER_RUN,
    MAX_RUN_COST_USD,
    SOURCE_TRUST,
    SignalState,
)

_TOKEN_COST_PER_TOKEN = 0.000000150
_PROMPT_PATH = (
    Path(__file__).resolve().parent.parent / "prompts" / "entity_extraction_v3.txt"
)


class EntityDataModel(BaseModel):
    company_name: str | None = None
    company_name_normalized: str | None = None
    founder_name: str | None = None
    investor_names: list[str] | None = None
    investor_names_normalized: list[str] | None = None
    funding_amount_usd: int | None = None
    funding_stage: str | None = None
    sector: str | None = None
    location: str | None = None
    announced_date: str | None = None
    category: str


def _load_prompt() -> str:
    return _PROMPT_PATH.read_text(encoding="utf-8")


def _entities_from_model(model: EntityDataModel) -> dict:
    data = model.model_dump()
    data.pop("category", None)
    return data


def entity_extraction(state: SignalState) -> dict:
    load_dotenv()
    prompt = _load_prompt()
    client = wrap_openai(OpenAI(api_key=os.getenv("OPENAI_API_KEY")))

    findings = state.get("raw_findings") or []
    scored_findings = []
    tokens_used = 0
    estimated_cost_usd = 0.0

    for index, finding in enumerate(findings):
        if index >= MAX_FINDINGS_PER_RUN:
            print(
                f"MAX_FINDINGS_PER_RUN ({MAX_FINDINGS_PER_RUN}) reached; "
                f"skipping remaining {len(findings) - index} findings"
            )
            break

        if estimated_cost_usd >= MAX_RUN_COST_USD:
            print(
                f"MAX_RUN_COST_USD (${MAX_RUN_COST_USD}) reached; "
                "stopping entity extraction"
            )
            break

        user_msg = f"Title: {finding['title']}\n\nSummary: {finding['summary']}"

        try:
            response = client.chat.completions.create(
                model="gpt-4o-mini",
                messages=[
                    {"role": "system", "content": prompt},
                    {"role": "user", "content": user_msg},
                ],
                temperature=0,
                max_tokens=400,
            )
        except Exception as exc:
            print(f"Entity extraction API error, skipping finding: {exc}")
            continue

        usage_tokens = getattr(getattr(response, "usage", None), "total_tokens", 0) or 0
        tokens_used += usage_tokens
        estimated_cost_usd = tokens_used * _TOKEN_COST_PER_TOKEN

        content = response.choices[0].message.content or ""

        try:
            parsed = json.loads(content)
            model = EntityDataModel.model_validate(parsed)
        except (json.JSONDecodeError, ValidationError, TypeError, ValueError) as exc:
            print(f"Entity extraction parse/validation error, skipping finding: {exc}")
            continue

        category = model.category
        if category not in ALLOWED_CATEGORIES:
            print(
                f"Invalid category '{category}' - falling back to 'funding'"
            )
            category = "funding"

        source_trust_score = float(SOURCE_TRUST.get(finding["source_name"], 0.60))
        freshness_penalty_applied = finding.get("freshness_penalized") is True
        penalty = 0.10 if freshness_penalty_applied else 0.0
        confidence_score = max(0.0, source_trust_score - penalty)

        scored_findings.append(
            {
                "title": finding["title"],
                "summary": finding["summary"],
                "source_url": finding["source_url"],
                "source_name": finding["source_name"],
                "published_date": finding.get("published_date"),
                "entities": _entities_from_model(model),
                "category": category,
                "source_trust_score": source_trust_score,
                "freshness_penalty_applied": freshness_penalty_applied,
                "confidence_score": confidence_score,
                "is_duplicate": False,
                "duplicate_reason": None,
            }
        )

    return {
        "scored_findings": scored_findings,
        "tokens_used": tokens_used,
        "estimated_cost_usd": estimated_cost_usd,
    }
