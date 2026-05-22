import json
import time

from agent.mcp_server import (
    BACKGROUND_JOBS,
    PENDING_RUNS,
    cancel_delivery,
    continue_delivery,
    get_delivery_status,
    plan_delivery,
    start_delivery_async,
)


class _DummyResponse:
    def __init__(self, content: str) -> None:
        self.content = content
        self.response_metadata = {
            "model_name": "dummy-model",
            "token_usage": {
                "prompt_tokens": 10,
                "completion_tokens": 5,
                "total_tokens": 15,
            },
        }


class _DummyModel:
    def invoke(self, prompt: str) -> _DummyResponse:
        return _DummyResponse(
            json.dumps(
                {
                    "request_type": "implementation",
                    "platforms": ["adobe_commerce"],
                    "confidence_score": 0.9,
                    "risk_level": "medium",
                    "rationale": "Implementation request",
                }
            )
        )


class _SlowArtifactResponse:
    def __init__(self, content: str) -> None:
        self.content = content
        self.response_metadata = {
            "model_name": "dummy-artifact-model",
            "token_usage": {
                "prompt_tokens": 10,
                "completion_tokens": 5,
                "total_tokens": 15,
            },
        }


class _SlowArtifactModel:
    def invoke(self, prompt: str) -> _SlowArtifactResponse:
        time.sleep(0.2)
        return _SlowArtifactResponse("# Artifact\n\nGenerated content.")


def test_mcp_plan_and_continue_drive_checkpointed_graph(monkeypatch, tmp_path) -> None:
    PENDING_RUNS.clear()
    BACKGROUND_JOBS.clear()
    monkeypatch.setattr("agent.tools.artifacts.repo_root", lambda: tmp_path)
    monkeypatch.setattr(
        "agent.nodes.classify.deployment_for_classification",
        lambda: "classification-model",
    )
    monkeypatch.setattr(
        "agent.nodes.classify.get_model", lambda **kwargs: _DummyModel()
    )

    planned = json.loads(
        plan_delivery(
            "Implement Adobe Commerce order GUID planning.",
            source_type="test",
            timeout=30,
        )
    )
    assert planned["current_stage"] == "intake"
    assert planned["next_stage"] == "classify"

    continued = json.loads(
        continue_delivery(planned["run_id"], action="continue", timeout=30)
    )
    assert continued["completed_stage"] == "classify"
    assert continued["next_stage"] == "platform_selection"

    continued = json.loads(
        continue_delivery(planned["run_id"], action="continue", timeout=30)
    )
    assert continued["completed_stage"] == "platform_selection"
    assert continued["next_stage"] == "requirements"
    assert PENDING_RUNS[planned["run_id"]]["mode"] == "graph"

    PENDING_RUNS.clear()
    BACKGROUND_JOBS.clear()


def test_mcp_async_start_status_cancel(monkeypatch, tmp_path) -> None:
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
        "agent.nodes.generation.get_model", lambda **kwargs: _SlowArtifactModel()
    )

    started = json.loads(
        start_delivery_async(
            input_text="Implement Adobe Commerce order GUID planning.",
            source_type="test",
            timeout=30,
        )
    )
    run_id = started["run_id"]
    assert started["status"] in {"awaiting_decision", "awaiting_approval"}

    status = json.loads(get_delivery_status(run_id))
    assert status["run_id"] == run_id
    assert "background" in status

    cancelled = json.loads(cancel_delivery(run_id, wait_seconds=0.01))
    assert cancelled["run_id"] == run_id
    assert cancelled["status"] in {"cancelling", "cancelled", "awaiting_approval"}

    PENDING_RUNS.clear()
    BACKGROUND_JOBS.clear()
