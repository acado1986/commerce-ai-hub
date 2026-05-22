import json

from agent.mcp_server import PENDING_RUNS, continue_delivery, plan_delivery


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


def test_mcp_plan_and_continue_drive_checkpointed_graph(monkeypatch, tmp_path) -> None:
    PENDING_RUNS.clear()
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
