"""QA planning node."""

from langchain_core.runnables import RunnableConfig

from agent.nodes.generation import generate_markdown
from agent.orchestrator.state import DeliveryHubState


def qa_node(
    state: DeliveryHubState,
    config: RunnableConfig | None = None,
) -> DeliveryHubState:
    return generate_markdown(
        state=state,
        stage="qa",
        artifact_name="qa-plan.md",
        agent_profile="qa_agent.md",
        context_artifacts=["requirements.md", "architecture.md", "implementation-plan.md"],
        config=config,
        instruction=(
            "Create a QA strategy with test matrix, scenarios, regression scope, and exit criteria."
        ),
    )
