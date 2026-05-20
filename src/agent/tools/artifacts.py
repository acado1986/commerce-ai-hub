"""LangChain tools for deterministic run artifact access."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from langchain_core.messages import AIMessage, ToolMessage
from langchain_core.tools import tool


def repo_root() -> Path:
    return Path(__file__).resolve().parents[3]


def artifact_run_dir(run_id: str) -> Path:
    path = repo_root() / "artifacts" / "runs" / run_id
    path.mkdir(parents=True, exist_ok=True)
    return path


def _validate_artifact_name(name: str) -> str:
    path = Path(name)
    if path.is_absolute() or ".." in path.parts or path.name != name:
        raise ValueError(f"Invalid artifact name: {name}")
    return name


@tool
def read_run_artifact(run_id: str, name: str) -> str:
    """Read a text artifact from artifacts/runs/<run_id>/."""
    safe_name = _validate_artifact_name(name)
    path = artifact_run_dir(run_id) / safe_name
    return path.read_text(encoding="utf-8")


@tool
def write_run_text_artifact(run_id: str, name: str, content: str) -> str:
    """Write a text artifact into artifacts/runs/<run_id>/ and return its path."""
    safe_name = _validate_artifact_name(name)
    path = artifact_run_dir(run_id) / safe_name
    path.write_text(content, encoding="utf-8")
    return str(path)


@tool
def write_run_json_artifact(run_id: str, name: str, payload: dict[str, Any]) -> str:
    """Write a JSON artifact into artifacts/runs/<run_id>/ and return its path."""
    safe_name = _validate_artifact_name(name)
    path = artifact_run_dir(run_id) / safe_name
    path.write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")
    return str(path)


def read_artifact(run_id: str, name: str) -> str:
    """Deterministically invoke the read artifact tool."""
    return _invoke_artifact_tool(
        "read_run_artifact",
        {"run_id": run_id, "name": name},
    )


def write_text_artifact(run_id: str, name: str, content: str) -> str:
    """Deterministically invoke the text artifact writer tool."""
    return _invoke_artifact_tool(
        "write_run_text_artifact",
        {"run_id": run_id, "name": name, "content": content},
    )


def write_json_artifact(run_id: str, name: str, payload: dict[str, Any]) -> str:
    """Deterministically invoke the JSON artifact writer tool."""
    return _invoke_artifact_tool(
        "write_run_json_artifact",
        {"run_id": run_id, "name": name, "payload": payload},
    )


ARTIFACT_TOOLS = [
    read_run_artifact,
    write_run_text_artifact,
    write_run_json_artifact,
]


def _invoke_artifact_tool(name: str, args: dict[str, Any]) -> str:
    """Invoke artifact tools through the controlled LangGraph ToolNode subgraph."""
    from agent.orchestrator.tool_graph import artifact_tool_graph

    result = artifact_tool_graph.invoke(
        {
            "messages": [
                AIMessage(
                    content="",
                    tool_calls=[
                        {
                            "name": name,
                            "args": args,
                            "id": f"{name}_call",
                        }
                    ],
                )
            ]
        }
    )
    message = result["messages"][-1]
    if not isinstance(message, ToolMessage):
        raise RuntimeError(f"Artifact tool {name} did not return a ToolMessage.")
    return str(message.content)
