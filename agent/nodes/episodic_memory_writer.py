from datetime import datetime, timezone

from agent.state import SignalState

EPISODIC_MEMORY_STORE: list[dict] = []


def episodic_memory_writer(state: SignalState) -> dict:
    new_findings = state["new_findings"]
    run_id = state.get("run_id", "")
    thread_id = state.get("thread_id", "")
    briefing_final = state.get("briefing_final", "")

    item_titles = [f["title"] for f in new_findings]
    source_urls = [f["source_url"] for f in new_findings]
    company_names_normalized = [
        f["entities"].get("company_name_normalized")
        for f in new_findings
        if f.get("entities") and f["entities"].get("company_name_normalized")
    ]

    episode = {
        "run_id": run_id,
        "thread_id": thread_id,
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "item_titles": item_titles,
        "source_urls": source_urls,
        "company_names_normalized": company_names_normalized,
        "briefing_summary": briefing_final[:200],
    }

    EPISODIC_MEMORY_STORE.append(episode)

    print(
        f"Episodic memory written: {len(item_titles)} items recorded for run {run_id}"
    )

    return {}
