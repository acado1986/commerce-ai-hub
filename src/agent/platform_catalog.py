"""Deterministic platform setup selection catalog."""

from __future__ import annotations

from typing import Any

from agent.orchestrator.state import DeliveryHubState

APP_BUILDER_SETUP_COMMAND = "aio commerce extensibility app-setup"
COMMERCE_AI_TOOLS_SETUP_COMMAND = "aio commerce extensibility tools-setup"
APP_BUILDER_PROJECT_COMMANDS = [
    "aio app init",
    "aio app dev",
    "aio app deploy",
]
API_MESH_COMMANDS = [
    "aio api-mesh:init",
    "aio api-mesh:create",
    "aio api-mesh:update",
    "aio api-mesh:get",
    "aio api-mesh:delete",
]

APP_BUILDER_PROFILES: dict[str, dict[str, Any]] = {
    "integration_kit": {
        "label": "Integration Kit",
        "platform": "app_builder",
        "setup_command": APP_BUILDER_SETUP_COMMAND,
        "skills_setup_command": COMMERCE_AI_TOOLS_SETUP_COMMAND,
        "requires_specialized_skills": True,
        "skills": ["app-builder-integration-kit"],
        "triggers": [
            "integration",
            "integration kit",
            "integrate",
            "external system",
            "sync",
            "runtime action",
            "runtime actions",
            "event",
            "events",
            "webhook",
            "webhooks",
            "commerce extensibility",
            "commerce integration",
            "ims",
            "oauth",
        ],
        "architecture_notes": [
            "Define Runtime action boundaries and contracts.",
            "Define event/webhook or API integration flow.",
            "Define secrets, retries, timeouts, idempotency, logging, and observability.",
        ],
        "source_documents": [
            "https://developer.adobe.com/commerce/extensibility/developer-agent/coding-tools/",
            "https://experienceleague.adobe.com/en/docs/commerce/cloud-service/tutorials/tutorial-prerequisites",
        ],
    },
    "starter_kit": {
        "label": "Starter Kit",
        "platform": "app_builder",
        "setup_command": APP_BUILDER_SETUP_COMMAND,
        "skills_setup_command": COMMERCE_AI_TOOLS_SETUP_COMMAND,
        "requires_specialized_skills": True,
        "skills": ["app-builder-starter-kit"],
        "triggers": [
            "starter kit",
            "new app builder app",
            "commerce app",
            "commerce extension",
            "proof of concept",
            "poc",
        ],
        "architecture_notes": [
            "Use Commerce extensibility setup as the base project scaffold.",
            "Keep Runtime actions and UI extension boundaries explicit.",
        ],
        "source_documents": [
            "https://developer.adobe.com/commerce/extensibility/developer-agent/coding-tools/",
            "https://experienceleague.adobe.com/en/docs/commerce/cloud-service/tutorials/tutorial-prerequisites",
        ],
    },
    "aem_boilerplate": {
        "label": "AEM Boilerplate",
        "platform": "app_builder",
        "setup_command": APP_BUILDER_SETUP_COMMAND,
        "skills_setup_command": COMMERCE_AI_TOOLS_SETUP_COMMAND,
        "requires_specialized_skills": True,
        "skills": ["aem-boilerplate"],
        "triggers": [
            "aem",
            "edge delivery",
            "eds",
            "boilerplate",
            "frontend site",
            "aem boilerplate",
        ],
        "architecture_notes": [
            "Separate AEM/Edge Delivery frontend concerns from Runtime/API integration concerns.",
            "Validate deployment and content-authoring constraints before implementation.",
        ],
        "source_documents": [
            "https://developer.adobe.com/commerce/extensibility/developer-agent/coding-tools/",
            "https://experienceleague.adobe.com/en/docs/commerce/cloud-service/tutorials/tutorial-prerequisites",
        ],
    },
    "generic_app_builder": {
        "label": "Generic App Builder Project",
        "platform": "app_builder",
        "setup_command": "aio app init",
        "skills_setup_command": None,
        "requires_specialized_skills": True,
        "skills": ["appbuilder-project-init"],
        "triggers": [
            "generic app builder",
            "app builder project",
            "developer console",
            "aio app init",
            "aio app dev",
            "aio app deploy",
        ],
        "architecture_notes": [
            "Use generic App Builder setup when Commerce extensibility scaffolding is not required.",
            "Define Developer Console project prerequisites and local/deploy commands.",
        ],
        "source_documents": [
            "https://developer.adobe.com/app-builder/docs/get_started/app_builder_get_started/ai-development-tools/",
        ],
    },
    "sdk_admin_ui": {
        "label": "SDK/Admin UI",
        "platform": "app_builder",
        "setup_command": None,
        "skills_setup_command": None,
        "requires_specialized_skills": False,
        "skills": [],
        "triggers": [
            "admin ui",
            "admin panel",
            "sdk",
            "configuration screen",
            "simple ui",
            "small ui extension",
        ],
        "architecture_notes": [
            "Keep setup minimal unless Runtime, events, API Mesh, or Commerce extensibility is required.",
            "Define whether a small custom skill should be created for repeatable SDK/Admin UI patterns.",
        ],
        "source_documents": [
            "https://developer.adobe.com/app-builder/docs/get_started/app_builder_get_started/ai-development-tools/",
        ],
    },
}

ADD_ON_CAPABILITIES: dict[str, dict[str, Any]] = {
    "api_mesh": {
        "label": "API Mesh",
        "triggers": [
            "api mesh",
            "graphql mesh",
            "mesh gateway",
            "mesh",
            "graphql gateway",
        ],
        "commands": API_MESH_COMMANDS,
        "skills": ["api-mesh"],
        "source_documents": ["https://developer.adobe.com/graphql-mesh-gateway/"],
        "architecture_notes": [
            "Model API Mesh as an add-on capability when GraphQL source composition is required.",
            "Include mesh configuration, create/update/get validation commands, and rollback path.",
        ],
    }
}


def select_solution_profile(state: DeliveryHubState) -> dict[str, Any]:
    """Select the allowed setup profile from deterministic platform rules."""
    platforms = list(state.get("platforms", [])) or ["generic"]
    text = state.get("input_text", "").lower()
    if "app_builder" in platforms:
        return _select_app_builder_profile(text)
    if "adobe_commerce" in platforms:
        return {
            "platform": "adobe_commerce",
            "scaffold_type": "adobe_commerce_module",
            "scaffold_label": "Adobe Commerce module/customization",
            "setup_command": None,
            "skills_setup_command": None,
            "requires_specialized_skills": False,
            "skills": ["adobe-commerce-developer"],
            "add_ons": _select_add_ons(text),
            "reason": "The classifier identified Adobe Commerce without App Builder scaffolding requirements.",
            "source_documents": ["knowledge/adobe-commerce.md"],
            "architecture_notes": [
                "Define module boundaries, dependency injection, cache/indexer impact, data patches, and tests.",
            ],
            "confidence_score": 0.8,
        }
    return {
        "platform": "generic",
        "scaffold_type": "generic_project",
        "scaffold_label": "Generic project setup",
        "setup_command": None,
        "skills_setup_command": None,
        "requires_specialized_skills": False,
        "skills": [],
        "add_ons": _select_add_ons(text),
        "reason": "No supported Adobe-specific platform was confidently identified.",
        "source_documents": [],
        "architecture_notes": [
            "Ask for platform details before prescribing Adobe setup commands."
        ],
        "confidence_score": 0.55,
    }


def _select_app_builder_profile(text: str) -> dict[str, Any]:
    scored: list[tuple[int, str, dict[str, Any]]] = []
    for key, profile in APP_BUILDER_PROFILES.items():
        score = sum(1 for trigger in profile["triggers"] if trigger in text)
        scored.append((score, key, profile))
    score, scaffold_type, selected = max(scored, key=lambda item: item[0])
    if score == 0:
        scaffold_type = "starter_kit"
        selected = APP_BUILDER_PROFILES[scaffold_type]

    add_ons = _select_add_ons(text)
    skills = list(
        dict.fromkeys(
            [
                *selected["skills"],
                *[skill for add_on in add_ons for skill in add_on["skills"]],
            ]
        )
    )
    confidence = 0.88 if score > 0 else 0.68
    return {
        "platform": "app_builder",
        "scaffold_type": scaffold_type,
        "scaffold_label": selected["label"],
        "setup_command": selected["setup_command"],
        "skills_setup_command": selected["skills_setup_command"],
        "project_commands": APP_BUILDER_PROJECT_COMMANDS
        if scaffold_type == "generic_app_builder"
        else [],
        "requires_specialized_skills": bool(
            selected["requires_specialized_skills"] or add_ons
        ),
        "skills": skills,
        "add_ons": add_ons,
        "reason": _reason_for_app_builder(scaffold_type, score),
        "source_documents": selected["source_documents"],
        "architecture_notes": selected["architecture_notes"],
        "confidence_score": confidence,
    }


def _select_add_ons(text: str) -> list[dict[str, Any]]:
    add_ons: list[dict[str, Any]] = []
    for key, add_on in ADD_ON_CAPABILITIES.items():
        if any(trigger in text for trigger in add_on["triggers"]):
            add_ons.append({"capability": key, **add_on})
    return add_ons


def _reason_for_app_builder(scaffold_type: str, score: int) -> str:
    if scaffold_type == "integration_kit":
        return "The request mentions integration/runtime/event/API behavior that requires Commerce extensibility scaffolding."
    if scaffold_type == "aem_boilerplate":
        return "The request mentions AEM, Edge Delivery, or boilerplate frontend work."
    if scaffold_type == "generic_app_builder":
        return "The request asks for a generic App Builder project rather than Commerce extensibility scaffolding."
    if scaffold_type == "sdk_admin_ui":
        return "The request is limited to SDK/Admin UI work and does not require a special Commerce scaffold."
    if score == 0:
        return "App Builder was identified, but no stronger scaffold signal was found, so Starter Kit is the safest default."
    return "The request matches App Builder starter-kit setup signals."
