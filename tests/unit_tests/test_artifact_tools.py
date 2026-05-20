import json

import pytest
from langchain_core.messages import AIMessage, ToolMessage

from agent.orchestrator.tool_graph import artifact_tool_graph
from agent.tools import read_run_artifact, write_run_json_artifact, write_run_text_artifact
from agent.tools.artifacts import write_text_artifact


def test_artifact_tools_read_and_write(monkeypatch, tmp_path) -> None:
    monkeypatch.setattr("agent.tools.artifacts.repo_root", lambda: tmp_path)

    text_path = write_run_text_artifact.invoke(
        {"run_id": "tool-test", "name": "requirements.md", "content": "# Requirements"}
    )
    json_path = write_run_json_artifact.invoke(
        {"run_id": "tool-test", "name": "classification.json", "payload": {"ok": True}}
    )

    assert text_path.endswith("requirements.md")
    assert json_path.endswith("classification.json")
    assert read_run_artifact.invoke(
        {"run_id": "tool-test", "name": "requirements.md"}
    ) == "# Requirements"
    assert json.loads(
        read_run_artifact.invoke({"run_id": "tool-test", "name": "classification.json"})
    ) == {"ok": True}


def test_artifact_tool_rejects_path_traversal(monkeypatch, tmp_path) -> None:
    monkeypatch.setattr("agent.tools.artifacts.repo_root", lambda: tmp_path)

    with pytest.raises(ValueError):
        write_run_text_artifact.invoke(
            {"run_id": "tool-test", "name": "../escape.md", "content": "bad"}
        )


def test_artifact_wrapper_uses_tool_graph(monkeypatch, tmp_path) -> None:
    monkeypatch.setattr("agent.tools.artifacts.repo_root", lambda: tmp_path)

    path = write_text_artifact("tool-graph-test", "ticket-comment.md", "ready")

    assert path.endswith("ticket-comment.md")


def test_artifact_tool_graph_executes_toolnode(monkeypatch, tmp_path) -> None:
    monkeypatch.setattr("agent.tools.artifacts.repo_root", lambda: tmp_path)

    result = artifact_tool_graph.invoke(
        {
            "messages": [
                AIMessage(
                    content="",
                    tool_calls=[
                        {
                            "name": "write_run_text_artifact",
                            "args": {
                                "run_id": "tool-node-test",
                                "name": "qa-plan.md",
                                "content": "# QA",
                            },
                            "id": "call_write_qa",
                        }
                    ],
                )
            ]
        }
    )

    message = result["messages"][-1]
    assert isinstance(message, ToolMessage)
    assert message.name == "write_run_text_artifact"
    assert message.content.endswith("qa-plan.md")
