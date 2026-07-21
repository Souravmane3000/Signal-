from agent.state import SignalState


def run_metrics_writer(state: SignalState) -> dict:
    source_failures = state.get("source_failures", {})

    metrics = {
        "run_id": state.get("run_id", ""),
        "graph_version": state.get("graph_version", "unknown"),
        "sources_queried": state.get("sources_queried", []),
        "findings_retrieved": state.get("findings_retrieved", 0),
        "findings_dropped_freshness": state.get("findings_dropped_freshness", 0),
        "findings_dropped_scope": state.get("findings_dropped_scope", 0),
        "findings_dropped_dedup": state.get("findings_dropped_dedup", 0),
        "findings_in_briefing": len(state.get("new_findings", [])),
        "tokens_used": state.get("tokens_used", 0),
        "estimated_cost_usd": state.get("estimated_cost_usd", 0.0),
        "source_health": source_failures,
    }

    print("--- Run Metrics ---")
    for key, value in metrics.items():
        print(f"{key}: {value}")

    for source, failed in source_failures.items():
        if failed:
            print(f"WARNING: {source} failed this run")

    return {}
