"""Business logic for MCP delivery tools."""

from __future__ import annotations

import json
import threading
import time
import uuid
from pathlib import Path
from typing import Any

from langgraph.types import Command

from agent.mcp.graph_driver import (
    enter_approval_if_next,
    flush_traces,
    graph_result_payload,
    invoke_graph_step,
    next_nodes,
    read_json_artifact,
    run_artifact_paths,
)
from agent.mcp.runtime import BACKGROUND_JOBS, PENDING_RUNS


def run_delivery_workflow_prompt(request: str) -> str:
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


def normalize_timeout(raw_timeout: Any, default: int = 900) -> int:
    """Normalize timeout input to a positive integer."""
    try:
        timeout = int(raw_timeout)
    except (TypeError, ValueError):
        return default
    return timeout if timeout > 0 else default


def job_record(run_id: str) -> dict[str, Any] | None:
    """Return background job metadata for a run id."""
    return BACKGROUND_JOBS.get(run_id)


def set_run_cancelled(run_id: str, message: str) -> None:
    """Mark a pending run as cancelled."""
    run = PENDING_RUNS.get(run_id)
    if not run:
        return
    run.update(
        {
            "status": "cancelled",
            "error": message,
            "next_nodes": (),
            "approval_payload": None,
        }
    )


def _background_worker(run_id: str, timeout: int) -> None:
    """Continue a run stage-by-stage until approval, completion, failure, or cancellation."""
    job = job_record(run_id)
    if not job:
        return
    cancel_event: threading.Event = job["cancel_event"]
    last_status = "running"
    try:
        while True:
            if cancel_event.is_set():
                set_run_cancelled(run_id, "Cancellation requested by user.")
                last_status = "cancelled"
                break

            payload = continue_delivery_payload(
                run_id=run_id, action="continue", timeout=timeout
            )
            status = str(payload.get("status", "unknown"))
            last_status = status
            if status in {
                "awaiting_approval",
                "completed",
                "failed",
                "unknown",
                "cancelled",
            }:
                break
            if not payload.get("next_stage"):
                break
    except Exception as exc:  # noqa: BLE001
        run = PENDING_RUNS.get(run_id)
        if run:
            run.update(
                {
                    "status": "failed",
                    "error": str(exc),
                    "artifact_paths": run_artifact_paths(run_id),
                }
            )
        last_status = "failed"
    finally:
        latest = PENDING_RUNS.get(run_id, {}).get("status", last_status)
        job["status"] = latest
        job["finished_at"] = time.time()


def draft_delivery_text(input_text: str, timeout: int = 90) -> str:
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
        return (
            response.content
            if isinstance(response.content, str)
            else str(response.content)
        )
    finally:
        flush_traces()


def plan_delivery_payload(
    input_text: str,
    source_type: str = "mcp",
    timeout: int = 900,
) -> dict[str, Any]:
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
        result = invoke_graph_step(
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
        flush_traces()
    except Exception as exc:  # noqa: BLE001
        PENDING_RUNS[run_id].update(
            {
                "status": "failed",
                "error": str(exc),
                "artifact_paths": run_artifact_paths(run_id),
            }
        )
        return {
            "run_id": run_id,
            "status": "failed",
            "error": str(exc),
            "artifact_paths": run_artifact_paths(run_id),
        }

    payload = graph_result_payload(run_id, thread_id, result, "intake")
    payload["message"] = (
        "Checkpointed LangGraph delivery run started. Use continue_delivery "
        "with action 'continue' to advance the compiled graph."
    )
    PENDING_RUNS[run_id]["mode"] = "graph"
    return payload


def start_delivery_async_payload(
    input_text: str,
    source_type: str = "mcp_async",
    timeout: int = 900,
) -> dict[str, Any]:
    """Start delivery and continue it in a background thread until approval or completion."""
    plan_payload = plan_delivery_payload(
        input_text=input_text,
        source_type=source_type,
        timeout=timeout,
    )
    run_id = str(plan_payload.get("run_id", ""))
    if not run_id or plan_payload.get("status") == "failed":
        return plan_payload

    existing = job_record(run_id)
    if existing and existing.get("thread") and existing["thread"].is_alive():
        return {
            **plan_payload,
            "background": {
                "status": "already_running",
                "cancel_requested": bool(existing.get("cancel_requested")),
            },
            "message": "Background job is already running for this run_id.",
        }

    normalized_timeout = normalize_timeout(timeout, default=900)
    cancel_event = threading.Event()
    worker = threading.Thread(
        target=_background_worker,
        args=(run_id, normalized_timeout),
        name=f"delivery-bg-{run_id}",
        daemon=True,
    )
    BACKGROUND_JOBS[run_id] = {
        "run_id": run_id,
        "thread": worker,
        "cancel_event": cancel_event,
        "cancel_requested": False,
        "timeout": normalized_timeout,
        "status": "running",
        "started_at": time.time(),
        "finished_at": None,
    }
    PENDING_RUNS[run_id]["mode"] = "background"
    worker.start()
    status_payload = get_delivery_status_payload(run_id)
    status_payload["message"] = (
        "Background delivery started. Poll with get_delivery_status, use cancel_delivery to stop, "
        "and continue_delivery with approve/revise/reject when status is awaiting_approval."
    )
    return status_payload


def get_delivery_status_payload(run_id: str) -> dict[str, Any]:
    """Return status for sync or async delivery runs, including background metadata."""
    pending = PENDING_RUNS.get(run_id)
    artifacts = run_artifact_paths(run_id)
    job = job_record(run_id)
    if not pending and not artifacts:
        return {
            "run_id": run_id,
            "status": "unknown",
            "error": "No run found for this run_id.",
            "background": None,
        }

    state = (pending or {}).get("state", {})
    stage_nodes = (pending or {}).get("next_nodes") or ()
    thread = job.get("thread") if job else None
    return {
        "run_id": run_id,
        "status": (pending or {}).get("status", "unknown"),
        "current_stage": state.get("current_stage"),
        "next_stage": stage_nodes[0] if stage_nodes else None,
        "approval_status": state.get("approval_status"),
        "next_action": state.get("next_action"),
        "artifact_paths": (pending or {}).get("artifact_paths", {}) or artifacts,
        "errors": (pending or {}).get("errors", []),
        "error": (pending or {}).get("error"),
        "approval_payload": (pending or {}).get("approval_payload"),
        "background": {
            "active": bool(thread and thread.is_alive()),
            "status": job.get("status") if job else None,
            "cancel_requested": bool(job.get("cancel_requested")) if job else False,
            "started_at": job.get("started_at") if job else None,
            "finished_at": job.get("finished_at") if job else None,
        },
    }


def cancel_delivery_payload(run_id: str, wait_seconds: float = 2.0) -> dict[str, Any]:
    """Request cancellation of a background delivery run."""
    run = PENDING_RUNS.get(run_id)
    job = job_record(run_id)
    if not run:
        return {
            "run_id": run_id,
            "status": "unknown",
            "error": "No run found for this run_id.",
        }
    if not job:
        set_run_cancelled(run_id, "Cancelled by user (no active background worker).")
        return {
            "run_id": run_id,
            "status": "cancelled",
            "message": "Run marked as cancelled.",
            "background": None,
        }

    job["cancel_requested"] = True
    cancel_event: threading.Event = job["cancel_event"]
    cancel_event.set()
    thread = job.get("thread")
    if thread and thread.is_alive():
        thread.join(timeout=max(wait_seconds, 0.0))
    if thread and thread.is_alive():
        run.update(
            {
                "status": "cancelling",
                "error": "Cancellation requested; waiting for current stage to finish.",
            }
        )
    else:
        set_run_cancelled(run_id, "Cancellation requested by user.")
        job["status"] = "cancelled"
        job["finished_at"] = time.time()
    return get_delivery_status_payload(run_id)


def continue_delivery_payload(
    run_id: str,
    action: str = "continue",
    instruction: str = "",
    timeout: int = 900,
) -> dict[str, Any]:
    """Advance the checkpointed LangGraph workflow or revise/approve/reject."""
    run = PENDING_RUNS.get(run_id)
    if not run:
        return {
            "run_id": run_id,
            "status": "unknown",
            "error": "No pending run found. Start with plan_delivery first.",
        }
    if run.get("status") in {"cancelled", "cancelling"}:
        return {
            "run_id": run_id,
            "status": run.get("status"),
            "error": run.get("error", "Run is cancelled."),
            "artifact_paths": run.get("artifact_paths", {}),
        }

    if action == "revise":
        if not instruction:
            return {
                "run_id": run_id,
                "status": run.get("status"),
                "error": "instruction is required for revise.",
            }
        from agent.artifact_review import revise_artifacts

        modified = revise_artifacts(run.get("artifact_paths", {}), instruction, timeout)
        flush_traces()
        return {
            "run_id": run_id,
            "status": run.get("status"),
            "modified_files": modified,
            "next_stage": (run.get("next_nodes") or [None])[0],
            "message": "Artifacts revised. Continue, revise again, approve, or reject.",
        }

    if action in {"approve", "reject"}:
        try:
            result = invoke_graph_step(
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
            flush_traces()
        except Exception as exc:  # noqa: BLE001
            run.update(
                {
                    "status": "failed",
                    "error": str(exc),
                    "artifact_paths": run_artifact_paths(run_id),
                }
            )
            return {
                "run_id": run_id,
                "status": "failed",
                "error": str(exc),
                "artifact_paths": run.get("artifact_paths", {}),
            }
        thread_id = run["thread_id"]
        payload = graph_result_payload(run_id, thread_id, result, "approval")
        if (
            payload.get("status") == "completed"
            or payload.get("approval_status") == "rejected"
        ):
            PENDING_RUNS.pop(run_id, None)
        payload["message"] = (
            "Delivery approved." if action == "approve" else "Delivery rejected."
        )
        return payload

    if action != "continue":
        return {
            "run_id": run_id,
            "status": run.get("status"),
            "error": "action must be continue, revise, approve, or reject.",
        }

    stage_nodes = next_nodes(run["thread_id"])
    if not stage_nodes:
        return {
            "run_id": run_id,
            "status": run.get("status", "completed"),
            "message": "The checkpointed graph has no pending stages.",
            "artifact_paths": run.get("artifact_paths", {}),
        }

    stage = stage_nodes[0]
    try:
        result = invoke_graph_step(
            run_id,
            {"timeout": timeout},
            None if stage == "approval" else [stage],
            timeout,
        )
        if stage != "approval":
            approval_result = enter_approval_if_next(run_id, timeout)
            if approval_result is not None:
                result = approval_result
        flush_traces()
    except Exception as exc:  # noqa: BLE001
        run.update(
            {
                "status": "failed",
                "error": str(exc),
                "artifact_paths": run_artifact_paths(run_id),
            }
        )
        return {
            "run_id": run_id,
            "status": "failed",
            "stage": stage,
            "error": str(exc),
            "artifact_paths": run.get("artifact_paths", {}),
        }

    payload = graph_result_payload(run_id, run["thread_id"], result, stage)
    if payload["status"] == "awaiting_decision" and payload.get("next_stage"):
        message = (
            f"Stage '{stage}' complete. Use continue_delivery with action 'continue' "
            f"for '{payload['next_stage']}', or action 'revise' to change generated artifacts."
        )
    elif payload["status"] == "awaiting_approval":
        message = (
            "Human approval required. Use action 'approve', 'revise', or 'reject'."
        )
    else:
        message = f"Stage '{stage}' complete."
    payload["message"] = message
    return payload


def review_delivery_payload(run_id: str) -> dict[str, Any]:
    """Review artifact paths, audit status, classification, and approval for a run."""
    artifact_paths = run_artifact_paths(run_id)
    pending = PENDING_RUNS.get(run_id, {})
    return {
        "run_id": run_id,
        "status": pending.get("status", "unknown"),
        "current_stage": (pending.get("state") or {}).get("current_stage"),
        "next_stage": (pending.get("next_nodes") or [None])[0],
        "artifact_paths": artifact_paths,
        "classification": read_json_artifact(run_id, "classification.json"),
        "audit": read_json_artifact(run_id, "audit.json"),
        "approval": read_json_artifact(run_id, "approval.json"),
        "modifications": read_json_artifact(run_id, "modifications.json"),
        "approval_payload": pending.get("approval_payload"),
        "errors": pending.get("errors", []),
        "error": pending.get("error"),
        "pending_approval_in_this_mcp_process": run_id in PENDING_RUNS,
    }


def revise_delivery_payload(
    run_id: str,
    instruction: str,
    timeout: int = 900,
) -> dict[str, Any]:
    """Revise generated delivery artifacts using reviewer instructions."""
    from agent.artifact_review import revise_artifacts

    run = PENDING_RUNS.get(run_id)
    if run:
        artifact_paths = run["artifact_paths"]
    else:
        run_dir = Path("artifacts") / "runs" / run_id
        artifact_paths = {
            path.name: str(path) for path in run_dir.glob("*") if path.is_file()
        }
    modified = revise_artifacts(artifact_paths, instruction, timeout)
    flush_traces()
    return {"run_id": run_id, "modified_files": modified}


def approve_delivery_payload(
    run_id: str,
    approved: bool = True,
    reviewer_note: str = "",
    timeout: int = 900,
) -> dict[str, Any]:
    """Approve or reject a pending delivery run created by this MCP server."""
    run = PENDING_RUNS.get(run_id)
    if not run:
        return {
            "run_id": run_id,
            "approval_status": "unknown",
            "error": "No pending MCP run found for this run_id. Plan the delivery in this MCP server process first.",
        }
    if run.get("status") != "awaiting_approval":
        return {
            "run_id": run_id,
            "approval_status": "not_ready",
            "status": run.get("status"),
            "error": "Delivery is not awaiting approval yet. Use review_delivery again later.",
        }

    result = invoke_graph_step(
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
    flush_traces()
    payload = graph_result_payload(run_id, run["thread_id"], result, "approval")
    if (
        payload.get("status") == "completed"
        or payload.get("approval_status") == "rejected"
    ):
        PENDING_RUNS.pop(run_id, None)
    return {
        "run_id": payload.get("run_id"),
        "approval_status": payload.get("approval_status"),
        "status": payload.get("status"),
        "next_action": payload.get("next_action"),
        "artifact_paths": payload.get("artifact_paths", {}),
        "errors": payload.get("errors", []),
    }
