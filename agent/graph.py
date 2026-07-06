"""LangGraph StateGraph — wired in Session 10."""

from __future__ import annotations

from langgraph.graph import END, StateGraph

from agent.nodes.config_loader import config_loader
from agent.state import SignalState


def build_graph() -> StateGraph:
    """Build and return the Signal agent graph (nodes wired in Session 10)."""
    graph = StateGraph(SignalState)

    graph.add_node("config_loader", config_loader)

    # TODO Session 10: wire remaining nodes and edges
    # graph.add_node("search_planner", search_planner)
    # ...

    graph.set_entry_point("config_loader")
    graph.add_edge("config_loader", END)

    return graph


def compile_graph():
    """Compile the graph for execution."""
    return build_graph().compile()
