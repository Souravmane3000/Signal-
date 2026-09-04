"""Print live-cursor vs checkpoint vs LangSmith child for one thread.

Usage (run from repo root while a pipeline is in flight):

    python scripts/debug_live_stage.py --thread-id run_abc123 --token <jwt>

    python scripts/debug_live_stage.py --thread-id run_abc123 --token <jwt> \\
        --base-url http://127.0.0.1:8080
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import urllib.error
import urllib.request

from pathlib import Path

from dotenv import load_dotenv

_REPO_ROOT = Path(__file__).resolve().parents[1]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

load_dotenv(_REPO_ROOT / ".env")


def _get(url: str, token: str) -> tuple[int, dict]:
    req = urllib.request.Request(
        url,
        headers={"Authorization": f"Bearer {token}", "Accept": "application/json"},
        method="GET",
    )
    try:
        with urllib.request.urlopen(req, timeout=15) as resp:
            raw = resp.read().decode()
            return resp.status, json.loads(raw) if raw else {}
    except urllib.error.HTTPError as exc:
        raw = exc.read().decode()
        try:
            body = json.loads(raw) if raw else {}
        except json.JSONDecodeError:
            body = {"raw": raw[:400]}
        return exc.code, body


def main() -> int:
    parser = argparse.ArgumentParser(description="Debug live pipeline stage for a thread.")
    parser.add_argument("--thread-id", required=True)
    parser.add_argument("--token", required=True, help="Bearer JWT from POST /auth/login")
    parser.add_argument(
        "--base-url",
        default=os.getenv("SIGNAL_API_BASE", "http://127.0.0.1:8080"),
    )
    args = parser.parse_args()

    from agent.graph import (
        get_live_node,
        graph,
        lookup_langsmith_pipeline_node,
        pipeline_stage,
    )

    tid = args.thread_id
    config = {"configurable": {"thread_id": tid}}
    live = get_live_node(tid)
    ls_node = lookup_langsmith_pipeline_node(tid)
    snap = graph.get_state(config)
    nxt = tuple(getattr(snap, "next", None) or ())
    status_code, api_body = _get(
        f"{args.base_url.rstrip('/')}/agent/status?thread_id={tid}",
        args.token,
    )

    print("thread_id", tid)
    print("live_map", live, pipeline_stage(live) if live else None)
    print("langsmith_child", ls_node, pipeline_stage(ls_node) if ls_node else None)
    print("checkpoint_next", nxt)
    print("GET /agent/status", status_code, api_body)
    return 0 if status_code == 200 else 1


if __name__ == "__main__":
    sys.exit(main())
