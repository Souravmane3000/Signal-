import time

import feedparser

from agent.state import RawFinding, SignalState


def _retry(url, max_attempts=2, backoff=None):
    if backoff is None:
        backoff = [5]
    for attempt in range(1, max_attempts + 1):
        try:
            feed = feedparser.parse(url)
            status = getattr(feed, "status", None)
            if status is not None and status >= 400:
                raise ValueError(f"RSS HTTP status {status}")
            if getattr(feed, "bozo", False) and not feed.entries:
                raise ValueError("RSS parse failed with no entries")
            return feed
        except Exception:
            if attempt < max_attempts:
                print(f"RSS feed '{url}' failed attempt {attempt}, retrying...")
                time.sleep(backoff[attempt - 1])
            else:
                print(f"RSS feed '{url}' failed attempt {attempt}, giving up")
                return None
    return None


def google_news_rss_node(state: SignalState) -> dict:
    feed_urls = state["query_plan"]["rss"]
    findings: list[RawFinding] = []
    failed_feeds = 0

    for url in feed_urls:
        feed = _retry(
            url,
            max_attempts=2,
            backoff=[5],
        )
        if feed is None:
            failed_feeds += 1
            continue

        for entry in feed.entries[:10]:
            title = entry.get("title", "")
            if not title:
                continue
            findings.append(
                {
                    "title": title,
                    "summary": entry.get("summary", "")[:400],
                    "source_url": entry.get("link", ""),
                    "source_name": "google_news",
                    "published_date": entry.get("published", None),
                }
            )

    rss_failed = failed_feeds == len(feed_urls) and len(feed_urls) > 0
    return {
        "raw_findings": findings,
        "source_failures": {
            **state.get("source_failures", {}),
            "rss": rss_failed,
        },
    }
