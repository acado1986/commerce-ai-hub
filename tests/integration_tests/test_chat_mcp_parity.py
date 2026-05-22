import json
from pathlib import Path

import pytest

from agent.chat_graph import workflow_graph
from agent.mcp_server import (
    BACKGROUND_JOBS,
    PENDING_RUNS,
    continue_delivery,
    plan_delivery,
)

pytestmark = pytest.mark.anyio


class _DummyResponse:
    def __init__(
        self, content: str, prompt_tokens: int = 10, completion_tokens: int = 5
    ) -> None:
        self.content = content
        self.response_metadata = {
            "model_name": "dummy-model",
            "token_usage": {
                "prompt_tokens": prompt_tokens,
                "completion_tokens": completion_tokens,
                "total_tokens": prompt_tokens + completion_tokens,
            },
        }


class _DummyModel:
    def invoke(self, prompt: str) -> _DummyResponse:
        if "Classify the request" in prompt:
            return _DummyResponse(
                json.dumps(
                    {
                        "request_type": "implementation",
                        "platforms": ["adobe_commerce"],
                        "confidence_score": 0.91,
                        "risk_level": "medium",
                        "rationale": "Implementation request with integration concerns",
                    }
                )
            )
        return _DummyResponse("# Artifact\n\nGenerated content.")


def _read_artifact_set(paths: dict[str, str], names: list[str]) -> dict[str, str]:
    result: dict[str, str] = {}
    for name in names:
        path = paths.get(name)
        assert path, f"Missing artifact path for {name}"
        result[name] = Path(path).read_text(encoding="utf-8").strip()
    return result


async def test_chat_and_mcp_generate_equivalent_artifacts(
    monkeypatch, tmp_path: Path
) -> None:
    PENDING_RUNS.clear()
    BACKGROUND_JOBS.clear()

    monkeypatch.setattr("agent.tools.artifacts.repo_root", lambda: tmp_path)
    monkeypatch.setattr(
        "agent.nodes.classify.deployment_for_classification",
        lambda: "classification-model",
    )
    monkeypatch.setattr(
        "agent.nodes.generation.deployment_for_artifact",
        lambda artifact_name, risk_level=None: f"{artifact_name}-model",
    )
    monkeypatch.setattr(
        "agent.nodes.classify.get_model", lambda **kwargs: _DummyModel()
    )
    monkeypatch.setattr(
        "agent.nodes.generation.get_model", lambda **kwargs: _DummyModel()
    )

    initial_state = {
        "run_id": "chat-parity",
        "source_type": "test",
        "input_text": "Implement Adobe Commerce checkout telemetry improvements.",
        "artifact_paths": {},
        "errors": [],
        "audit_log": [],
    }

    chat_state = workflow_graph.invoke(initial_state)
    guard = 0
    while chat_state.get("next_action") == "awaiting_approval":
        guard += 1
        assert guard < 20, "Chat workflow did not converge"
        chat_state = workflow_graph.invoke(
            {
                **chat_state,
                "approval_decision": {"action": "approve"},
            }
        )

    chat_artifacts = chat_state.get("artifact_paths", {})
    assert chat_artifacts

    mcp_payload = json.loads(
        plan_delivery(
            input_text="Implement Adobe Commerce checkout telemetry improvements.",
            source_type="test",
            timeout=30,
        )
    )
    run_id = mcp_payload["run_id"]

    guard = 0
    while True:
        guard += 1
        assert guard < 40, "MCP workflow did not converge"
        status = mcp_payload.get("status")
        if status == "awaiting_decision":
            mcp_payload = json.loads(
                continue_delivery(run_id, action="continue", timeout=30)
            )
            continue
        if status == "awaiting_approval":
            mcp_payload = json.loads(
                continue_delivery(run_id, action="approve", timeout=30)
            )
            continue
        assert status == "completed"
        break

    mcp_artifacts = mcp_payload.get("artifact_paths", {})
    assert mcp_artifacts

    parity_names = [
        "classification.json",
        "platform-selection.json",
        "requirements.md",
        "architecture.md",
        "implementation-plan.md",
        "review-checklist.md",
        "qa-plan.md",
        "ticket-comment.md",
        "audit.json",
    ]

    chat_content = _read_artifact_set(chat_artifacts, parity_names)
    mcp_content = _read_artifact_set(mcp_artifacts, parity_names)

    for name in parity_names:
        if name == "audit.json":
            chat_audit = json.loads(chat_content[name])
            mcp_audit = json.loads(mcp_content[name])
            assert chat_audit["request_type"] == mcp_audit["request_type"]
            assert chat_audit["mapped_request_type"] == mcp_audit["mapped_request_type"]
            assert chat_audit["platforms"] == mcp_audit["platforms"]
            continue
        if name == "platform-selection.json":
            chat_platform = json.loads(chat_content[name])["solution_profile"]
            mcp_platform = json.loads(mcp_content[name])["solution_profile"]
            stable_keys = [
                "platform",
                "scaffold_type",
                "setup_command",
                "skills_setup_command",
                "skills",
                "project_commands",
                "requires_specialized_skills",
            ]
            for key in stable_keys:
                assert chat_platform[key] == mcp_platform[key]
            assert [item["capability"] for item in chat_platform.get("add_ons", [])] == [
                item["capability"] for item in mcp_platform.get("add_ons", [])
            ]
            continue
        assert chat_content[name] == mcp_content[name]

    PENDING_RUNS.clear()
    BACKGROUND_JOBS.clear()
