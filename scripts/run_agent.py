"""Manual trigger for local Signal agent runs."""

from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from agent.graph import compile_graph  # noqa: E402


def main() -> None:
    graph = compile_graph()
    initial_state = {
        "config": {
            "topic": "AI agent startups",
            "scope_keywords": ["agent", "startup", "LLM"],
        }
    }
    result = graph.invoke(initial_state)
    print(json.dumps(result, indent=2, default=str))


if __name__ == "__main__":
    main()
