"""Approval payload shaping."""

from __future__ import annotations

from typing import Any

from agent.orchestrator.state import DeliveryHubState


def approval_payload(state: DeliveryHubState) -> dict[str, Any]:
    return {
        "run_id": state.get("run_id"),
        "request_type": state.get("request_type"),
        "mapped_request_type": state.get("mapped_request_type"),
        "platforms": state.get("platforms", []),
        "confidence_score": state.get("confidence_score"),
        "risk_level": state.get("risk_level"),
        "artifact_paths": state.get("artifact_paths", {}),
        "errors": state.get("errors", []),
        "approval_stage": state.get("approval_stage") or state.get("current_stage"),
        "allowed_actions": ["approve", "modify", "reject"],
        "next_action": "human_approval_required",
    }
