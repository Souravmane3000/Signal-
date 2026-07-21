from agent.state import SignalState

NON_INDIA_LOCATIONS = [
    "san francisco",
    "new york",
    "london",
    "beijing",
    "shanghai",
    "singapore",
    "tokyo",
    "berlin",
    "paris",
    "dubai",
]

OUT_OF_SCOPE_STAGES = {
    "series_c",
    "series_d",
    "series_e",
    "ipo",
    "private_equity",
}

_MIN_FUNDING_USD = 500_000
_MAX_FUNDING_USD = 50_000_000


def _is_out_of_scope(finding: dict) -> bool:
    entities = finding.get("entities") or {}

    location = entities.get("location", None)
    if location is not None:
        location_lower = location.lower()
        if any(non_india in location_lower for non_india in NON_INDIA_LOCATIONS):
            return True

    amount = entities.get("funding_amount_usd", None)
    if amount is not None:
        if amount < _MIN_FUNDING_USD or amount > _MAX_FUNDING_USD:
            return True

    stage = entities.get("funding_stage", None)
    if stage is not None:
        if stage.lower() in OUT_OF_SCOPE_STAGES:
            return True

    return False


def scope_filter(state: SignalState) -> dict:
    findings = state["scored_findings"]
    kept = []
    dropped = 0

    for finding in findings:
        if _is_out_of_scope(finding):
            dropped += 1
            continue
        kept.append(finding)

    print(f"Scope filter: {len(kept)} kept, {dropped} dropped")

    return {
        "scored_findings": kept,
        "findings_dropped_scope": dropped,
    }
