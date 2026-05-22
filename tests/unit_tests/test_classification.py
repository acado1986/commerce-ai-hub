import json
from pathlib import Path

import pytest

from agent.nodes.classify import _classify_payload, classify_node
from agent.platform_catalog import load_platform_catalog


class _RecordingResponse:
    def __init__(self, content: str) -> None:
        self.content = content
        self.response_metadata = {
            "model_name": "classification-model",
            "token_usage": {
                "prompt_tokens": 10,
                "completion_tokens": 5,
                "total_tokens": 15,
            },
        }


class _RecordingModel:
    def __init__(self) -> None:
        self.prompts: list[str] = []

    def invoke(self, prompt: str) -> _RecordingResponse:
        self.prompts.append(prompt)
        return _RecordingResponse(
            json.dumps(
                {
                    "request_type": "implementation",
                    "platforms": ["shopify"],
                    "confidence_score": 0.92,
                    "risk_level": "medium",
                    "rationale": "Shopify app request",
                }
            )
        )


@pytest.fixture()
def catalog_with_shopify(monkeypatch, tmp_path: Path) -> Path:
    catalog_path = tmp_path / "platform_catalog.yaml"
    catalog_path.write_text(
        json.dumps(
            {
                "version": 1,
                "platforms": {
                    "shopify": {
                        "profile_ids": ["shopify_app"],
                        "default_profile_id": "shopify_app",
                    },
                    "generic": {
                        "profile_ids": ["generic_project"],
                        "default_profile_id": "generic_project",
                    },
                },
                "profiles": {
                    "shopify_app": {
                        "label": "Shopify App",
                        "platform": "shopify",
                        "setup_command": "shopify app init",
                        "skills_setup_command": None,
                        "requires_specialized_skills": True,
                        "skills": ["shopify-app-dev"],
                        "project_commands": ["shopify app dev"],
                        "triggers": ["shopify", "shopify app"],
                        "source_documents": ["https://shopify.dev/docs/apps/build"],
                        "architecture_notes": [
                            "Define auth, webhook, and app-extension boundaries."
                        ],
                    },
                    "generic_project": {
                        "label": "Generic project setup",
                        "platform": "generic",
                        "setup_command": None,
                        "skills_setup_command": None,
                        "requires_specialized_skills": False,
                        "skills": [],
                        "project_commands": [],
                        "triggers": [],
                        "source_documents": [],
                        "architecture_notes": [
                            "Ask for platform details before prescribing setup commands."
                        ],
                    },
                },
                "capabilities": {},
            }
        ),
        encoding="utf-8",
    )
    monkeypatch.setenv("PLATFORM_CATALOG_PATH", str(catalog_path))
    load_platform_catalog.cache_clear()
    yield catalog_path
    load_platform_catalog.cache_clear()


def test_classification_prompt_uses_catalog_platforms(
    monkeypatch,
    catalog_with_shopify: Path,
) -> None:
    model = _RecordingModel()
    monkeypatch.setattr(
        "agent.nodes.classify.deployment_for_classification",
        lambda: "classification-model",
    )
    monkeypatch.setattr(
        "agent.nodes.classify.model_name_for_deployment",
        lambda deployment: deployment,
    )
    monkeypatch.setattr("agent.nodes.classify.get_model", lambda **kwargs: model)
    monkeypatch.setattr(
        "agent.nodes.classify.invoke_model",
        lambda model, prompt, config=None: model.invoke(prompt),
    )

    payload, _usage = _classify_payload("Build a Shopify app.", timeout=30)

    assert payload["platforms"] == ["shopify"]
    assert model.prompts
    assert 'Allowed platforms values: ["shopify", "generic"]' in model.prompts[0]
    assert '"triggers": ["shopify", "shopify app"]' in model.prompts[0]
    assert "adobe_commerce, app_builder, generic" not in model.prompts[0]


def test_classify_node_accepts_catalog_only_platform(
    monkeypatch,
    tmp_path: Path,
    catalog_with_shopify: Path,
) -> None:
    monkeypatch.setattr("agent.tools.artifacts.repo_root", lambda: tmp_path)
    monkeypatch.setattr(
        "agent.nodes.classify._classify_payload",
        lambda text, timeout, config=None: (
            {
                "request_type": "implementation",
                "platforms": ["shopify"],
                "confidence_score": 0.9,
                "risk_level": "medium",
                "rationale": "Shopify app request",
            },
            {"input_tokens": 1, "output_tokens": 1, "total_tokens": 2},
        ),
    )

    state = classify_node(
        {
            "run_id": "shopify-classification",
            "input_text": "Build a Shopify checkout extension.",
            "source_type": "test",
            "artifact_paths": {},
            "errors": [],
            "audit_log": [],
        }
    )

    assert state["platforms"] == ["shopify"]
    path = Path(state["artifact_paths"]["classification.json"])
    classification = json.loads(path.read_text(encoding="utf-8"))
    assert classification["platforms"] == ["shopify"]
