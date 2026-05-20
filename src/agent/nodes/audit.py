"""Audit persist node."""

from __future__ import annotations

from agent.nodes.common import write_json_artifact
from agent.orchestrator.audit import append_audit_event, summarize_llm_usage
from agent.orchestrator.state import DeliveryHubState


def audit_node(state: DeliveryHubState) -> DeliveryHubState:
    audit_log = append_audit_event(state, "audit", "completed", {"artifact": "audit.json"})
    llm_usage = state.get("llm_usage", [])
    llm_usage_totals = summarize_llm_usage(llm_usage)
    payload = {
        "run_id": state.get("run_id"),
        "request_type": state.get("request_type"),
        "mapped_request_type": state.get("mapped_request_type"),
        "platforms": state.get("platforms", []),
        "confidence_score": state.get("confidence_score"),
        "risk_level": state.get("risk_level"),
        "approval_status": state.get("approval_status", "pending"),
        "events": audit_log,
        "llm_usage": llm_usage,
        "llm_usage_totals": llm_usage_totals,
        "errors": state.get("errors", []),
    }
    artifacts = dict(state.get("artifact_paths", {}))
    artifacts.update(write_json_artifact(state, "audit.json", payload))
    return {
        **state,
        "current_stage": "audit",
        "approval_stage": "audit",
        "approval_status": "pending",
        "next_action": "human_review",
        "artifact_paths": artifacts,
        "audit_log": audit_log,
        "llm_usage_totals": llm_usage_totals,
    }
