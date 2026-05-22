"""MCP server for AI Delivery Hub."""

from __future__ import annotations

import json
import warnings

from mcp.server.fastmcp import FastMCP

from agent.mcp.runtime import BACKGROUND_JOBS, PENDING_RUNS
from agent.mcp.service import (
    approve_delivery_payload,
    cancel_delivery_payload,
    continue_delivery_payload,
    draft_delivery_text,
    get_delivery_status_payload,
    plan_delivery_payload,
    review_delivery_payload,
    revise_delivery_payload,
    run_delivery_workflow_prompt,
    start_delivery_async_payload,
)

warnings.filterwarnings("ignore", message=".*allowed_objects.*")

mcp = FastMCP("ai-delivery-hub")


def _json(payload: dict) -> str:
    return json.dumps(payload, indent=2)


@mcp.prompt(
    name="run_delivery_workflow",
    title="Run Delivery Workflow",
    description="Instruction prompt for running the full delivery workflow through short MCP tool calls.",
)
def run_delivery_workflow(request: str) -> str:
    """Return instructions for a one-chat delivery workflow."""
    return run_delivery_workflow_prompt(request)


@mcp.tool(title="Draft Delivery", structured_output=False)
def draft_delivery(input_text: str, timeout: int = 90) -> str:
    """Create a fast one-call delivery brief without running the full graph."""
    return draft_delivery_text(input_text=input_text, timeout=timeout)


@mcp.tool(title="Plan Delivery", structured_output=False)
def plan_delivery(
    input_text: str,
    source_type: str = "mcp",
    timeout: int = 900,
) -> str:
    """Start a checkpointed LangGraph delivery run and pause after intake."""
    return _json(
        plan_delivery_payload(
            input_text=input_text,
            source_type=source_type,
            timeout=timeout,
        )
    )


@mcp.tool(title="Start Delivery Async", structured_output=False)
def start_delivery_async(
    input_text: str,
    source_type: str = "mcp_async",
    timeout: int = 900,
) -> str:
    """Start delivery and continue it in a background thread until approval or completion."""
    return _json(
        start_delivery_async_payload(
            input_text=input_text,
            source_type=source_type,
            timeout=timeout,
        )
    )


@mcp.tool(title="Get Delivery Status", structured_output=False)
def get_delivery_status(run_id: str) -> str:
    """Return status for sync or async delivery runs, including background metadata."""
    return _json(get_delivery_status_payload(run_id=run_id))


@mcp.tool(title="Cancel Delivery", structured_output=False)
def cancel_delivery(
    run_id: str,
    wait_seconds: float = 2.0,
) -> str:
    """Request cancellation of a background delivery run."""
    return _json(cancel_delivery_payload(run_id=run_id, wait_seconds=wait_seconds))


@mcp.tool(title="Continue Delivery", structured_output=False)
def continue_delivery(
    run_id: str,
    action: str = "continue",
    instruction: str = "",
    timeout: int = 900,
) -> str:
    """Advance the checkpointed LangGraph workflow or revise/approve/reject."""
    return _json(
        continue_delivery_payload(
            run_id=run_id,
            action=action,
            instruction=instruction,
            timeout=timeout,
        )
    )


@mcp.tool(title="Review Delivery", structured_output=False)
def review_delivery(run_id: str) -> str:
    """Review artifact paths, audit status, classification, and approval for a run."""
    return _json(review_delivery_payload(run_id=run_id))


@mcp.tool(title="Revise Delivery", structured_output=False)
def revise_delivery(
    run_id: str,
    instruction: str,
    timeout: int = 900,
) -> str:
    """Revise generated delivery artifacts using reviewer instructions."""
    return _json(
        revise_delivery_payload(
            run_id=run_id,
            instruction=instruction,
            timeout=timeout,
        )
    )


@mcp.tool(title="Approve Delivery", structured_output=False)
def approve_delivery(
    run_id: str,
    approved: bool = True,
    reviewer_note: str = "",
    timeout: int = 900,
) -> str:
    """Approve or reject a pending delivery run created by this MCP server."""
    return _json(
        approve_delivery_payload(
            run_id=run_id,
            approved=approved,
            reviewer_note=reviewer_note,
            timeout=timeout,
        )
    )


def main() -> None:
    mcp.run()


if __name__ == "__main__":
    main()
