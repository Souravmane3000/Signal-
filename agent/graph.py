import os
import re
from urllib.parse import quote
from uuid import uuid4

from dotenv import load_dotenv
from langgraph.checkpoint.postgres import PostgresSaver
from langgraph.graph import END, START, StateGraph
from langgraph.store.postgres import PostgresStore
from psycopg.rows import dict_row
from psycopg_pool import ConnectionPool

from agent.nodes.config_loader import config_loader
from agent.nodes.delivery import delivery
from agent.nodes.discard_and_log import discard_and_log
from agent.nodes.entity_extraction import entity_extraction
from agent.nodes.episodic_memory_writer import episodic_memory_writer
from agent.nodes.freshness_validation import freshness_validation
from agent.nodes.google_news_rss import google_news_rss_node
from agent.nodes.hn_algolia import hn_algolia_node
from agent.nodes.hitl import hitl_node, route_after_hitl
from agent.nodes.hybrid_dedup import hybrid_dedup
from agent.nodes.reducer import reducer
from agent.nodes.run_metrics_writer import run_metrics_writer
from agent.nodes.scope_filter import scope_filter
from agent.nodes.search_planner import search_planner
from agent.nodes.source_trust_scoring import source_trust_scoring
from agent.nodes.synthesis import synthesis
from agent.nodes.tavily_search import tavily_search
from agent.nodes.yc_api import yc_api_node
from agent.state import SignalState

load_dotenv()

_raw_db_url = os.getenv("DATABASE_URL")
if not _raw_db_url:
    raise RuntimeError(
        "DATABASE_URL is not set. Add it to .env before importing agent.graph. "
        "SIG-P2-002 stop condition: DATABASE_URL missing."
    )


def _encode_db_url(url: str) -> str:
    """Percent-encode the password component so special chars (#, %) are valid."""
    match = re.match(
        r"^(postgresql(?:\+\w+)?://)([^:@/]+):(.+)@([^/]+)(/.*)?$",
        url,
    )
    if not match:
        return url
    scheme, user, password, hostport, path = match.groups()
    return f"{scheme}{user}:{quote(password, safe='')}@{hostport}{path or ''}"


_DB_URL = _encode_db_url(_raw_db_url)


def _compat_side_effect(node_fn):
    """Adapt BUILD_SPEC side-effect nodes (return {}) for LangGraph StateGraph.

    This LangGraph version rejects empty dict updates:
    all(k not in output_keys for k in {}) is True → InvalidUpdateError.
    Echo an existing SignalState field as a no-op write so the node may
    complete without changing schema or node semantics.
    """

    def wrapped(state: SignalState) -> dict:
        result = node_fn(state)
        if result:
            return result
        return {"run_id": state.get("run_id", "")}

    return wrapped


builder = StateGraph(SignalState)

# Node 1-15 in exact BUILD_SPEC order
builder.add_node("config_loader", config_loader)
builder.add_node("search_planner", search_planner)
builder.add_node("tavily_search", tavily_search)
builder.add_node("yc_api_node", yc_api_node)
builder.add_node("hn_algolia_node", hn_algolia_node)
builder.add_node("google_news_rss_node", google_news_rss_node)
builder.add_node("reducer", reducer)
builder.add_node("freshness_validation", freshness_validation)
builder.add_node("entity_extraction", entity_extraction)
builder.add_node("scope_filter", scope_filter)
builder.add_node("source_trust_scoring", source_trust_scoring)
builder.add_node("hybrid_dedup", hybrid_dedup)
builder.add_node("synthesis", synthesis)
builder.add_node("hitl_node", hitl_node)
builder.add_node("discard_and_log", discard_and_log)
builder.add_node(
    "episodic_memory_writer", _compat_side_effect(episodic_memory_writer)
)
builder.add_node("delivery", delivery)
builder.add_node("run_metrics_writer", _compat_side_effect(run_metrics_writer))

# Edges through Synthesis unchanged; HITL inserted after Synthesis (SIG-018).
# Delivery on Approve/Edit path only (SIG-020A): episodic → delivery → metrics.
builder.add_edge(START, "config_loader")
builder.add_edge("config_loader", "search_planner")
builder.add_edge("search_planner", "tavily_search")
builder.add_edge("tavily_search", "yc_api_node")
builder.add_edge("yc_api_node", "hn_algolia_node")
builder.add_edge("hn_algolia_node", "google_news_rss_node")
builder.add_edge("google_news_rss_node", "reducer")
builder.add_edge("reducer", "freshness_validation")
builder.add_edge("freshness_validation", "entity_extraction")
builder.add_edge("entity_extraction", "scope_filter")
builder.add_edge("scope_filter", "source_trust_scoring")
builder.add_edge("source_trust_scoring", "hybrid_dedup")
builder.add_edge("hybrid_dedup", "synthesis")
builder.add_edge("synthesis", "hitl_node")
builder.add_conditional_edges(
    "hitl_node",
    route_after_hitl,
    {
        "episodic_memory_writer": "episodic_memory_writer",
        "discard_and_log": "discard_and_log",
    },
)
# Approve/Edit: episodic → delivery → metrics (DEC-004 ordering)
builder.add_edge("episodic_memory_writer", "delivery")
builder.add_edge("delivery", "run_metrics_writer")
# Reject: discard → metrics (DEC-004: no episodic write, no delivery)
builder.add_edge("discard_and_log", "run_metrics_writer")
builder.add_edge("run_metrics_writer", END)

# Phase 2 persistence — PostgresSaver + PostgresStore.
# Official LangGraph pattern for long-lived graphs: ConnectionPool (not a raw
# Connection held via ExitStack/from_conn_string). A single Connection goes idle
# during multi-minute LLM nodes and is dropped by Supabase; the pool checks out
# a healthy connection per checkpoint write and reconnects as needed.
#
# keepalives: prevent Supabase from silently dropping idle pooled connections
# during long LLM nodes (SSL SYSCALL EOF / "connection is lost").
# supports_pipeline=False: put() defaults to pipeline mode; a dropped mid-pipeline
# connection surfaces as Pipeline[BAD]. Transaction mode recovers cleanly via the
# pool's check/reconnect path instead.
_pool = ConnectionPool(
    conninfo=_DB_URL,
    min_size=1,
    max_size=5,
    kwargs={
        "autocommit": True,
        "prepare_threshold": 0,
        "row_factory": dict_row,
        "keepalives": 1,
        "keepalives_idle": 30,
        "keepalives_interval": 10,
        "keepalives_count": 5,
    },
    check=ConnectionPool.check_connection,
)

_postgres_saver = PostgresSaver(_pool)
_postgres_saver.supports_pipeline = False
_postgres_saver.setup()

_postgres_store = PostgresStore(_pool)
_postgres_store.setup()

graph = builder.compile(checkpointer=_postgres_saver, store=_postgres_store)


def run_graph() -> dict:
    initial_state = {
        "run_id": str(uuid4()),
        "raw_findings": [],
        "scored_findings": [],
        "new_findings": [],
        "briefing_items": [],
        "sources_queried": [],
        "findings_retrieved": 0,
        "findings_dropped_freshness": 0,
        "findings_dropped_dedup": 0,
        "findings_dropped_scope": 0,
        "tokens_used": 0,
        "estimated_cost_usd": 0.0,
        "run_duration_seconds": 0.0,
        "run_config_snapshot": {},
        "error": None,
        "source_failures": {},
        "semantic_memory": {},
        "procedural_memory": {},
        "query_plan": {},
        "user_config": {},
        "user_id": "",
        "thread_id": "",
        "run_type": "manual",
        "graph_version": os.getenv("GRAPH_VERSION", "1.0"),
        "hitl_decision": None,
        "hitl_edits": None,
        "delivery_status": None,
        "briefing_draft": "",
        "briefing_final": "",
    }
    return graph.invoke(
        initial_state,
        config={"configurable": {"thread_id": "run_001"}},
    )
