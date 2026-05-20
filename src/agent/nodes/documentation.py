"""Documentation summary node."""

from langchain_core.runnables import RunnableConfig

from agent.nodes.generation import generate_markdown
from agent.orchestrator.state import DeliveryHubState


def documentation_node(
    state: DeliveryHubState,
    config: RunnableConfig | None = None,
) -> DeliveryHubState:
    return generate_markdown(
        state=state,
        stage="documentation",
        artifact_name="ticket-comment.md",
        agent_profile="documentation_agent.md",
        context_artifacts=[
            "requirements.md",
            "architecture.md",
            "implementation-plan.md",
            "qa-plan.md",
            "review-checklist.md",
        ],
        config=config,
        instruction=(
            "Create a concise ticket update summarizing scope, artifacts produced, risks, "
            "and pending human approvals."
        ),
    )
