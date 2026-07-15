import time

import httpx

from agent.state import RawFinding, SignalState

# YC fallback chain (ARCHITECTURE): Primary = YC API (this node).
# Fallback = Tavily query scoped to ycombinator.com via include_domains.
# Final = log failure, continue without YC data.
# Phase 1 implements primary + retry only; Tavily fallback is deferred.


def _retry(batch_code, max_attempts=3, backoff=None):
    if backoff is None:
        backoff = [5, 15]
    url = (
        f"https://api.ycombinator.com/v0.1/companies"
        f"?batch={batch_code}&country=India"
    )
    for attempt in range(1, max_attempts + 1):
        try:
            response = httpx.get(url, timeout=10)
            response.raise_for_status()
            response_json = response.json()
            if isinstance(response_json, dict) and "companies" in response_json:
                return response_json["companies"]
            if isinstance(response_json, list):
                return response_json
            raise ValueError("YC response missing companies list")
        except Exception:
            if attempt < max_attempts:
                print(
                    f"YC batch '{batch_code}' failed attempt {attempt}, retrying..."
                )
                time.sleep(backoff[attempt - 1])
            else:
                print(
                    f"YC batch '{batch_code}' failed attempt {attempt}, giving up"
                )
                return None
    return None


def yc_api_node(state: SignalState) -> dict:
    batch_queries = state["query_plan"]["yc"]
    findings: list[RawFinding] = []
    failed_batches = 0

    for batch_query in batch_queries:
        batch_code = batch_query.split("batch=", 1)[1]
        companies = _retry(
            batch_code,
            max_attempts=3,
            backoff=[5, 15],
        )
        if companies is None:
            failed_batches += 1
            print(f"YC batch '{batch_code}' exhausted retries, continuing")
            continue

        for company in companies:
            findings.append(
                {
                    "title": company["name"]
                    + " accepted into YC "
                    + company.get("batch", ""),
                    "summary": company.get("one_liner", "")
                    + " | "
                    + company.get("long_description", "")[:300],
                    "source_url": "https://www.ycombinator.com/companies/"
                    + company.get("slug", ""),
                    "source_name": "yc",
                    "published_date": None,
                }
            )

    yc_failed = failed_batches == len(batch_queries) and len(batch_queries) > 0
    return {
        "raw_findings": findings,
        "source_failures": {
            **state.get("source_failures", {}),
            "yc": yc_failed,
        },
    }
