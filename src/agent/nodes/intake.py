"""Intake node."""

from __future__ import annotations

import uuid

from agent.nodes.common import write_json_artifact, write_text_artifact
from agent.orchestrator.audit import append_audit_event
from agent.orchestrator.state import DeliveryHubState


def intake_node(state: DeliveryHubState) -> DeliveryHubState:
    run_id = state.get("run_id") or str(uuid.uuid4())
    source_type = state.get("source_type", "manual")
    source_id = state.get("source_id")
    input_text = state.get("input_text", "").strip()
    artifacts = dict(state.get("artifact_paths", {}))
    artifacts.update(write_text_artifact({"run_id": run_id}, "input.md", input_text))
    intake_payload = {
        "run_id": run_id,
        "source_type": source_type,
        "source_id": source_id,
        "input_length": len(input_text),
    }
    artifacts.update(write_json_artifact({"run_id": run_id}, "intake.json", intake_payload))
    new_state: DeliveryHubState = {
        **state,
        "run_id": run_id,
        "source_type": source_type,
        "source_id": source_id,
        "input_text": input_text,
        "current_stage": "intake",
        "artifact_paths": artifacts,
        "errors": list(state.get("errors", [])),
        "audit_log": append_audit_event(state, "intake", "completed", intake_payload),
    }
    return new_state
