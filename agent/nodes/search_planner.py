from datetime import datetime, timezone

from agent.state import SignalState


def get_recent_yc_batches() -> list[str]:
    now = datetime.now(timezone.utc)
    year = now.year
    month = now.month

    if 1 <= month <= 4:
        season = "W"
    elif 5 <= month <= 8:
        season = "S"
    else:
        season = "F"

    two_digit_year = str(year)[2:]
    current_batch = season + two_digit_year

    if season == "W":
        previous_season = "F"
        previous_year = year - 1
    elif season == "S":
        previous_season = "W"
        previous_year = year
    else:
        previous_season = "S"
        previous_year = year

    previous_batch = previous_season + str(previous_year)[2:]
    return [current_batch, previous_batch]


def search_planner(state: SignalState) -> dict:
    procedural_memory = state["procedural_memory"]
    query_boost_terms = procedural_memory.get("query_boost_terms", [])
    query_suppress_terms = procedural_memory.get("query_suppress_terms", [])

    now = datetime.now(timezone.utc)
    current_month_name = now.strftime("%B")
    current_year = now.year

    tavily_queries = [
        "Indian startup funding seed round this week",
        f"India Series A funding announcement {current_month_name} {current_year}",
        "YC batch India founder startup",
        "Indian B2B SaaS startup funding",
        "Bengaluru Mumbai startup ecosystem news",
    ]
    for term in query_boost_terms[:3]:
        tavily_queries.append(term)

    yc_batches = get_recent_yc_batches()
    yc_queries = [f"batch={batch_code}" for batch_code in yc_batches]

    hn_queries = [
        "Indian startup",
        "Show HN India founder",
        "Who is hiring India startup",
    ]

    rss_queries = [
        "https://news.google.com/rss/search?q=indian+startup+funding&hl=en-IN&gl=IN&ceid=IN:en",
        "https://news.google.com/rss/search?q=India+Series+A+seed+funding&hl=en-IN&gl=IN&ceid=IN:en",
    ]

    query_plan = {
        "tavily": tavily_queries,
        "yc": yc_queries,
        "hn": hn_queries,
        "rss": rss_queries,
    }

    return {
        "query_plan": query_plan,
        "sources_queried": ["tavily", "yc", "hn", "rss"],
        "run_config_snapshot": {
            "query_plan": query_plan,
            "procedural_memory": state.get("procedural_memory", {}),
        },
    }
