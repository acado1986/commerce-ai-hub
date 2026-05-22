from pathlib import Path

from agent.agent_runtime import build_artifact_agent
from agent.agent_profiles import load_agent_profile
from agent.nodes.architecture import architecture_node
from agent.nodes.requirements import requirements_node


class _RecordingResponse:
    content = "# Requirements\n\nGenerated content."


class _RecordingModel:
    def __init__(self) -> None:
        self.prompts: list[str] = []

    def invoke(self, prompt: str) -> _RecordingResponse:
        self.prompts.append(prompt)
        return _RecordingResponse()


def test_load_agent_profile_reads_role_definition() -> None:
    profile = load_agent_profile("business_analyst_agent.md")

    assert "BusinessAnalystAgent" in profile
    assert "## SOP" in profile


def test_requirements_node_uses_business_analyst_profile(monkeypatch, tmp_path: Path) -> None:
    model = _RecordingModel()
    monkeypatch.setattr("agent.nodes.common.repo_root", lambda: tmp_path)
    monkeypatch.setattr(
        "agent.nodes.generation.deployment_for_artifact",
        lambda artifact_name, risk_level=None: "requirements-model",
    )
    monkeypatch.setattr("agent.nodes.generation.get_model", lambda **kwargs: model)

    requirements_node(
        {
            "run_id": "profile-test",
            "input_text": "Plan an Adobe Commerce checkout improvement.",
            "source_type": "test",
            "artifact_paths": {},
            "errors": [],
            "audit_log": [],
        }
    )

    assert model.prompts
    assert "BusinessAnalystAgent" in model.prompts[0]
    assert "You must communicate through the requested artifact only" in model.prompts[0]
    assert "Allowed tools for this agent" in model.prompts[0]
    assert "generate_markdown_artifact" in model.prompts[0]


def test_requirements_node_prefers_platform_specific_profile(
    monkeypatch, tmp_path: Path
) -> None:
    model = _RecordingModel()
    agents_root = tmp_path / "agents"
    (agents_root / "platforms" / "app_builder").mkdir(parents=True, exist_ok=True)
    (agents_root / "business_analyst_agent.md").write_text(
        "# Agent: BusinessAnalystAgent\n",
        encoding="utf-8",
    )
    (agents_root / "platforms" / "app_builder" / "business_analyst_agent.md").write_text(
        "# Agent: AppBuilderBusinessAnalystAgent\n",
        encoding="utf-8",
    )

    load_agent_profile.cache_clear()
    monkeypatch.setattr("agent.agent_profiles.repo_root", lambda: tmp_path)
    monkeypatch.setattr("agent.nodes.common.repo_root", lambda: tmp_path)
    monkeypatch.setattr(
        "agent.nodes.generation.deployment_for_artifact",
        lambda artifact_name, risk_level=None: "requirements-model",
    )
    monkeypatch.setattr("agent.nodes.generation.get_model", lambda **kwargs: model)

    requirements_node(
        {
            "run_id": "platform-profile-test",
            "input_text": "Plan an App Builder integration.",
            "source_type": "test",
            "platforms": ["app_builder"],
            "solution_profile": {"platform": "app_builder"},
            "artifact_paths": {},
            "errors": [],
            "audit_log": [],
        }
    )

    assert model.prompts
    assert "AppBuilderBusinessAnalystAgent" in model.prompts[0]
    assert "platforms/app_builder/business_analyst_agent.md" in model.prompts[0]


def test_artifact_agent_has_scoped_tools() -> None:
    agent = build_artifact_agent(
        "platforms/adobe_commerce/solution_architect_agent.md"
    )

    tool_names = {tool.name for tool in agent.allowed_tools}
    forbidden_names = {tool.name for tool in agent.forbidden_tools}
    assert agent.name == "SolutionArchitectAgent"
    assert "read_adobe_knowledge" in tool_names
    assert "generate_markdown_artifact" in tool_names
    assert "modify_source_code" in forbidden_names


def test_architecture_node_uses_platform_specific_profile(monkeypatch) -> None:
    captured: dict[str, str] = {}

    def _fake_generate_markdown(*, agent_profile: str, **kwargs):
        captured["agent_profile"] = agent_profile
        return kwargs["state"]

    monkeypatch.setattr(
        "agent.nodes.architecture.generate_markdown", _fake_generate_markdown
    )

    architecture_node(
        {
            "input_text": "Design App Builder runtime integration.",
            "platforms": ["app_builder"],
            "solution_profile": {"platform": "app_builder"},
        }
    )

    assert captured["agent_profile"] == "solution_architect_agent.md"


def test_architecture_node_falls_back_to_default_profile(monkeypatch) -> None:
    captured: dict[str, str] = {}

    def _fake_generate_markdown(*, agent_profile: str, **kwargs):
        captured["agent_profile"] = agent_profile
        return kwargs["state"]

    monkeypatch.setattr(
        "agent.nodes.architecture.generate_markdown", _fake_generate_markdown
    )

    architecture_node({"input_text": "Design solution."})

    assert captured["agent_profile"] == "solution_architect_agent.md"
