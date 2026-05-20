"""Human approval gate node."""

from __future__ import annotations

from typing import Any

from langgraph.types import interrupt

from agent.nodes.common import write_json_artifact
from agent.orchestrator.approvals import approval_payload
from agent.orchestrator.audit import append_audit_event
from agent.orchestrator.state import DeliveryHubState


def _decision_action(decision: dict[str, object]) -> str:
    action = str(decision.get("action", "")).strip().lower()
    if action in {"approve", "approved"}:
        return "approve"
    if action in {"reject", "rejected"}:
        return "reject"
    if action == "modify":
        return "modify"
    if "approved" in decision:
        return "approve" if bool(decision.get("approved")) else "reject"
    return "reject"


def pending_approval_state(
    state: DeliveryHubState,
    *,
    payload: dict[str, Any] | None = None,
) -> DeliveryHubState:
    approval_stage = state.get("approval_stage") or state.get("current_stage")
    return {
        **state,
        "current_stage": "approval",
        "approval_status": "pending",
        "next_action": "awaiting_approval",
        "approval_stage": approval_stage,
        "approval_request": payload or approval_payload(state),
        "approval_decision": None,
    }


def apply_approval_decision(
    state: DeliveryHubState,
    decision_obj: dict[str, object],
    *,
    payload: dict[str, Any] | None = None,
) -> DeliveryHubState:
    payload = payload or approval_payload(state)
    action = _decision_action(decision_obj)

    approval_stage = state.get("approval_stage") or state.get("current_stage")
    reviewer_note = str(decision_obj.get("reviewer_note", "")).strip()

    if action == "modify":
        instruction = str(decision_obj.get("instruction", "")).strip()
        return {
            **state,
            "current_stage": "approval",
            "approval_status": "pending",
            "next_action": "revise",
            "revision_stage": approval_stage,
            "revision_instruction": instruction,
            "approval_request": None,
            "approval_decision": None,
            "audit_log": append_audit_event(
                state,
                "approval",
                "modify_requested",
                {
                    "approval_stage": approval_stage,
                    "instruction": instruction,
                    "decision": decision_obj,
                },
            ),
        }

    approved = action == "approve"
    status = "approved" if approved else "rejected"
    artifact_paths = dict(state.get("artifact_paths", {}))
    approved_files = sorted(artifact_paths) if approved else []
    approval_record = {
        "run_id": state.get("run_id"),
        "approval_stage": approval_stage,
        "approval_status": status,
        "approved_files": approved_files,
        "reviewer_note": reviewer_note,
    }
    artifact_paths.update(write_json_artifact(state, "approval.json", approval_record))
    return {
        **state,
        "current_stage": "approval",
        "approval_status": status,
        "next_action": "approved" if approved else "rejected",
        "artifact_paths": artifact_paths,
        "revision_stage": None,
        "revision_instruction": None,
        "approval_request": None,
        "approval_decision": None,
        "audit_log": append_audit_event(
            state,
            "approval",
            status,
            {
                "payload": payload,
                "decision": decision_obj,
                "approval_stage": approval_stage,
                "approved_files": approved_files,
            },
        ),
    }


def approval_node(state: DeliveryHubState) -> DeliveryHubState:
    """Collect user decision: approve to continue, modify to rerun stage, reject to stop."""
    payload = approval_payload(state)
    decision = interrupt(payload)
    decision_obj = decision if isinstance(decision, dict) else {}
    return apply_approval_decision(state, decision_obj, payload=payload)
