"""Workflow routing helpers."""

from __future__ import annotations

from agent.orchestrator.state import DeliveryHubState

ROUTE_MAP = {
    "implementation": "implementation",
    "bug_investigation": "implementation",
    "qa": "implementation",
    "research": "implementation",
    "architecture": "architecture",
    "documentation": "documentation",
    "offer": "offer",
    "proposal": "offer",
}


def mapped_request_type(state: DeliveryHubState) -> str:
    request_type = state.get("request_type", "implementation")
    return ROUTE_MAP.get(request_type, "implementation")


def route_after_classification(state: DeliveryHubState) -> str:
    return (
        "approval"
        if state.get("next_action") == "human_review"
        else "platform_selection"
    )


def route_after_platform_selection(state: DeliveryHubState) -> str:
    return "approval" if state.get("next_action") == "human_review" else "requirements"


def route_after_requirements(state: DeliveryHubState) -> str:
    return "approval" if state.get("next_action") == "human_review" else "architecture"


def route_after_architecture(state: DeliveryHubState) -> str:
    return "approval" if state.get("next_action") == "human_review" else "planning"


def route_after_planning(state: DeliveryHubState) -> str:
    return "approval" if state.get("next_action") == "human_review" else "qa"


def route_after_qa(state: DeliveryHubState) -> str:
    return "approval" if state.get("next_action") == "human_review" else "documentation"


def route_after_documentation(state: DeliveryHubState) -> str:
    return "approval" if state.get("next_action") == "human_review" else "audit"


def route_after_approval(state: DeliveryHubState) -> str:
    if state.get("approval_status") == "rejected":
        return "end"
    if state.get("next_action") == "revise":
        return state.get("revision_stage") or "end"

    stage = state.get("approval_stage")
    if stage == "audit":
        return "end"
    if stage == "classify":
        return "platform_selection"
    if stage == "platform_selection":
        return "requirements"
    if stage == "requirements":
        return "architecture"
    if stage == "architecture":
        return "planning"
    if stage == "planning":
        return "qa"
    if stage == "qa":
        return "documentation"
    if stage == "documentation":
        return "audit"
    return "end"
