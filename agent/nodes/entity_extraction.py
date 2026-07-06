"""Extract entities from validated findings using LLM prompt."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from agent.state import PROMPT_PATH_ENTITY_EXTRACTION, EntityRecord, SignalState


def _load_prompt() -> str:
    path = Path(PROMPT_PATH_ENTITY_EXTRACTION)
    if path.exists():
        return path.read_text(encoding="utf-8")
    return ""


def entity_extraction(state: SignalState) -> dict[str, Any]:
    _ = _load_prompt()
    entities: list[EntityRecord] = []
    return {"entities": entities}
