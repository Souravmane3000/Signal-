import os
import time
from urllib.parse import urlparse

from dotenv import load_dotenv
from tavily import TavilyClient

from agent.state import RawFinding, SignalState

INCLUDE_DOMAINS = [
    "inc42.com",
    "yourstory.com",
    "economictimes.indiatimes.com",
    "entrackr.com",
    "techcrunch.com",
    "livemint.com",
    "thehindu.com",
]


def _domain_to_source(url: str) -> str:
    host = urlparse(url).netloc.lower()
    if host.startswith("www."):
        host = host[4:]
    if not host:
        return "rss_other"
    return host.split(".")[0]


def _retry(client, query, include_domains, max_attempts=3, backoff=None):
    if backoff is None:
        backoff = [5, 15]
    for attempt in range(1, max_attempts + 1):
        try:
            results = client.search(
                query=query,
                search_depth="advanced",
                max_results=5,
                include_domains=include_domains,
            )
            return results.get("results", [])
        except Exception:
            if attempt < max_attempts:
                print(
                    f"Tavily query '{query}' failed attempt {attempt}, retrying..."
                )
                time.sleep(backoff[attempt - 1])
            else:
                print(
                    f"Tavily query '{query}' failed attempt {attempt}, retrying..."
                )
                return None
    return None


def tavily_search(state: SignalState) -> dict:
    load_dotenv()
    client = TavilyClient(api_key=os.getenv("TAVILY_API_KEY"))
    queries = state["query_plan"]["tavily"]

    findings: list[RawFinding] = []
    failed_queries = 0

    for query in queries:
        results = _retry(
            client,
            query,
            INCLUDE_DOMAINS,
            max_attempts=3,
            backoff=[5, 15],
        )
        if results is None:
            failed_queries += 1
            continue
        for result in results:
            findings.append(
                {
                    "title": result["title"],
                    "summary": result.get("content", "")[:500],
                    "source_url": result["url"],
                    "source_name": _domain_to_source(result["url"]),
                    "published_date": result.get("published_date", None),
                }
            )

    tavily_failed = failed_queries == len(queries) and len(queries) > 0
    return {
        "raw_findings": findings,
        "source_failures": {
            **state.get("source_failures", {}),
            "tavily": tavily_failed,
        },
    }
