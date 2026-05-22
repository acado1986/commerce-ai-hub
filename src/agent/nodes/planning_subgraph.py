"""Planning subgraph for implementation plan and review checklist."""

from langchain_core.runnables import RunnableConfig
from langgraph.graph import END, START, StateGraph

from agent.nodes.generation import generate_markdown
from agent.orchestrator.state import DeliveryHubState


def implementation_plan_node(
    state: DeliveryHubState,
    config: RunnableConfig | None = None,
) -> DeliveryHubState:
    """Generate implementation-plan.md from architecture context."""
    return generate_markdown(
        state=state,
        stage="planning",
        artifact_name="implementation-plan.md",
        agent_profile="workflow_planner_agent.md",
        context_artifacts=[
            "platform-selection.json",
            "requirements.md",
            "architecture.md",
        ],
        config=config,
        instruction=(
            "Create implementation steps, sequencing, dependency map, and rollback strategy. "
            "Include the selected platform, selected scaffold type, exact setup command, "
            "required skills/tools setup command, expected files/directories after setup, manual "
            "prerequisites, validation commands, and rollback/cleanup steps. Use the solution profile as "
            "authoritative; do not invent scaffold options outside the platform-selection artifact. "
            "For API Mesh add-ons, include the relevant aio api-mesh command sequence."
        ),
    )


def review_checklist_node(
    state: DeliveryHubState,
    config: RunnableConfig | None = None,
) -> DeliveryHubState:
    """Generate review-checklist.md from plan and upstream artifacts."""
    return generate_markdown(
        state=state,
        stage="planning",
        artifact_name="review-checklist.md",
        agent_profile="workflow_planner_agent.md",
        context_artifacts=[
            "requirements.md",
            "architecture.md",
            "implementation-plan.md",
        ],
        config=config,
        instruction=(
            "Create a code/design review checklist with correctness, risk, test, "
            "security, and operational readiness checks."
        ),
    )


_planning_builder = StateGraph(DeliveryHubState)
_planning_builder.add_node("implementation_plan", implementation_plan_node)
_planning_builder.add_node("review_checklist", review_checklist_node)
_planning_builder.add_edge(START, "implementation_plan")
_planning_builder.add_edge("implementation_plan", "review_checklist")
_planning_builder.add_edge("review_checklist", END)

planning_subgraph = _planning_builder.compile(name="AI Delivery Hub Planning Subgraph")
