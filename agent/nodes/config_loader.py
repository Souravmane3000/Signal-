"""Load run configuration into state."""

from __future__ import annotations

import os
from typing import Any

from dotenv import load_dotenv

from agent.state import ErrorCode, SignalState


def config_loader(state: SignalState) -> dict[str, Any]:
    load_dotenv()

    config = state.get("config") or {}
    config.setdefault("openai_api_key", os.getenv("OPENAI_API_KEY"))
    config.setdefault("tavily_api_key", os.getenv("TAVILY_API_KEY"))

    if not config.get("openai_api_key"):
        return {
            "errors": [
                {
                    "code": ErrorCode.CONFIG_LOAD_FAILED,
                    "message": "OPENAI_API_KEY is not set",
                }
            ]
        }

    return {"config": config}
