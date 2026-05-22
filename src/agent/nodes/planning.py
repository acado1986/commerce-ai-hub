"""Implementation planning node."""

from langchain_core.runnables import RunnableConfig

from agent.nodes.planning_subgraph import planning_subgraph
from agent.orchestrator.state import DeliveryHubState


def planning_node(
    state: DeliveryHubState,
    config: RunnableConfig | None = None,
) -> DeliveryHubState:
    return planning_subgraph.invoke(state, config=config)
