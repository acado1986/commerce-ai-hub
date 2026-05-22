"""Deterministic platform and scaffold selection node."""

from __future__ import annotations

from agent.nodes.common import write_json_artifact
from agent.orchestrator.audit import append_audit_event
from agent.orchestrator.state import DeliveryHubState
from agent.platform_catalog import select_solution_profile


def platform_selection_node(state: DeliveryHubState) -> DeliveryHubState:
    """Persist deterministic platform/scaffold selection before generation stages."""
    artifacts = dict(state.get("artifact_paths", {}))
    profile = select_solution_profile(state)
    payload = {
        "platforms": state.get("platforms", []),
        "solution_profile": profile,
    }
    artifacts.update(write_json_artifact(state, "platform-selection.json", payload))
    next_action = (
        "human_review" if profile.get("confidence_score", 0) < 0.65 else "continue"
    )
    return {
        **state,
        "solution_profile": profile,
        "current_stage": "platform_selection",
        "approval_stage": "platform_selection",
        "next_action": next_action,
        "artifact_paths": artifacts,
        "audit_log": append_audit_event(
            state,
            "platform_selection",
            "completed",
            {
                "platform": profile.get("platform"),
                "scaffold_type": profile.get("scaffold_type"),
                "setup_command": profile.get("setup_command"),
                "skills_setup_command": profile.get("skills_setup_command"),
                "skills": profile.get("skills", []),
                "confidence_score": profile.get("confidence_score"),
            },
        ),
    }
