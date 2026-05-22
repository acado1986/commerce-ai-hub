"""Delivery hub graph definition."""

from __future__ import annotations

from collections.abc import Callable

from langgraph.graph import END, START, StateGraph

from agent.nodes.approval import approval_node
from agent.nodes.approval_router import approval_router_node
from agent.nodes.architecture import architecture_node
from agent.nodes.audit import audit_node
from agent.nodes.classify import classify_node
from agent.nodes.documentation import documentation_node
from agent.nodes.intake import intake_node
from agent.nodes.planning import planning_node
from agent.nodes.platform_selection import platform_selection_node
from agent.nodes.qa import qa_node
from agent.nodes.requirements import requirements_node
from agent.observability import traced_graph
from agent.orchestrator.checkpoints import get_checkpointer
from agent.orchestrator.router import (
    route_after_approval,
    route_after_architecture,
    route_after_classification,
    route_after_documentation,
    route_after_planning,
    route_after_platform_selection,
    route_after_qa,
    route_after_requirements,
)
from agent.orchestrator.state import DeliveryHubState

WorkflowRoute = Callable[[DeliveryHubState], str]


def build_workflow_builder(
    *,
    approval_action: Callable[[DeliveryHubState], DeliveryHubState] = approval_node,
    entry_route: WorkflowRoute | None = None,
    after_approval_route: WorkflowRoute = route_after_approval,
) -> StateGraph:
    builder = StateGraph(DeliveryHubState)
    builder.add_node("intake", intake_node)
    builder.add_node("classify", classify_node)
    builder.add_node("platform_selection", platform_selection_node)
    builder.add_node("requirements", requirements_node)
    builder.add_node("architecture", architecture_node)
    builder.add_node("planning", planning_node)
    builder.add_node("qa", qa_node)
    builder.add_node("documentation", documentation_node)
    builder.add_node("audit", audit_node)
    builder.add_node("approval", approval_action)
    builder.add_node("approval_router", approval_router_node)

    if entry_route is None:
        builder.add_edge(START, "intake")
    else:
        builder.add_conditional_edges(
            START,
            entry_route,
            {"intake": "intake", "approval": "approval"},
        )

    builder.add_edge("intake", "classify")
    builder.add_conditional_edges(
        "classify",
        route_after_classification,
        {"platform_selection": "platform_selection", "approval": "approval"},
    )
    builder.add_conditional_edges(
        "platform_selection",
        route_after_platform_selection,
        {"requirements": "requirements", "approval": "approval"},
    )
    builder.add_conditional_edges(
        "requirements",
        route_after_requirements,
        {"architecture": "architecture", "approval": "approval"},
    )
    builder.add_conditional_edges(
        "architecture",
        route_after_architecture,
        {"planning": "planning", "approval": "approval"},
    )
    builder.add_conditional_edges(
        "planning",
        route_after_planning,
        {"qa": "qa", "approval": "approval"},
    )
    builder.add_conditional_edges(
        "qa",
        route_after_qa,
        {"documentation": "documentation", "approval": "approval"},
    )
    builder.add_conditional_edges(
        "documentation",
        route_after_documentation,
        {"audit": "audit", "approval": "approval"},
    )
    builder.add_edge("audit", END)
    builder.add_edge("approval", "approval_router")
    builder.add_conditional_edges(
        "approval_router",
        after_approval_route,
        {
            "requirements": "requirements",
            "platform_selection": "platform_selection",
            "architecture": "architecture",
            "planning": "planning",
            "qa": "qa",
            "documentation": "documentation",
            "audit": "audit",
            "end": END,
        },
    )
    return builder


builder = build_workflow_builder()


graph = traced_graph(
    builder.compile(name="AI Delivery Hub Workflow (Graph)"),
    trace_name="ai-delivery-hub-studio",
)
cli_graph = builder.compile(
    name="AI Delivery Hub Workflow CLI",
    checkpointer=get_checkpointer(),
)
