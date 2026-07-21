from agent.state import SignalState


def source_trust_scoring(state: SignalState) -> dict:
    findings = state["scored_findings"]
    sorted_findings = sorted(
        findings,
        key=lambda finding: finding["confidence_score"],
        reverse=True,
    )
    return {"scored_findings": sorted_findings}
