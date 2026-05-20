"""Common helpers for delivery hub nodes."""

from __future__ import annotations

from pathlib import Path

from agent.orchestrator.state import DeliveryHubState
from agent.tools.artifacts import (
    artifact_run_dir,
    write_json_artifact as invoke_write_json_artifact,
    write_text_artifact as invoke_write_text_artifact,
)


def repo_root() -> Path:
    return Path(__file__).resolve().parents[3]


def run_dir(state: DeliveryHubState) -> Path:
    return artifact_run_dir(state["run_id"])


def write_text_artifact(
    state: DeliveryHubState,
    name: str,
    content: str,
) -> dict[str, str]:
    return {name: invoke_write_text_artifact(state["run_id"], name, content)}


def write_json_artifact(state: DeliveryHubState, name: str, payload: dict) -> dict[str, str]:
    return {name: invoke_write_json_artifact(state["run_id"], name, payload)}
