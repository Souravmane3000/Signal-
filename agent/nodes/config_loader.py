import os
from datetime import datetime, timezone

from dotenv import load_dotenv

from agent.state import SignalState


def config_loader(state: SignalState) -> dict:
    load_dotenv()

    user_config = {
        "user_id": "user_001",
        "keywords": [
            "Indian startup",
            "funding India",
            "seed round India",
            "Series A India",
        ],
        "verticals": ["AI", "fintech", "healthtech", "B2B SaaS", "climate", "edtech"],
        "stage_filter": ["seed", "series_a", "series_b"],
        "delivery_email": "test@example.com",
        "schedule_freq": "weekly",
    }

    procedural_memory = {
        "high_signal_categories": ["funding", "accelerator"],
        "low_signal_categories": [],
        "trusted_sources": ["inc42", "yc"],
        "preferred_stage": ["seed", "series_a"],
        "query_boost_terms": ["Bengaluru", "B2B SaaS"],
        "query_suppress_terms": ["Infosys", "Wipro", "IT services"],
        "source_weights": {
            "tavily": 1.0,
            "yc": 1.0,
            "hn": 0.7,
            "google_news": 0.65,
        },
        "min_confidence_threshold": 0.70,
    }

    return {
        "user_config": user_config,
        "user_id": "user_001",
        "thread_id": "run_" + str(int(datetime.now(timezone.utc).timestamp())),
        "run_type": "manual",
        "graph_version": os.getenv("GRAPH_VERSION", "1.0"),
        "semantic_memory": {},
        "procedural_memory": procedural_memory,
        "source_failures": {
            "tavily": False,
            "yc": False,
            "hn": False,
            "rss": False,
        },
    }
