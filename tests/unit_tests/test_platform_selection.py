import json
from pathlib import Path

from agent.nodes.platform_selection import platform_selection_node
from agent.platform_catalog import load_platform_catalog, select_solution_profile


def test_app_builder_integration_kit_selected_for_runtime_and_events() -> None:
    profile = select_solution_profile(
        {
            "platforms": ["app_builder"],
            "input_text": "Build an App Builder Commerce integration with runtime actions, webhooks, and API Mesh.",
        }
    )

    assert profile["platform"] == "app_builder"
    assert profile["scaffold_type"] == "integration_kit"
    assert profile["setup_command"] == "aio commerce extensibility app-setup"
    assert profile["skills_setup_command"] == "aio commerce extensibility tools-setup"
    assert "app-builder-integration-kit" in profile["skills"]
    assert "api-mesh" in profile["skills"]
    assert profile["add_ons"][0]["capability"] == "api_mesh"
    assert "aio api-mesh:create" in profile["add_ons"][0]["commands"]


def test_app_builder_sdk_admin_ui_does_not_require_special_scaffold() -> None:
    profile = select_solution_profile(
        {
            "platforms": ["app_builder"],
            "input_text": "Create a simple SDK admin UI configuration screen.",
        }
    )

    assert profile["scaffold_type"] == "sdk_admin_ui"
    assert profile["setup_command"] is None
    assert profile["requires_specialized_skills"] is False
    assert profile["skills"] == []


def test_generic_app_builder_uses_aio_app_init() -> None:
    profile = select_solution_profile(
        {
            "platforms": ["app_builder"],
            "input_text": "Set up a generic App Builder project with Developer Console and aio app init.",
        }
    )

    assert profile["scaffold_type"] == "generic_app_builder"
    assert profile["setup_command"] == "aio app init"
    assert profile["skills"] == ["appbuilder-project-init"]
    assert profile["project_commands"] == [
        "aio app init",
        "aio app dev",
        "aio app deploy",
    ]


def test_platform_selection_node_writes_artifact(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.setattr("agent.tools.artifacts.repo_root", lambda: tmp_path)

    state = platform_selection_node(
        {
            "run_id": "platform-test",
            "platforms": ["app_builder"],
            "input_text": "Use App Builder integration kit for events.",
            "artifact_paths": {},
            "audit_log": [],
        }
    )

    path = Path(state["artifact_paths"]["platform-selection.json"])
    payload = json.loads(path.read_text(encoding="utf-8"))
    assert payload["solution_profile"]["scaffold_type"] == "integration_kit"
    assert (
        state["solution_profile"]["setup_command"]
        == "aio commerce extensibility app-setup"
    )
    assert state["next_action"] == "continue"


def test_platform_catalog_structure_loads() -> None:
    catalog = load_platform_catalog()

    assert catalog["version"] == 1
    assert "platforms" in catalog
    assert "profiles" in catalog
    assert "capabilities" in catalog
    assert "integration_kit" in catalog["profiles"]
    assert "api_mesh" in catalog["capabilities"]


def test_llm_selection_is_constrained_to_catalog(monkeypatch) -> None:
    class _DummySelectionResponse:
        content = json.dumps(
            {
                "profile_id": "integration_kit",
                "add_on_ids": ["api_mesh", "invalid_capability"],
                "confidence_score": 0.93,
                "reason": "Runtime actions and API Mesh were requested.",
            }
        )

    class _DummySelectionModel:
        def invoke(self, prompt: str):
            return _DummySelectionResponse()

    monkeypatch.setattr(
        "agent.platform_catalog.get_model", lambda **kwargs: _DummySelectionModel()
    )
    monkeypatch.setattr(
        "agent.platform_catalog.invoke_model",
        lambda model, prompt: model.invoke(prompt),
    )
    monkeypatch.setattr(
        "agent.platform_catalog.deployment_for_classification", lambda: "dummy"
    )
    monkeypatch.setenv("PLATFORM_SELECTION_USE_LLM", "true")

    profile = select_solution_profile(
        {
            "platforms": ["app_builder"],
            "input_text": "Need App Builder runtime actions with API Mesh.",
            "timeout": 30,
        }
    )

    assert profile["selection_method"] == "llm"
    assert profile["scaffold_type"] == "integration_kit"
    assert [item["capability"] for item in profile["add_ons"]] == ["api_mesh"]
    assert "invalid_capability" not in {
        item["capability"] for item in profile["add_ons"]
    }
