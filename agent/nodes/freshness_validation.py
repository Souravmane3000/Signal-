from datetime import datetime, timezone

from agent.state import SignalState

FRESHNESS_WINDOW_DAYS = 30

_DATE_FORMATS = (
    "%Y-%m-%dT%H:%M:%SZ",
    "%Y-%m-%d",
    "%a, %d %b %Y %H:%M:%S %z",
)


def _parse_published_date(published_date: str | None):
    if published_date is None:
        return None
    for fmt in _DATE_FORMATS:
        try:
            return datetime.strptime(published_date, fmt).date()
        except ValueError:
            continue
    return None


def freshness_validation(state: SignalState) -> dict:
    findings = state["raw_findings"]
    today = datetime.now(timezone.utc).date()

    kept = []
    dropped = 0
    penalized = 0

    for finding in findings:
        parsed_date = _parse_published_date(finding.get("published_date"))

        if parsed_date is None:
            kept.append({**finding, "freshness_penalized": True})
            penalized += 1
            continue

        age_days = (today - parsed_date).days
        if age_days > FRESHNESS_WINDOW_DAYS:
            dropped += 1
            continue

        kept.append({**finding, "freshness_penalized": False})

    print(
        f"Freshness validation: {len(kept)} kept, {dropped} dropped, "
        f"{penalized} penalized (no date)"
    )

    return {
        "raw_findings": kept,
        "findings_dropped_freshness": dropped,
        "findings_retrieved": len(findings),
    }
