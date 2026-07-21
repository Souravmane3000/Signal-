import time

from dotenv import load_dotenv

load_dotenv()

from agent.graph import run_graph  # noqa: E402

if __name__ == "__main__":
    print("Starting Signal agent run...")
    start = time.time()

    final_state = run_graph()

    duration = time.time() - start

    print("\n" + "=" * 60)
    print("SIGNAL WEEKLY BRIEFING")
    print("=" * 60)
    print(final_state.get("briefing_final", "No briefing generated"))
    print("=" * 60)
    print(f"\nRun complete in {duration:.1f}s")
    print(f"Graph version: {final_state.get('graph_version', 'unknown')}")
    print(f"Findings retrieved: {final_state.get('findings_retrieved', 0)}")
    print(f"Dropped (freshness): {final_state.get('findings_dropped_freshness', 0)}")
    print(f"Dropped (scope): {final_state.get('findings_dropped_scope', 0)}")
    print(f"Dropped (dedup): {final_state.get('findings_dropped_dedup', 0)}")
    print(f"In briefing: {len(final_state.get('new_findings', []))}")
    print(f"Tokens used: {final_state.get('tokens_used', 0)}")
    print(f"Estimated cost: ${final_state.get('estimated_cost_usd', 0.0):.4f}")
    print(f"Source failures: {final_state.get('source_failures', {})}")
