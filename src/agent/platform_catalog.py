"""Config-driven platform setup selection with LLM-assisted constrained choice."""

from __future__ import annotations

import json
import os
from functools import lru_cache
from pathlib import Path
from typing import Any

import yaml

from agent.llm import (
    deployment_for_classification,
    get_model,
    invoke_model,
    response_content,
)
from agent.orchestrator.state import DeliveryHubState


def _repo_root() -> Path:
    return Path(__file__).resolve().parents[2]


def _catalog_path() -> Path:
    configured = os.getenv("PLATFORM_CATALOG_PATH", "").strip()
    if configured:
        return Path(configured)
    return _repo_root() / "config" / "platform_catalog.yaml"


@lru_cache(maxsize=1)
def load_platform_catalog() -> dict[str, Any]:
    """Load and validate the platform catalog."""
    path = _catalog_path()
    if not path.exists():
        raise RuntimeError(f"Platform catalog not found: {path}")
    raw = yaml.safe_load(path.read_text(encoding="utf-8"))
    if not isinstance(raw, dict):
        raise RuntimeError("Platform catalog root must be a mapping.")

    platforms = raw.get("platforms")
    profiles = raw.get("profiles")
    capabilities = raw.get("capabilities")
    if (
        not isinstance(platforms, dict)
        or not isinstance(profiles, dict)
        or not isinstance(capabilities, dict)
    ):
        raise RuntimeError(
            "Platform catalog requires mapping keys: platforms, profiles, capabilities."
        )

    for platform_key, platform_config in platforms.items():
        if not isinstance(platform_config, dict):
            raise RuntimeError(f"platforms.{platform_key} must be a mapping")
        profile_ids = platform_config.get("profile_ids")
        default_profile_id = platform_config.get("default_profile_id")
        if not isinstance(profile_ids, list) or not all(
            isinstance(item, str) for item in profile_ids
        ):
            raise RuntimeError(
                f"platforms.{platform_key}.profile_ids must be a string list"
            )
        if not isinstance(default_profile_id, str):
            raise RuntimeError(
                f"platforms.{platform_key}.default_profile_id must be a string"
            )
        if default_profile_id not in profile_ids:
            raise RuntimeError(
                f"platforms.{platform_key}.default_profile_id must be included in profile_ids"
            )
        for profile_id in profile_ids:
            if profile_id not in profiles:
                raise RuntimeError(
                    f"Unknown profile id '{profile_id}' in platforms.{platform_key}"
                )

    for profile_id, profile in profiles.items():
        if not isinstance(profile, dict):
            raise RuntimeError(f"profiles.{profile_id} must be a mapping")
        required_keys = [
            "label",
            "platform",
            "requires_specialized_skills",
            "skills",
            "project_commands",
            "triggers",
            "source_documents",
            "architecture_notes",
        ]
        for key in required_keys:
            if key not in profile:
                raise RuntimeError(
                    f"profiles.{profile_id} missing required key '{key}'"
                )

    for capability_id, capability in capabilities.items():
        if not isinstance(capability, dict):
            raise RuntimeError(f"capabilities.{capability_id} must be a mapping")
        required_keys = [
            "label",
            "applicable_platforms",
            "triggers",
            "commands",
            "skills",
            "source_documents",
            "architecture_notes",
        ]
        for key in required_keys:
            if key not in capability:
                raise RuntimeError(
                    f"capabilities.{capability_id} missing required key '{key}'"
                )

    return raw


def select_solution_profile(state: DeliveryHubState) -> dict[str, Any]:
    """Select a setup profile from catalog; prefer LLM constrained selection with safe fallback."""
    catalog = load_platform_catalog()
    text = str(state.get("input_text", "")).strip()
    platforms = _normalized_platforms(state, catalog)

    fallback = _deterministic_selection(text=text, platforms=platforms, catalog=catalog)
    llm_enabled = os.getenv("PLATFORM_SELECTION_USE_LLM", "true").lower() == "true"
    if not llm_enabled:
        return {**fallback, "selection_method": "deterministic"}

    llm_choice = _llm_constrained_selection(
        text=text,
        platforms=platforms,
        catalog=catalog,
        timeout=_state_timeout(state),
    )
    if not llm_choice:
        return {**fallback, "selection_method": "deterministic_fallback"}

    profile_id = llm_choice["profile_id"]
    add_on_ids = llm_choice.get("add_on_ids", [])
    selected = _build_solution_profile(
        catalog=catalog,
        profile_id=profile_id,
        add_on_ids=add_on_ids,
        reason=llm_choice.get("reason", ""),
        confidence=llm_choice.get(
            "confidence_score", fallback.get("confidence_score", 0.65)
        ),
    )
    selected["selection_method"] = "llm"
    return selected


def _normalized_platforms(
    state: DeliveryHubState, catalog: dict[str, Any]
) -> list[str]:
    available = set(catalog["platforms"].keys())
    input_platforms = [
        str(item).strip() for item in state.get("platforms", []) if str(item).strip()
    ]
    normalized = [item for item in input_platforms if item in available]
    return normalized or ["generic"]


def _state_timeout(state: DeliveryHubState, default: int = 60) -> int:
    raw_timeout = state.get("timeout", default)
    try:
        timeout = int(raw_timeout)
    except (TypeError, ValueError):
        return default
    return timeout if timeout > 0 else default


def _candidate_profiles(platforms: list[str], catalog: dict[str, Any]) -> list[str]:
    profile_ids: list[str] = []
    for platform in platforms:
        config = catalog["platforms"].get(platform, {})
        for profile_id in config.get("profile_ids", []):
            if profile_id not in profile_ids:
                profile_ids.append(profile_id)
    if not profile_ids:
        generic_default = catalog["platforms"]["generic"]["default_profile_id"]
        profile_ids = [generic_default]
    return profile_ids


def _candidate_add_ons(platforms: list[str], catalog: dict[str, Any]) -> list[str]:
    add_on_ids: list[str] = []
    for capability_id, capability in catalog["capabilities"].items():
        applicable = set(capability.get("applicable_platforms", []))
        if applicable.intersection(platforms):
            add_on_ids.append(capability_id)
    return add_on_ids


def _llm_constrained_selection(
    text: str,
    platforms: list[str],
    catalog: dict[str, Any],
    timeout: int,
) -> dict[str, Any] | None:
    candidate_profiles = _candidate_profiles(platforms, catalog)
    candidate_add_ons = _candidate_add_ons(platforms, catalog)
    if not text.strip():
        return None

    profile_hints = {
        pid: {
            "label": catalog["profiles"][pid].get("label"),
            "platform": catalog["profiles"][pid].get("platform"),
            "triggers": catalog["profiles"][pid].get("triggers", []),
        }
        for pid in candidate_profiles
    }
    add_on_hints = {
        aid: {
            "label": catalog["capabilities"][aid].get("label"),
            "triggers": catalog["capabilities"][aid].get("triggers", []),
        }
        for aid in candidate_add_ons
    }

    prompt = (
        "You are selecting a platform setup profile for implementation planning.\n"
        "Return strict JSON only with keys: profile_id, add_on_ids, confidence_score, reason.\n"
        "Rules:\n"
        "- profile_id must be exactly one of candidate_profile_ids.\n"
        "- add_on_ids must contain only values from candidate_add_on_ids.\n"
        "- confidence_score must be a number from 0 to 1.\n"
        "- reason must be concise and concrete.\n\n"
        f"classified_platforms: {json.dumps(platforms)}\n"
        f"candidate_profile_ids: {json.dumps(candidate_profiles)}\n"
        f"candidate_profile_hints: {json.dumps(profile_hints)}\n"
        f"candidate_add_on_ids: {json.dumps(candidate_add_ons)}\n"
        f"candidate_add_on_hints: {json.dumps(add_on_hints)}\n\n"
        f"request_text:\n{text}\n"
    )

    try:
        deployment = deployment_for_classification()
        model = get_model(timeout=timeout, deployment=deployment)
        response = invoke_model(model, prompt)
        payload = json.loads(response_content(response))
    except Exception:
        return None

    if not isinstance(payload, dict):
        return None

    profile_id = payload.get("profile_id")
    if profile_id not in candidate_profiles:
        return None

    raw_add_on_ids = payload.get("add_on_ids", [])
    if not isinstance(raw_add_on_ids, list):
        raw_add_on_ids = []
    add_on_ids = [
        item
        for item in raw_add_on_ids
        if isinstance(item, str) and item in candidate_add_ons
    ]

    try:
        confidence = float(payload.get("confidence_score", 0.0))
    except (TypeError, ValueError):
        confidence = 0.0
    confidence = max(0.0, min(1.0, confidence))

    reason = str(payload.get("reason", "")).strip()
    return {
        "profile_id": profile_id,
        "add_on_ids": add_on_ids,
        "confidence_score": confidence,
        "reason": reason,
    }


def _deterministic_selection(
    text: str,
    platforms: list[str],
    catalog: dict[str, Any],
) -> dict[str, Any]:
    lower_text = text.lower()
    candidate_profiles = _candidate_profiles(platforms, catalog)

    best_profile_id = candidate_profiles[0]
    best_score = -1
    for profile_id in candidate_profiles:
        profile = catalog["profiles"][profile_id]
        triggers = profile.get("triggers", [])
        score = sum(
            1
            for trigger in triggers
            if isinstance(trigger, str) and trigger.lower() in lower_text
        )
        if score > best_score:
            best_score = score
            best_profile_id = profile_id

    if best_score <= 0:
        best_profile_id = catalog["platforms"][platforms[0]].get(
            "default_profile_id", best_profile_id
        )

    add_on_ids = _deterministic_add_ons(lower_text, platforms, catalog)
    confidence = 0.88 if best_score > 0 else 0.68
    if best_profile_id in {"adobe_commerce_module", "generic_project"}:
        confidence = 0.8 if best_profile_id == "adobe_commerce_module" else 0.55

    return _build_solution_profile(
        catalog=catalog,
        profile_id=best_profile_id,
        add_on_ids=add_on_ids,
        reason=_default_reason(best_profile_id, best_score),
        confidence=confidence,
    )


def _deterministic_add_ons(
    lower_text: str,
    platforms: list[str],
    catalog: dict[str, Any],
) -> list[str]:
    selected: list[str] = []
    for capability_id in _candidate_add_ons(platforms, catalog):
        capability = catalog["capabilities"][capability_id]
        triggers = capability.get("triggers", [])
        if any(
            isinstance(trigger, str) and trigger.lower() in lower_text
            for trigger in triggers
        ):
            selected.append(capability_id)
    return selected


def _build_solution_profile(
    catalog: dict[str, Any],
    profile_id: str,
    add_on_ids: list[str],
    reason: str,
    confidence: float,
) -> dict[str, Any]:
    profile = catalog["profiles"][profile_id]
    add_ons = [
        _format_add_on(catalog["capabilities"][add_on_id], add_on_id)
        for add_on_id in add_on_ids
    ]

    skills = list(profile.get("skills", []))
    for add_on in add_ons:
        for skill in add_on.get("skills", []):
            if skill not in skills:
                skills.append(skill)

    requires_specialized_skills = bool(
        profile.get("requires_specialized_skills", False) or add_ons
    )

    return {
        "catalog_version": catalog.get("version"),
        "platform": profile.get("platform", "generic"),
        "scaffold_type": profile_id,
        "scaffold_label": profile.get("label", profile_id),
        "setup_command": profile.get("setup_command"),
        "skills_setup_command": profile.get("skills_setup_command"),
        "project_commands": list(profile.get("project_commands", [])),
        "requires_specialized_skills": requires_specialized_skills,
        "skills": skills,
        "add_ons": add_ons,
        "reason": reason.strip() or "Selection derived from catalog rules.",
        "source_documents": list(profile.get("source_documents", [])),
        "architecture_notes": list(profile.get("architecture_notes", [])),
        "confidence_score": max(0.0, min(1.0, float(confidence))),
    }


def _format_add_on(capability: dict[str, Any], capability_id: str) -> dict[str, Any]:
    return {
        "capability": capability_id,
        "label": capability.get("label", capability_id),
        "commands": list(capability.get("commands", [])),
        "skills": list(capability.get("skills", [])),
        "source_documents": list(capability.get("source_documents", [])),
        "architecture_notes": list(capability.get("architecture_notes", [])),
    }


def _default_reason(profile_id: str, score: int) -> str:
    if profile_id == "integration_kit":
        return "The request mentions integration/runtime/event/API behavior requiring Commerce extensibility scaffolding."
    if profile_id == "aem_boilerplate":
        return "The request mentions AEM, Edge Delivery, or boilerplate frontend requirements."
    if profile_id == "generic_app_builder":
        return "The request asks for a generic App Builder project instead of Commerce extensibility scaffolding."
    if profile_id == "sdk_admin_ui":
        return "The request is focused on SDK/Admin UI and does not require a special scaffold."
    if profile_id == "adobe_commerce_module":
        return "The classifier identified Adobe Commerce without App Builder scaffold requirements."
    if profile_id == "generic_project":
        return "No supported platform-specific signals were found; generic profile selected."
    if score <= 0:
        return "No stronger profile signal found, defaulting to the platform default profile."
    return "The request matches profile trigger signals in the platform catalog."
