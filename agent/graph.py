import os
import re
import threading
import time
from dataclasses import dataclass
from typing import Any, Optional
from urllib.parse import quote
from uuid import uuid4

from dotenv import load_dotenv
from langchain_core.callbacks import BaseCallbackHandler
from langchain_core.callbacks.manager import CallbackManager
from langgraph.checkpoint.postgres import PostgresSaver
from langgraph.graph import END, START, StateGraph
from langgraph.store.postgres import PostgresStore
from psycopg import OperationalError
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

# Frozen display order for live dashboard stage (matches node ids / LangSmith spans).
PIPELINE_NODES: tuple[str, ...] = (
    "config_loader",
    "search_planner",
    "tavily_search",
    "yc_api_node",
    "hn_algolia_node",
    "google_news_rss_node",
    "reducer",
    "freshness_validation",
    "entity_extraction",
    "scope_filter",
    "source_trust_scoring",
    "hybrid_dedup",
    "synthesis",
    "hitl_node",
    "discard_and_log",
    "episodic_memory_writer",
    "delivery",
    "run_metrics_writer",
)

PIPELINE_LABELS: dict[str, str] = {
    "config_loader": "Loading configuration",
    "search_planner": "Planning searches",
    "tavily_search": "Searching the web",
    "yc_api_node": "Checking YC companies",
    "hn_algolia_node": "Scanning Hacker News",
    "google_news_rss_node": "Reading Google News",
    "reducer": "Merging findings",
    "freshness_validation": "Checking freshness",
    "entity_extraction": "Extracting entities",
    "scope_filter": "Filtering scope",
    "source_trust_scoring": "Scoring sources",
    "hybrid_dedup": "Removing duplicates",
    "synthesis": "Writing briefing",
    "hitl_node": "Awaiting your review",
    "discard_and_log": "Discarding draft",
    "episodic_memory_writer": "Saving memory",
    "delivery": "Sending briefing",
    "run_metrics_writer": "Recording metrics",
}


def pipeline_stage(node: Optional[str]) -> dict:
    """Map a graph node id to live-status fields. Idle/unknown → nulls."""
    if not node:
        return {
            "current_node": None,
            "current_label": None,
            "step_index": None,
            "step_total": None,
        }
    label = PIPELINE_LABELS.get(node) or node.replace("_", " ")
    try:
        index = PIPELINE_NODES.index(node) + 1
    except ValueError:
        return {
            "current_node": node,
            "current_label": label,
            "step_index": None,
            "step_total": None,
        }
    return {
        "current_node": node,
        "current_label": label,
        "step_index": index,
        "step_total": len(PIPELINE_NODES),
    }


_PIPELINE_NODES_SET = frozenset(PIPELINE_NODES)
_live_nodes: dict[str, str] = {}
_live_lock = threading.Lock()
_ls_lookup_cache: dict[str, tuple[float, Optional[str]]] = {}
_LS_LOOKUP_TTL_SEC = 2.0
_LS_LOOKUP_JOIN_SEC = 0.4


def set_live_node(thread_id: str, node: str) -> None:
    if not thread_id or node not in _PIPELINE_NODES_SET:
        return
    with _live_lock:
        _live_nodes[thread_id] = node


def get_live_node(thread_id: str) -> Optional[str]:
    if not thread_id:
        return None
    with _live_lock:
        return _live_nodes.get(thread_id)


def clear_live_node(thread_id: str) -> None:
    if not thread_id:
        return
    with _live_lock:
        _live_nodes.pop(thread_id, None)


def _callback_pipeline_node(serialized: Any, name: Optional[str], kwargs: dict) -> Optional[str]:
    candidates = [
        name,
        kwargs.get("name"),
        (serialized or {}).get("name") if isinstance(serialized, dict) else None,
    ]
    sid = (serialized or {}).get("id") if isinstance(serialized, dict) else None
    if isinstance(sid, (list, tuple)) and sid:
        candidates.append(sid[-1])
    for candidate in candidates:
        if isinstance(candidate, str) and candidate in _PIPELINE_NODES_SET:
            return candidate
    return None


class PipelineProgressHandler(BaseCallbackHandler):
    """Process-local cursor: last started PIPELINE_NODES name for a thread_id."""

    def __init__(self, thread_id: str):
        super().__init__()
        self.thread_id = thread_id

    def on_chain_start(
        self,
        serialized: Any,
        inputs: Any,
        *,
        run_id: Any = None,
        parent_run_id: Any = None,
        tags: Any = None,
        metadata: Any = None,
        name: Optional[str] = None,
        **kwargs: Any,
    ) -> None:
        node = _callback_pipeline_node(serialized, name, kwargs)
        if node:
            set_live_node(self.thread_id, node)


def _langsmith_run_in_progress(run: Any) -> bool:
    if getattr(run, "end_time", None):
        return False
    status = str(getattr(run, "status", "") or "").lower()
    if status in ("success", "error", "completed"):
        return False
    return True


def _langsmith_run_thread_id(run: Any) -> str:
    extra = getattr(run, "extra", None) or {}
    metadata = getattr(run, "metadata", None) or {}
    if not isinstance(metadata, dict):
        metadata = {}
    if isinstance(extra, dict):
        nested = extra.get("metadata") or {}
        if isinstance(nested, dict):
            metadata = {**nested, **metadata}
    return str(metadata.get("thread_id") or "")


def _lookup_langsmith_pipeline_node_uncached(thread_id: str) -> Optional[str]:
    if os.getenv("PYTEST_CURRENT_TEST"):
        return None
    tracing = (
        os.getenv("LANGCHAIN_TRACING_V2")
        or os.getenv("LANGSMITH_TRACING")
        or ""
    ).lower()
    if tracing not in ("true", "1"):
        return None
    if not (os.getenv("LANGCHAIN_API_KEY") or os.getenv("LANGSMITH_API_KEY")):
        return None
    if not re.fullmatch(r"[A-Za-z0-9_-]{1,64}", thread_id or ""):
        return None
    try:
        from langsmith import Client

        client = Client()
        kwargs: dict[str, Any] = {
            "limit": 20,
            "is_root": False,
            "filter": f'has(metadata, \'{{"thread_id": "{thread_id}"}}\')',
        }
        project = os.getenv("LANGCHAIN_PROJECT") or os.getenv("LANGSMITH_PROJECT")
        if project:
            kwargs["project_name"] = project.strip().strip('"').strip("'")
        for run in client.list_runs(**kwargs):
            if not _langsmith_run_in_progress(run):
                continue
            name = getattr(run, "name", None)
            if name not in _PIPELINE_NODES_SET:
                continue
            if _langsmith_run_thread_id(run) == thread_id:
                return str(name)
    except Exception:
        return None
    return None


def lookup_langsmith_pipeline_node(thread_id: str) -> Optional[str]:
    """Best-effort in-progress child span. Fail open; never the primary clock."""
    if not thread_id:
        return None
    now = time.monotonic()
    cached = _ls_lookup_cache.get(thread_id)
    if cached and now - cached[0] < _LS_LOOKUP_TTL_SEC:
        return cached[1]

    box: list[Optional[str]] = []

    def _work() -> None:
        try:
            box.append(_lookup_langsmith_pipeline_node_uncached(thread_id))
        except Exception:
            box.append(None)

    worker = threading.Thread(target=_work, daemon=True)
    worker.start()
    worker.join(_LS_LOOKUP_JOIN_SEC)
    if worker.is_alive() or not box:
        return None
    node = box[0]
    _ls_lookup_cache[thread_id] = (now, node)
    return node


def graph_invoke_config(thread_id: str, *, run_type: str = "manual", user_id: str = "") -> dict:
    """LangGraph invoke config plus LangSmith run_name/metadata (same thread_id)."""
    metadata: dict = {"thread_id": thread_id, "run_type": run_type}
    if user_id:
        metadata["user_id"] = user_id
    handler = PipelineProgressHandler(thread_id)
    # Merge into tracing (do not replace LANGCHAIN/LANGSMITH tracers).
    callbacks = CallbackManager.configure(inheritable_callbacks=[handler])
    return {
        "configurable": {"thread_id": thread_id},
        "run_name": "signal-pipeline",
        "metadata": metadata,
        "callbacks": callbacks,
    }


# Phase 2 persistence — PostgresSaver + PostgresStore.
# Official LangGraph pattern for long-lived graphs: ConnectionPool (not a raw
# Connection held via ExitStack/from_conn_string). A single Connection goes idle
# during multi-minute LLM nodes / HITL waits and is dropped by Supabase; the pool
# must discard those sockets on checkout and replace them before checkpoint writes.
#
# Hardening (psycopg_pool + Supabase / PgBouncer):
# - check: SELECT-ping on every checkout; close the socket if the ping fails so a
#   half-dead SSL session is never returned to the idle pool.
# - max_idle < Supabase idle kill window so unused conns are closed by the pool
#   before the server/proxy silently tears them down (SSL SYSCALL EOF).
# - max_lifetime: recycle long-lived sockets even if still "alive".
# - TCP keepalives: detect middlebox/server drops while a conn sits in the pool.
# - prepare_threshold=0: required for PgBouncer transaction pooling.
# - supports_pipeline=False: pipeline mode surfaces half-closed sockets as
#   Pipeline[BAD] / SSL framing errors instead of a clean OperationalError the
#   pool can discard.
def _check_pool_connection(conn) -> None:
    """Checkout health check — discard the socket if the ping fails."""
    try:
        ConnectionPool.check_connection(conn)
    except Exception:
        try:
            conn.close()
        except Exception:
            pass
        raise


def _log_pool_reconnect_failed(p: ConnectionPool) -> None:
    """Surface prolonged reconnect failure without crashing the process."""
    import logging

    logging.getLogger(__name__).error(
        "Postgres ConnectionPool %r failed to reconnect within reconnect_timeout",
        getattr(p, "name", p),
    )


pool = ConnectionPool(
    conninfo=_DB_URL,
    # min_size=0 so max_idle can close *all* idle sockets (max_idle only
    # shrinks above min_size). A sticky min_size=1 conn survives HITL/LLM
    # waits and is the classic Supabase SSL EOF victim.
    min_size=0,
    max_size=5,
    open=True,
    timeout=30.0,
    # Close idle pooled connections before Supabase/PgBouncer drops them
    # (~5–10 min typical). Default max_idle=600 is too long for cloud proxies.
    max_idle=180.0,
    max_lifetime=1800.0,
    reconnect_timeout=60.0,
    reconnect_failed=_log_pool_reconnect_failed,
    kwargs={
        "autocommit": True,
        "prepare_threshold": 0,
        "row_factory": dict_row,
        "keepalives": 1,
        "keepalives_idle": 30,
        "keepalives_interval": 10,
        "keepalives_count": 5,
        "connect_timeout": 10,
    },
    check=_check_pool_connection,
)

# With min_size=0, wait() only confirms the pool is open (no pre-warm).
pool.wait(timeout=30.0)

_postgres_saver = PostgresSaver(pool)
_postgres_saver.supports_pipeline = False
_postgres_saver.setup()

_postgres_store = PostgresStore(pool)
_postgres_store.supports_pipeline = False
_postgres_store.setup()

graph = builder.compile(checkpointer=_postgres_saver, store=_postgres_store)
graph.name = "signal-pipeline"


def _ensure_pool_healthy() -> None:
    """Discard broken idle connections before a long graph / checkpoint session."""
    try:
        pool.check()
    except Exception:
        import logging

        logging.getLogger(__name__).warning(
            "pool.check() raised; continuing — checkout check will replace bad conns",
            exc_info=True,
        )


def _checkpoint_exists(config) -> bool:
    """True when PostgresSaver already has state for this thread_id."""
    snap = graph.get_state(config)
    if not snap:
        return False
    if snap.values:
        return True
    if snap.next:
        return True
    if snap.tasks:
        return True
    return False


def _pending_interrupt(config) -> bool:
    """True when the thread is paused on an interrupt() (e.g. HITL)."""
    snap = graph.get_state(config)
    for task in getattr(snap, "tasks", ()) or ():
        if getattr(task, "interrupts", None):
            return True
    return False


def _recovery_input(original_input, config):
    """Choose invoke input for a post-OperationalError retry.

    Mid-run failures must NOT replay the original initial_state — that re-runs
    completed nodes and duplicates LLM/research work. LangGraph resumes from the
    last persisted checkpoint with ``invoke(None, config)`` (same contract as
    ``execute_graph(resume=True)`` / scripts/test_hitl.py).

    If the original call was ``Command(resume=...)`` and the interrupt is still
    pending (failure before the resume was applied), re-send that Command.
    Once past the interrupt, recover with ``None``.
    """
    from langgraph.types import Command

    if not _checkpoint_exists(config):
        # Nothing persisted yet — safe to retry the original first-start input.
        return original_input

    if isinstance(original_input, Command) and _pending_interrupt(config):
        return original_input

    return None


def _invoke_with_stale_conn_retry(invoke_input, config):
    """Invoke once; on SSL/pool OperationalError refresh pool and resume checkpoint."""
    tid = str(((config or {}).get("configurable") or {}).get("thread_id") or "")
    try:
        _ensure_pool_healthy()
        try:
            return graph.invoke(invoke_input, config)
        except OperationalError:
            import logging

            recovery_input = _recovery_input(invoke_input, config)
            logging.getLogger(__name__).warning(
                "graph.invoke hit OperationalError (likely stale pooled conn); "
                "refreshing pool and resuming from checkpoint "
                "(recovery_input=%s, not replaying initial_state)",
                type(recovery_input).__name__
                if recovery_input is not None
                else None,
                exc_info=True,
            )
            _ensure_pool_healthy()
            return graph.invoke(recovery_input, config)
    finally:
        if tid:
            clear_live_node(tid)


def _get_state_with_stale_conn_retry(config):
    """Best-effort get_state using the same pool refresh + OperationalError retry as invoke.

    Diagnostics only: returns None instead of raising so callers never fail the request.
    """
    _ensure_pool_healthy()
    try:
        return graph.get_state(config)
    except OperationalError:
        import logging

        logging.getLogger(__name__).warning(
            "graph.get_state hit OperationalError (likely stale pooled conn); "
            "refreshing pool and retrying get_state",
            exc_info=True,
        )
        _ensure_pool_healthy()
        try:
            return graph.get_state(config)
        except Exception:
            return None
    except Exception:
        return None


@dataclass(frozen=True)
class GraphRunResult:
    """Result of a single graph.invoke, including checkpoint metadata for API status."""

    state: dict
    checkpoint_next: tuple[str, ...] = ()


def build_initial_state(
    *,
    run_id: Optional[str] = None,
    user_id: str = "",
    thread_id: str = "",
    run_type: str = "manual",
) -> dict:
    """Canonical SignalState initializer shared by CLI, API, and scheduler."""
    return {
        "run_id": run_id or str(uuid4()),
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
        "user_id": user_id,
        "thread_id": thread_id,
        "run_type": run_type,
        "graph_version": os.getenv("GRAPH_VERSION", "1.0"),
        "hitl_decision": None,
        "hitl_edits": None,
        "delivery_status": None,
        "briefing_draft": "",
        "briefing_final": "",
    }


def execute_graph(
    *,
    user_id: Optional[str] = None,
    run_type: str = "manual",
    thread_id: Optional[str] = None,
    run_id: Optional[str] = None,
    resume: bool = False,
) -> GraphRunResult:
    """Canonical pipeline execution entry point."""
    tid = thread_id or f"run_{uuid4().hex[:12]}"
    config = graph_invoke_config(tid, run_type=run_type, user_id=user_id or "")

    if resume:
        invoke_input = None
    else:
        invoke_input = build_initial_state(
            run_id=run_id,
            user_id=user_id or "",
            thread_id=tid,
            run_type=run_type,
        )

    # Discard idle sockets killed by Supabase/PgBouncer before checkpoint I/O.
    start = time.perf_counter()
    final_state = _invoke_with_stale_conn_retry(invoke_input, config)
    elapsed = time.perf_counter() - start

    # Accumulate graph-compute time across HITL pause/resume segments.
    # run_metrics_writer may have already written with a stale/zero duration;
    # finalize_run_duration patches agent_run_metrics after the outer timer.
    from agent.nodes.run_metrics_writer import finalize_run_duration

    prev = float(final_state.get("run_duration_seconds") or 0.0)
    # On the first segment, state still has 0.0 — use measured elapsed.
    # On resume, checkpoint holds prior segment time; add this segment.
    total_duration = elapsed if prev <= 0.0 else prev + elapsed

    try:
        graph.update_state(config, {"run_duration_seconds": total_duration})
    except Exception:
        pass

    finalize_run_duration(final_state.get("run_id"), total_duration)
    final_state = {**final_state, "run_duration_seconds": total_duration}

    graph_state = graph.get_state(config)
    checkpoint_next = tuple(graph_state.next or ())

    return GraphRunResult(state=final_state, checkpoint_next=checkpoint_next)


def run_graph() -> dict:
    """CLI / scheduler convenience wrapper — returns final state dict only."""
    return execute_graph().state
