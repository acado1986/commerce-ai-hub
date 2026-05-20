"""Implementation planning node."""

from langchain_core.runnables import RunnableConfig

from agent.nodes.generation import generate_markdown
from agent.orchestrator.state import DeliveryHubState


def planning_node(
    state: DeliveryHubState,
    config: RunnableConfig | None = None,
) -> DeliveryHubState:
    state = generate_markdown(
        state=state,
        stage="planning",
        artifact_name="implementation-plan.md",
        agent_profile="workflow_planner_agent.md",
        context_artifacts=["requirements.md", "architecture.md"],
        config=config,
        instruction=(
            "Create implementation steps, sequencing, dependency map, and rollback strategy."
        ),
    )
    return generate_markdown(
        state=state,
        stage="planning",
        artifact_name="review-checklist.md",
        agent_profile="workflow_planner_agent.md",
        context_artifacts=["requirements.md", "architecture.md", "implementation-plan.md"],
        config=config,
        instruction=(
            "Create a code/design review checklist with correctness, risk, test, "
            "security, and operational readiness checks."
        ),
    )
