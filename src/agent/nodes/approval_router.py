"""Approval routing node."""

from __future__ import annotations

from agent.orchestrator.state import DeliveryHubState


def approval_router_node(state: DeliveryHubState) -> DeliveryHubState:
    """Pass state through so graph routing can branch after approval decisions."""
    return {
        **state,
        "current_stage": "approval_router",
    }
