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
        context_artifacts=["platform-selection.json", "requirements.md"],
        config=config,
        instruction=(
            "Produce an architecture artifact with system context, component design, "
            "integration points, risk notes, and Adobe Commerce/App Builder considerations. "
            "Use the solution profile as the authoritative allowed scaffold/setup selection. "
            "Identify the platform, selected scaffold type, exact setup command, required "
            "skills/tools setup command, source documents, and validation commands. Explain why this "
            "scaffold is correct and reject unsuitable scaffold options with concise reasons. "
            "If API Mesh is selected as an add-on, include its aio command family and where "
            "it fits in the architecture."
        ),
    )
