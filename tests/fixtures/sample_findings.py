SAMPLE_FUNDING_FINDING = {
    "title": "Bengaluru fintech startup PayNova raises $8M Series A led by Elevation Capital",
    "summary": "PayNova, a Bengaluru-based fintech platform, announced an $8 million Series A round led by Elevation Capital with participation from existing investors in March 2025.",
    "source_url": "https://inc42.com/buzz/paynova-series-a",
    "source_name": "inc42",
    "published_date": "2025-03-10",
}

SAMPLE_HIRING_FINDING = {
    "title": "AI startup Sarvam doubles engineering team in Q1 2025",
    "summary": "Sarvam AI has grown its engineering headcount from 20 to 45 in the first quarter, with a focus on hiring NLP researchers.",
    "source_url": "https://yourstory.com/sarvam-hiring",
    "source_name": "yourstory",
    "published_date": "2025-04-01",
}

SAMPLE_SHUTDOWN_FINDING = {
    "title": "Quick commerce startup Dunzo shuts down operations after funding crunch",
    "summary": "Dunzo has officially ceased operations citing inability to raise further funding amid a prolonged cash crunch.",
    "source_url": "https://economictimes.indiatimes.com/dunzo-shutdown",
    "source_name": "economictimes",
    "published_date": "2025-02-15",
}

SAMPLE_ACCELERATOR_FINDING = {
    "title": "Chennai-based logistics startup RouteBox accepted into YC W25 batch",
    "summary": "RouteBox, a logistics optimization startup from Chennai, has been accepted into Y Combinator's Winter 2025 batch.",
    "source_url": "https://ycombinator.com/companies/routebox",
    "source_name": "yc",
    "published_date": "2025-01-20",
}

SAMPLE_OLD_FINDING = {
    "title": "Old funding round republished by aggregator",
    "summary": "This is a stale story that should be dropped by freshness validation.",
    "source_url": "https://aggregator-site.com/old-story",
    "source_name": "rss_other",
    "published_date": "2024-11-01",
}

SAMPLE_UNDATED_FINDING = {
    "title": "Startup news with no parseable date",
    "summary": "This finding has no date and should be penalized but not dropped.",
    "source_url": "https://example.com/undated",
    "source_name": "hn",
    "published_date": None,
}

SAMPLE_OUT_OF_SCOPE_FINDING = {
    "title": "US SaaS startup CloudPeak raises $5M Series A",
    "summary": "CloudPeak, a San Francisco-based SaaS platform, announced a $5 million Series A round.",
    "source_url": "https://example.com/cloudpeak-series-a",
    "source_name": "techcrunch",
    "published_date": "2025-03-01",
    "entities": {
        "company_name": "CloudPeak",
        "company_name_normalized": "cloudpeak",
        "founder_name": "Jane Doe",
        "investor_names": ["Example Ventures"],
        "investor_names_normalized": ["example ventures"],
        "funding_amount_usd": 5000000,
        "funding_stage": "series_a",
        "sector": "saas",
        "location": "San Francisco",
        "announced_date": "2025-03-01",
    },
    "category": "funding",
    "source_trust_score": 0.9,
    "freshness_penalty_applied": False,
    "confidence_score": 0.9,
    "is_duplicate": False,
    "duplicate_reason": None,
}

SAMPLE_SCORED_FUNDING_FINDING = {
    "title": "Bengaluru fintech startup PayNova raises $8M Series A led by Elevation Capital",
    "summary": "PayNova, a Bengaluru-based fintech platform, announced an $8 million Series A round led by Elevation Capital with participation from existing investors in March 2025.",
    "source_url": "https://inc42.com/buzz/paynova-series-a",
    "source_name": "inc42",
    "published_date": "2025-03-10",
    "entities": {
        "company_name": "PayNova",
        "company_name_normalized": "paynova",
        "founder_name": None,
        "investor_names": ["Elevation Capital"],
        "investor_names_normalized": ["elevation capital"],
        "funding_amount_usd": 8000000,
        "funding_stage": "series_a",
        "sector": "fintech",
        "location": "Bengaluru",
        "announced_date": "2025-03-10",
    },
    "category": "funding",
    "source_trust_score": 0.90,
    "freshness_penalty_applied": False,
    "confidence_score": 0.90,
    "is_duplicate": False,
    "duplicate_reason": None,
}

ALL_SAMPLE_RAW_FINDINGS = [
    SAMPLE_FUNDING_FINDING,
    SAMPLE_HIRING_FINDING,
    SAMPLE_SHUTDOWN_FINDING,
    SAMPLE_ACCELERATOR_FINDING,
]
