import json
from pathlib import Path

import pytest

from agent import graph

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


async def test_delivery_hub_run_creates_required_artifacts(monkeypatch) -> None:
    tmp_root = Path("tests/.tmp_artifacts").resolve()
    tmp_root.mkdir(parents=True, exist_ok=True)
    monkeypatch.setattr("agent.tools.artifacts.repo_root", lambda: tmp_root)
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
    config = {"configurable": {"thread_id": "test-thread"}}
    await graph.ainvoke(
        {
            "input_text": "Implement Adobe Commerce checkout telemetry improvements.",
            "source_type": "manual_prompt",
        },
        config=config,
    )
    artifacts_root = tmp_root / "artifacts" / "runs"
    latest = sorted(artifacts_root.iterdir(), key=lambda p: p.stat().st_mtime)[-1]
    expected = {
        "input.md",
        "intake.json",
        "classification.json",
        "platform-selection.json",
        "requirements.md",
    }
    assert expected.issubset({p.name for p in latest.iterdir()})
    platform_selection = json.loads(
        (latest / "platform-selection.json").read_text(encoding="utf-8")
    )
    assert platform_selection["solution_profile"]["platform"] == "adobe_commerce"
    assert (
        platform_selection["solution_profile"]["scaffold_type"]
        == "adobe_commerce_module"
    )
