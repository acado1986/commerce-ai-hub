"""Requirements generation node."""

from langchain_core.runnables import RunnableConfig

from agent.nodes.generation import generate_markdown
from agent.orchestrator.state import DeliveryHubState


def requirements_node(
    state: DeliveryHubState,
    config: RunnableConfig | None = None,
) -> DeliveryHubState:
    return generate_markdown(
        state=state,
        stage="requirements",
        artifact_name="requirements.md",
        agent_profile="business_analyst_agent.md",
        config=config,
        instruction=(
            "Create clear functional and non-functional requirements, assumptions, "
            "constraints, and acceptance criteria for this request."
        ),
    )
