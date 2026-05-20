"""Architecture generation node."""

from langchain_core.runnables import RunnableConfig

from agent.nodes.generation import generate_markdown
from agent.orchestrator.state import DeliveryHubState


def architecture_node(
    state: DeliveryHubState,
    config: RunnableConfig | None = None,
) -> DeliveryHubState:
    return generate_markdown(
        state=state,
        stage="architecture",
        artifact_name="architecture.md",
        agent_profile="solution_architect_agent.md",
        context_artifacts=["requirements.md"],
        config=config,
        instruction=(
            "Produce an architecture artifact with system context, component design, "
            "integration points, risk notes, and Adobe Commerce/App Builder considerations."
        ),
    )
