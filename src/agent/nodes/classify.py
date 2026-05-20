"""Classification node."""

import json
from typing import Any

from langchain_core.runnables import RunnableConfig

from agent.llm import (
    deployment_for_classification,
    get_model,
    invoke_model,
    model_name_for_deployment,
    response_content,
    response_usage,
)
from agent.nodes.common import write_json_artifact
from agent.observability import with_stage_trace_config
from agent.orchestrator.audit import append_audit_event, append_llm_usage
from agent.orchestrator.policies import confidence_requires_review
from agent.orchestrator.router import mapped_request_type
from agent.orchestrator.state import DeliveryHubState

REQUEST_TYPES = {
    "implementation",
    "architecture",
    "offer",
    "proposal",
    "bug_investigation",
    "documentation",
    "qa",
    "research",
}
PLATFORMS = {"adobe_commerce", "app_builder", "generic"}
RISK = {"low", "medium", "high"}


def _classify_payload(
    text: str,
    config: RunnableConfig | None = None,
) -> tuple[dict[str, Any], dict[str, Any]]:
    deployment = deployment_for_classification()
    model_name = model_name_for_deployment(deployment)
    model = get_model(deployment=deployment)
    print("[llm] classify request", flush=True)
    prompt = (
        "Classify the request. Return strict JSON only with keys: "
        "request_type, platforms, confidence_score, risk_level, rationale. "
        "Allowed request_type: implementation, architecture, offer, proposal, "
        "bug_investigation, documentation, qa, research. "
        "Allowed platforms values: adobe_commerce, app_builder, generic.\n\n"
        f"Input:\n{text}"
    )
    response = invoke_model(
        model,
        prompt,
        with_stage_trace_config(config, stage="classify", artifact="classification.json", model=model_name),
    )
    return json.loads(response_content(response)), response_usage(response, requested_model=model_name)


def classify_node(
    state: DeliveryHubState,
    config: RunnableConfig | None = None,
) -> DeliveryHubState:
    errors = list(state.get("errors", []))
    artifacts = dict(state.get("artifact_paths", {}))
    try:
        payload, usage = _classify_payload(state.get("input_text", ""), config)
    except Exception as exc:  # noqa: BLE001
        errors.append({"stage": "classify", "error": str(exc)})
        return {
            **state,
            "current_stage": "classify",
            "approval_status": "blocked",
            "next_action": "human_review",
            "errors": errors,
            "audit_log": append_audit_event(state, "classify", "failed", {"error": str(exc)}),
        }

    request_type = str(payload.get("request_type", "implementation"))
    platforms = payload.get("platforms", ["generic"])
    confidence = float(payload.get("confidence_score", 0.0))
    risk_level = str(payload.get("risk_level", "medium"))
    rationale = str(payload.get("rationale", ""))
    if request_type not in REQUEST_TYPES:
        request_type = "implementation"
    platforms = [p for p in platforms if p in PLATFORMS] or ["generic"]
    if risk_level not in RISK:
        risk_level = "medium"
    mapped = mapped_request_type({"request_type": request_type})
    next_action = "human_review" if confidence_requires_review(confidence) else "continue"
    classification = {
        "request_type": request_type,
        "mapped_request_type": mapped,
        "platforms": platforms,
        "confidence_score": confidence,
        "risk_level": risk_level,
        "rationale": rationale,
    }
    llm_usage = append_llm_usage(state, "classify", "classification.json", usage)
    artifacts.update(write_json_artifact(state, "classification.json", classification))
    return {
        **state,
        "request_type": request_type,
        "mapped_request_type": mapped,
        "platforms": platforms,
        "confidence_score": confidence,
        "risk_level": risk_level,
        "classification_rationale": rationale,
        "current_stage": "classify",
        "next_action": next_action,
        "artifact_paths": artifacts,
        "errors": errors,
        "llm_usage": llm_usage,
        "audit_log": append_audit_event(
            state,
            "classify",
            "completed",
            {**classification, "llm_usage": usage},
        ),
    }
