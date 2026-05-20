"""Controlled LangGraph ToolNode subgraphs."""

from __future__ import annotations

from langgraph.graph import END, START, MessagesState, StateGraph
from langgraph.prebuilt import ToolNode

from agent.tools.artifacts import ARTIFACT_TOOLS

artifact_tool_builder = StateGraph(MessagesState)
artifact_tool_builder.add_node("artifact_tools", ToolNode(ARTIFACT_TOOLS))
artifact_tool_builder.add_edge(START, "artifact_tools")
artifact_tool_builder.add_edge("artifact_tools", END)

artifact_tool_graph = artifact_tool_builder.compile(name="Artifact Tool Graph")
