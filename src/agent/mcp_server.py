"""MCP server for AI Delivery Hub."""

from __future__ import annotations

import contextlib
import io
import json
import warnings
import uuid
from pathlib import Path
from typing import Any

from langgraph.types import Command
from mcp.server.fastmcp import FastMCP

warnings.filterwarnings("ignore", message=".*allowed_objects.*")

mcp = FastMCP("ai-delivery-hub")
PENDING_RUNS: dict[str, dict[str, Any]] = {}


@mcp.prompt(
    name="run_delivery_workflow",
    title="Run Delivery Workflow",
    description="Instruction prompt for running the full delivery workflow through short MCP tool calls.",
)
def run_delivery_workflow(request: str) -> str:
    """Return instructions for a one-chat delivery workflow."""
    return (
        "Run the AI Delivery Hub workflow for the following request in one chat turn. "
        "Do not call a single long-running tool. Use short tool calls instead.\n\n"
        "Steps:\n"
        "1. Call plan_delivery with the request text.\n"
        "2. Read the returned run_id.\n"
        "3. Repeatedly call continue_delivery with action='continue' until the tool returns status='awaiting_approval'.\n"
        "4. If any stage returns status='failed', summarize the error and stop.\n"
        "5. When awaiting approval, summarize generated artifact paths and ask the user whether to approve, revise, or reject.\n"
        "6. If the user asks for changes, call continue_delivery with action='revise' and their instruction, then ask again.\n"
        "7. If the user approves, call continue_delivery with action='approve'. If they reject, call action='reject'.\n\n"
        f"Request:\n{request}"
    )


def _interrupt_payload(result: dict[str, Any]) -> dict[str, Any] | None:
    interrupts = result.get("__interrupt__")
    if not interrupts:
        return None
    return interrupts[0].value if interrupts else None


def _run_artifact_paths(run_id: str) -> dict[str, str]:
    run_dir = Path("artifacts") / "runs" / run_id
    return {path.name: str(path) for path in run_dir.glob("*") if path.is_file()}


def _read_json_artifact(run_id: str, name: str) -> dict[str, Any]:
    path = Path("artifacts") / "runs" / run_id / name
    if not path.exists():
        return {}
    return json.loads(path.read_text(encoding="utf-8"))


def _graph_config(thread_id: str) -> dict[str, Any]:
    from agent.observability import langgraph_config

    run_id = thread_id.removeprefix("mcp-") if thread_id.startswith("mcp-") else None
    return langgraph_config(
        thread_id=thread_id,
        run_id=run_id,
        source_type="mcp",
        trace_name="ai-delivery-hub-mcp",
    )


def _flush_traces() -> None:
    from agent.observability import flush_langfuse

    flush_langfuse()


def _state_values(thread_id: str) -> dict[str, Any]:
    from agent.orchestrator.graph import cli_graph

    return dict(cli_graph.get_state(_graph_config(thread_id)).values or {})


def _next_nodes(thread_id: str) -> tuple[str, ...]:
    from agent.orchestrator.graph import cli_graph

    return tuple(cli_graph.get_state(_graph_config(thread_id)).next or ())


def _status_for_graph_position(next_nodes: tuple[str, ...], interrupted: bool) -> str:
    if interrupted:
        return "awaiting_approval"
    if not next_nodes:
        return "completed"
    if next_nodes == ("approval",):
        return "awaiting_approval"
    return "awaiting_decision"


def _graph_result_payload(
    run_id: str,
    thread_id: str,
    result: dict[str, Any] | None = None,
    completed_stage: str | None = None,
) -> dict[str, Any]:
    values = _state_values(thread_id)
    next_nodes = _next_nodes(thread_id)
    interrupt_payload = _interrupt_payload(result or {})
    artifact_paths = (
        values.get("artifact_paths")
        or (interrupt_payload or {}).get("artifact_paths", {})
        or _run_artifact_paths(run_id)
    )
    status = _status_for_graph_position(next_nodes, interrupt_payload is not None)
    PENDING_RUNS[run_id].update(
        {
            "status": status,
            "state": values,
            "next_nodes": next_nodes,
            "artifact_paths": artifact_paths,
            "approval_payload": interrupt_payload,
            "errors": values.get("errors", []),
        }
    )
    return {
        "run_id": run_id,
        "status": status,
        "current_stage": values.get("current_stage"),
        "completed_stage": completed_stage,
        "next_stage": next_nodes[0] if next_nodes else None,
        "approval_status": values.get("approval_status"),
        "next_action": values.get("next_action"),
        "artifact_dir": str(Path("artifacts") / "runs" / run_id),
        "artifact_paths": artifact_paths,
        "errors": values.get("errors", []),
        "approval_payload": interrupt_payload,
    }


def _invoke_graph_step(
    run_id: str,
    graph_input: dict[str, Any] | Command | None,
    interrupt_after: list[str] | None,
    timeout: int,
) -> dict[str, Any]:
    from agent.orchestrator.graph import cli_graph

    thread_id = PENDING_RUNS[run_id]["thread_id"]
    with contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(io.StringIO()):
        return cli_graph.invoke(
            graph_input,
            config=_graph_config(thread_id),
            interrupt_after=interrupt_after,
        )


def _enter_approval_if_next(run_id: str, timeout: int) -> dict[str, Any] | None:
    if _next_nodes(PENDING_RUNS[run_id]["thread_id"]) != ("approval",):
        return None
    return _invoke_graph_step(run_id, None, None, timeout)


@mcp.tool(title="Draft Delivery", structured_output=False)
def draft_delivery(input_text: str, timeout: int = 90) -> str:
    """Create a fast one-call delivery brief without running the full graph."""
    from agent.llm import (
        deployment_for_draft,
        get_model,
        invoke_model,
        model_name_for_deployment,
    )
    from agent.observability import langchain_trace_config

    run_id = str(uuid.uuid4())
    deployment = deployment_for_draft()
    model_name = model_name_for_deployment(deployment)
    prompt = (
        "Create a concise professional AI Delivery Hub brief for this request. "
        "Do not write source code. Include these sections only: "
        "Request classification, Requirements, Architecture approach, "
        "Implementation plan, QA plan, Review checklist, Risks, Approval recommendation. "
        "If Adobe Commerce is involved, include relevant modules, db schema/data patch, "
        "di.xml/events.xml, observer/plugin choice, service contracts/API exposure, "
        "cache/indexer impact, Cloud compatibility, and tests.\n\n"
        f"Request:\n{input_text}"
    )
    try:
        response = invoke_model(
            get_model(timeout=timeout, deployment=deployment),
            prompt,
            langchain_trace_config(
                trace_name="ai-delivery-hub-draft",
                run_id=run_id,
                source_type="mcp",
                stage="draft",
                model=model_name,
            ),
        )
        return response.content if isinstance(response.content, str) else str(response.content)
    finally:
        _flush_traces()


@mcp.tool(title="Plan Delivery", structured_output=False)
def plan_delivery(
    input_text: str,
    source_type: str = "mcp",
    timeout: int = 900,
) -> str:
    """Start a checkpointed LangGraph delivery run and pause after intake."""
    run_id = f"mcp-{uuid.uuid4()}"
    thread_id = f"mcp-{run_id}"
    PENDING_RUNS[run_id] = {
        "mode": "graph",
        "thread_id": thread_id,
        "status": "starting",
        "artifact_paths": {},
        "errors": [],
    }
    try:
        result = _invoke_graph_step(
            run_id,
            {
                "run_id": run_id,
                "input_text": input_text,
                "source_type": source_type,
                "timeout": timeout,
                "errors": [],
                "audit_log": [],
                "artifact_paths": {},
            },
            ["intake"],
            timeout,
        )
        _flush_traces()
    except Exception as exc:  # noqa: BLE001
        PENDING_RUNS[run_id].update(
            {
                "status": "failed",
                "error": str(exc),
                "artifact_paths": _run_artifact_paths(run_id),
            }
        )
        return json.dumps(
            {
                "run_id": run_id,
                "status": "failed",
                "error": str(exc),
                "artifact_paths": _run_artifact_paths(run_id),
            },
            indent=2,
        )
    payload = _graph_result_payload(run_id, thread_id, result, "intake")
    payload["message"] = (
        "Checkpointed LangGraph delivery run started. Use continue_delivery "
        "with action 'continue' to advance the compiled graph."
    )
    return json.dumps(
        payload,
        indent=2,
    )


@mcp.tool(title="Continue Delivery", structured_output=False)
def continue_delivery(
    run_id: str,
    action: str = "continue",
    instruction: str = "",
    timeout: int = 900,
) -> str:
    """Advance the checkpointed LangGraph workflow or revise/approve/reject."""
    run = PENDING_RUNS.get(run_id)
    if not run:
        return json.dumps(
            {
                "run_id": run_id,
                "status": "unknown",
                "error": "No pending run found. Start with plan_delivery first.",
            },
            indent=2,
        )
    if action == "revise":
        if not instruction:
            return json.dumps(
                {"run_id": run_id, "status": run.get("status"), "error": "instruction is required for revise."},
                indent=2,
            )
        from agent.artifact_review import revise_artifacts

        modified = revise_artifacts(run.get("artifact_paths", {}), instruction, timeout)
        _flush_traces()
        return json.dumps(
            {
                "run_id": run_id,
                "status": run.get("status"),
                "modified_files": modified,
                "next_stage": (run.get("next_nodes") or [None])[0],
                "message": "Artifacts revised. Continue, revise again, approve, or reject.",
            },
            indent=2,
        )
    if action in {"approve", "reject"}:
        try:
            result = _invoke_graph_step(
                run_id,
                Command(
                    resume={
                        "approved": action == "approve",
                        "reviewer_note": instruction,
                    }
                ),
                None,
                timeout,
            )
            _flush_traces()
        except Exception as exc:  # noqa: BLE001
            run.update({"status": "failed", "error": str(exc), "artifact_paths": _run_artifact_paths(run_id)})
            return json.dumps(
                {
                    "run_id": run_id,
                    "status": "failed",
                    "error": str(exc),
                    "artifact_paths": run.get("artifact_paths", {}),
                },
                indent=2,
            )
        thread_id = run["thread_id"]
        payload = _graph_result_payload(run_id, thread_id, result, "approval")
        PENDING_RUNS.pop(run_id, None)
        payload["message"] = "Delivery approved." if action == "approve" else "Delivery rejected."
        return json.dumps(payload, indent=2)
    if action != "continue":
        return json.dumps(
            {"run_id": run_id, "status": run.get("status"), "error": "action must be continue, revise, approve, or reject."},
            indent=2,
        )

    next_nodes = _next_nodes(run["thread_id"])
    if not next_nodes:
        return json.dumps(
            {
                "run_id": run_id,
                "status": run.get("status", "completed"),
                "message": "The checkpointed graph has no pending stages.",
                "artifact_paths": run.get("artifact_paths", {}),
            },
            indent=2,
        )
    stage = next_nodes[0]
    try:
        result = _invoke_graph_step(
            run_id,
            {"timeout": timeout},
            None if stage == "approval" else [stage],
            timeout,
        )
        if stage != "approval":
            approval_result = _enter_approval_if_next(run_id, timeout)
            if approval_result is not None:
                result = approval_result
        _flush_traces()
    except Exception as exc:  # noqa: BLE001
        run.update({"status": "failed", "error": str(exc), "artifact_paths": _run_artifact_paths(run_id)})
        return json.dumps(
            {
                "run_id": run_id,
                "status": "failed",
                "stage": stage,
                "error": str(exc),
                "artifact_paths": run.get("artifact_paths", {}),
            },
            indent=2,
        )
    payload = _graph_result_payload(run_id, run["thread_id"], result, stage)
    if payload["status"] == "awaiting_decision" and payload.get("next_stage"):
        message = (
            f"Stage '{stage}' complete. Use continue_delivery with action 'continue' "
            f"for '{payload['next_stage']}', or action 'revise' to change generated artifacts."
        )
    elif payload["status"] == "awaiting_approval":
        message = "Human approval required. Use action 'approve', 'revise', or 'reject'."
    else:
        message = f"Stage '{stage}' complete."
    payload["message"] = message
    return json.dumps(payload, indent=2)


@mcp.tool(title="Review Delivery", structured_output=False)
def review_delivery(run_id: str) -> str:
    """Review artifact paths, audit status, classification, and approval for a run."""
    artifact_paths = _run_artifact_paths(run_id)
    pending = PENDING_RUNS.get(run_id, {})
    return json.dumps(
        {
            "run_id": run_id,
            "status": pending.get("status", "unknown"),
            "current_stage": (pending.get("state") or {}).get("current_stage"),
            "next_stage": (pending.get("next_nodes") or [None])[0],
            "artifact_paths": artifact_paths,
            "classification": _read_json_artifact(run_id, "classification.json"),
            "audit": _read_json_artifact(run_id, "audit.json"),
            "approval": _read_json_artifact(run_id, "approval.json"),
            "modifications": _read_json_artifact(run_id, "modifications.json"),
            "approval_payload": pending.get("approval_payload"),
            "errors": pending.get("errors", []),
            "error": pending.get("error"),
            "pending_approval_in_this_mcp_process": run_id in PENDING_RUNS,
        },
        indent=2,
    )


@mcp.tool(title="Revise Delivery", structured_output=False)
def revise_delivery(
    run_id: str,
    instruction: str,
    timeout: int = 900,
) -> str:
    """Revise generated delivery artifacts using reviewer instructions."""
    from agent.artifact_review import revise_artifacts

    run = PENDING_RUNS.get(run_id)
    if run:
        artifact_paths = run["artifact_paths"]
    else:
        run_dir = Path("artifacts") / "runs" / run_id
        artifact_paths = {path.name: str(path) for path in run_dir.glob("*") if path.is_file()}
    modified = revise_artifacts(artifact_paths, instruction, timeout)
    _flush_traces()
    return json.dumps({"run_id": run_id, "modified_files": modified}, indent=2)


@mcp.tool(title="Approve Delivery", structured_output=False)
def approve_delivery(
    run_id: str,
    approved: bool = True,
    reviewer_note: str = "",
    timeout: int = 900,
) -> str:
    """Approve or reject a pending delivery run created by this MCP server."""
    run = PENDING_RUNS.get(run_id)
    if not run:
        return json.dumps({
            "run_id": run_id,
            "approval_status": "unknown",
            "error": "No pending MCP run found for this run_id. Plan the delivery in this MCP server process first.",
        }, indent=2)
    if run.get("status") != "awaiting_approval":
        return json.dumps(
            {
                "run_id": run_id,
                "approval_status": "not_ready",
                "status": run.get("status"),
                "error": "Delivery is not awaiting approval yet. Use review_delivery again later.",
            },
            indent=2,
        )
    result = _invoke_graph_step(
        run_id,
        Command(
            resume={
                "approved": approved,
                "reviewer_note": reviewer_note,
            }
        ),
        None,
        timeout,
    )
    _flush_traces()
    payload = _graph_result_payload(run_id, run["thread_id"], result, "approval")
    PENDING_RUNS.pop(run_id, None)
    return json.dumps({
        "run_id": payload.get("run_id"),
        "approval_status": payload.get("approval_status"),
        "status": payload.get("status"),
        "next_action": payload.get("next_action"),
        "artifact_paths": payload.get("artifact_paths", {}),
        "errors": payload.get("errors", []),
    }, indent=2)


def main() -> None:
    mcp.run()


if __name__ == "__main__":
    main()
