import time
from urllib.parse import quote

import httpx

from agent.state import RawFinding, SignalState


def _retry(query, max_attempts=3, backoff=None):
    if backoff is None:
        backoff = [5, 15]
    url = (
        "https://hn.algolia.com/api/v1/search"
        f"?query={quote(query)}&tags=story&hitsPerPage=5"
    )
    for attempt in range(1, max_attempts + 1):
        try:
            response = httpx.get(url, timeout=10)
            response.raise_for_status()
            response_json = response.json()
            if not isinstance(response_json, dict):
                raise ValueError("HN response is not a JSON object")
            return response_json.get("hits", [])
        except Exception:
            if attempt < max_attempts:
                print(
                    f"HN query '{query}' failed attempt {attempt}, retrying..."
                )
                time.sleep(backoff[attempt - 1])
            else:
                print(
                    f"HN query '{query}' failed attempt {attempt}, giving up"
                )
                return None
    return None


def hn_algolia_node(state: SignalState) -> dict:
    queries = state["query_plan"]["hn"]
    findings: list[RawFinding] = []
    failed_queries = 0

    for query in queries:
        hits = _retry(
            query,
            max_attempts=3,
            backoff=[5, 15],
        )
        if hits is None:
            failed_queries += 1
            continue

        for hit in hits:
            title = hit.get("title", "")
            summary = hit.get("story_text", "") or hit.get("comment_text", "") or ""
            summary = summary[:400]
            source_url = hit.get("url", "") or (
                "https://news.ycombinator.com/item?id="
                + str(hit.get("objectID", ""))
            )
            if not title or not source_url:
                continue
            findings.append(
                {
                    "title": title,
                    "summary": summary,
                    "source_url": source_url,
                    "source_name": "hn",
                    "published_date": hit.get("created_at", None),
                }
            )

    hn_failed = failed_queries == len(queries) and len(queries) > 0
    return {
        "raw_findings": findings,
        "source_failures": {
            **state.get("source_failures", {}),
            "hn": hn_failed,
        },
    }
