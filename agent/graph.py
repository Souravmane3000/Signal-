from langgraph.checkpoint.memory import MemorySaver
from langgraph.graph import StateGraph

from agent.state import SignalState

builder = StateGraph(SignalState)

checkpointer = MemorySaver()
graph = builder.compile(checkpointer=checkpointer)
