"""Low-level graph interaction helpers for MCP service."""

from __future__ import annotations

import contextlib
import io
import json
from pathlib import Path
from typing import Any

from langgraph.types import Command

from agent.mcp.runtime import PENDING_RUNS


def interrupt_payload(result: dict[str, Any]) -> dict[str, Any] | None:
    interrupts = result.get("__interrupt__")
    if not interrupts:
        return None
    return interrupts[0].value if interrupts else None


def run_artifact_paths(run_id: str) -> dict[str, str]:
    run_dir = Path("artifacts") / "runs" / run_id
    return {path.name: str(path) for path in run_dir.glob("*") if path.is_file()}


def read_json_artifact(run_id: str, name: str) -> dict[str, Any]:
    path = Path("artifacts") / "runs" / run_id / name
    if not path.exists():
        return {}
    return json.loads(path.read_text(encoding="utf-8"))


def graph_config(thread_id: str) -> dict[str, Any]:
    from agent.observability import langgraph_config

    run_id = thread_id.removeprefix("mcp-") if thread_id.startswith("mcp-") else None
    return langgraph_config(
        thread_id=thread_id,
        run_id=run_id,
        source_type="mcp",
        trace_name="ai-delivery-hub-mcp",
    )


def flush_traces() -> None:
    from agent.observability import flush_langfuse

    flush_langfuse()


def state_values(thread_id: str) -> dict[str, Any]:
    from agent.orchestrator.graph import cli_graph

    return dict(cli_graph.get_state(graph_config(thread_id)).values or {})


def next_nodes(thread_id: str) -> tuple[str, ...]:
    from agent.orchestrator.graph import cli_graph

    return tuple(cli_graph.get_state(graph_config(thread_id)).next or ())


def status_for_graph_position(
    next_stage_nodes: tuple[str, ...], interrupted: bool
) -> str:
    if interrupted:
        return "awaiting_approval"
    if not next_stage_nodes:
        return "completed"
    if next_stage_nodes == ("approval",):
        return "awaiting_approval"
    return "awaiting_decision"


def graph_result_payload(
    run_id: str,
    thread_id: str,
    result: dict[str, Any] | None = None,
    completed_stage: str | None = None,
) -> dict[str, Any]:
    values = state_values(thread_id)
    stage_nodes = next_nodes(thread_id)
    approval_payload = interrupt_payload(result or {})
    artifact_paths = (
        values.get("artifact_paths")
        or (approval_payload or {}).get("artifact_paths", {})
        or run_artifact_paths(run_id)
    )
    status = status_for_graph_position(stage_nodes, approval_payload is not None)
    PENDING_RUNS[run_id].update(
        {
            "status": status,
            "state": values,
            "next_nodes": stage_nodes,
            "artifact_paths": artifact_paths,
            "approval_payload": approval_payload,
            "errors": values.get("errors", []),
        }
    )
    return {
        "run_id": run_id,
        "status": status,
        "current_stage": values.get("current_stage"),
        "completed_stage": completed_stage,
        "next_stage": stage_nodes[0] if stage_nodes else None,
        "approval_status": values.get("approval_status"),
        "next_action": values.get("next_action"),
        "artifact_dir": str(Path("artifacts") / "runs" / run_id),
        "artifact_paths": artifact_paths,
        "errors": values.get("errors", []),
        "approval_payload": approval_payload,
    }


def invoke_graph_step(
    run_id: str,
    graph_input: dict[str, Any] | Command | None,
    interrupt_after: list[str] | None,
    timeout: int,
) -> dict[str, Any]:
    from agent.orchestrator.graph import cli_graph

    _ = timeout
    thread_id = PENDING_RUNS[run_id]["thread_id"]
    with (
        contextlib.redirect_stdout(io.StringIO()),
        contextlib.redirect_stderr(io.StringIO()),
    ):
        return cli_graph.invoke(
            graph_input,
            config=graph_config(thread_id),
            interrupt_after=interrupt_after,
        )


def enter_approval_if_next(run_id: str, timeout: int) -> dict[str, Any] | None:
    if next_nodes(PENDING_RUNS[run_id]["thread_id"]) != ("approval",):
        return None
    return invoke_graph_step(run_id, None, None, timeout)
