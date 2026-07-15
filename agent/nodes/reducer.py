from agent.state import SignalState


def reducer(state: SignalState) -> dict:
    raw_findings = state["raw_findings"]
    print(f"Reducer: {len(raw_findings)} total findings merged from all research nodes")
    return {"raw_findings": state["raw_findings"]}
