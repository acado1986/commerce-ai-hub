"""Chat-safe approval node that pauses via state instead of interrupts."""

from __future__ import annotations

from agent.nodes.approval import apply_approval_decision, pending_approval_state
from agent.orchestrator.state import DeliveryHubState


def chat_approval_node(state: DeliveryHubState) -> DeliveryHubState:
    decision = state.get("approval_decision")
    if not isinstance(decision, dict):
        return pending_approval_state(state)
    return apply_approval_decision(state, decision)
