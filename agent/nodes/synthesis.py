import os
from uuid import uuid4

from dotenv import load_dotenv
from openai import OpenAI

from agent.state import ErrorCode, SignalState

_SYSTEM_PROMPT = (
    "You are Signal, an Indian startup intelligence agent. "
    "Write a structured weekly briefing from the findings provided. "
    "Format the briefing as follows:\n\n"
    "## Signal Weekly Briefing\n\n"
    "### Executive Summary\n"
    "2-3 sentences summarizing the most important themes this week.\n\n"
    "### Funding Highlights\n"
    "List each funding finding with company, amount, stage, investors.\n\n"
    "### Ecosystem Moves\n"
    "List founder moves, accelerator announcements, hiring signals.\n\n"
    "### Trends to Watch\n"
    "1-2 patterns emerging across multiple findings.\n\n"
    "Prioritize findings with higher confidence scores. "
    "Write clearly for a founder audience. "
    "Do not invent information not present in the findings."
)

_EMPTY_BRIEFING = "No new findings this week."


def _build_context(findings: list[dict]) -> str:
    parts = []
    for f in findings:
        parts.append(
            f"[{f['category'].upper()}] {f['title']}\n"
            f"Source: {f['source_name']} (confidence: {f['confidence_score']:.2f})\n"
            f"{f['summary']}\n"
        )
    return "\n".join(parts)


def _build_briefing_items(findings: list[dict]) -> list[dict]:
    return [
        {
            "id": str(uuid4()),
            "title": f["title"],
            "summary": f["summary"],
            "source_url": f["source_url"],
            "source_name": f["source_name"],
            "category": f["category"],
            "confidence_score": f["confidence_score"],
            "entities": f["entities"],
        }
        for f in findings
    ]


def synthesis(state: SignalState) -> dict:
    findings = state.get("new_findings") or []

    if not findings:
        return {
            "briefing_draft": _EMPTY_BRIEFING,
            "briefing_final": _EMPTY_BRIEFING,
            "briefing_items": [],
        }

    load_dotenv()
    client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))

    context_string = _build_context(findings)

    # One attempt + one retry on failure
    last_exc = None
    for attempt in range(2):
        try:
            response = client.chat.completions.create(
                model="gpt-4o",
                messages=[
                    {"role": "system", "content": _SYSTEM_PROMPT},
                    {"role": "user", "content": context_string},
                ],
                temperature=0.3,
                max_tokens=1500,
            )
            break
        except Exception as exc:
            last_exc = exc
            if attempt == 1:
                return {
                    "error": {
                        "code": ErrorCode.SYNTHESIS_FAILED,
                        "message": str(last_exc),
                    }
                }

    briefing_text = response.choices[0].message.content
    briefing_items = _build_briefing_items(findings)

    tokens = state.get("tokens_used", 0) + response.usage.total_tokens
    cost = state.get("estimated_cost_usd", 0.0) + (response.usage.total_tokens * 0.000005)

    return {
        "briefing_draft": briefing_text,
        "briefing_final": briefing_text,
        "briefing_items": briefing_items,
        "tokens_used": tokens,
        "estimated_cost_usd": cost,
    }
