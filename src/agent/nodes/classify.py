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
from agent.platform_catalog import load_platform_catalog

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
RISK = {"low", "medium", "high"}


def _catalog_platforms() -> list[str]:
    catalog = load_platform_catalog()
    return list(catalog["platforms"].keys())


def _catalog_platform_context() -> tuple[list[str], dict[str, Any]]:
    catalog = load_platform_catalog()
    platform_context: dict[str, Any] = {}
    for platform_id, platform_config in catalog["platforms"].items():
        profile_labels: list[str] = []
        triggers: list[str] = []
        for profile_id in platform_config.get("profile_ids", []):
            profile = catalog["profiles"].get(profile_id, {})
            label = str(profile.get("label", "")).strip()
            if label and label not in profile_labels:
                profile_labels.append(label)
            for trigger in profile.get("triggers", []):
                normalized = str(trigger).strip()
                if normalized and normalized not in triggers:
                    triggers.append(normalized)
        platform_context[platform_id] = {
            "profile_labels": profile_labels,
            "triggers": triggers,
        }
    return list(catalog["platforms"].keys()), platform_context


def _fallback_platform(platforms: list[str]) -> str:
    if "generic" in platforms:
        return "generic"
    if not platforms:
        raise RuntimeError("Platform catalog must define at least one platform.")
    return platforms[0]


def _normalize_platforms(raw_platforms: Any, allowed_platforms: list[str]) -> list[str]:
    if isinstance(raw_platforms, str):
        candidates = [raw_platforms]
    elif isinstance(raw_platforms, list):
        candidates = raw_platforms
    else:
        candidates = []

    allowed = set(allowed_platforms)
    normalized: list[str] = []
    for candidate in candidates:
        platform = str(candidate).strip()
        if platform in allowed and platform not in normalized:
            normalized.append(platform)
    return normalized or [_fallback_platform(allowed_platforms)]


def _state_timeout(state: DeliveryHubState, default: int = 60) -> int:
    raw_timeout = state.get("timeout", default)
    try:
        timeout = int(raw_timeout)
    except (TypeError, ValueError):
        return default
    return timeout if timeout > 0 else default


def _classify_payload(
    text: str,
    timeout: int,
    config: RunnableConfig | None = None,
) -> tuple[dict[str, Any], dict[str, Any]]:
    allowed_platforms, platform_context = _catalog_platform_context()
    deployment = deployment_for_classification()
    model_name = model_name_for_deployment(deployment)
    model = get_model(timeout=timeout, deployment=deployment)
    print("[llm] classify request", flush=True)  # noqa: T201
    prompt = (
        "Classify the request. Return strict JSON only with keys: "
        "request_type, platforms, confidence_score, risk_level, rationale. "
        "Allowed request_type: implementation, architecture, offer, proposal, "
        "bug_investigation, documentation, qa, research. "
        f"Allowed platforms values: {json.dumps(allowed_platforms)}. "
        "Use platform_hints to recognize catalog-specific platform terms.\n"
        f"platform_hints: {json.dumps(platform_context)}\n\n"
        f"Input:\n{text}"
    )
    response = invoke_model(
        model,
        prompt,
        with_stage_trace_config(
            config,
            stage="classify",
            artifact="classification.json",
            model=model_name,
        ),
    )
    return json.loads(response_content(response)), response_usage(
        response,
        requested_model=model_name,
    )


def classify_node(
    state: DeliveryHubState,
    config: RunnableConfig | None = None,
) -> DeliveryHubState:
    """Classify the request and persist normalized classification metadata."""
    errors = list(state.get("errors", []))
    artifacts = dict(state.get("artifact_paths", {}))
    timeout = _state_timeout(state)
    try:
        payload, usage = _classify_payload(state.get("input_text", ""), timeout, config)
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
    platforms = _normalize_platforms(platforms, _catalog_platforms())
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
