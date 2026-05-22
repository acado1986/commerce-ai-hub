"""Compatibility entrypoint for the MCP server."""

from agent.mcp.runtime import BACKGROUND_JOBS, PENDING_RUNS
from agent.mcp.server import (
    approve_delivery,
    cancel_delivery,
    continue_delivery,
    draft_delivery,
    get_delivery_status,
    main,
    mcp,
    plan_delivery,
    revise_delivery,
    review_delivery,
    run_delivery_workflow,
    start_delivery_async,
)

__all__ = [
    "mcp",
    "main",
    "PENDING_RUNS",
    "BACKGROUND_JOBS",
    "run_delivery_workflow",
    "draft_delivery",
    "plan_delivery",
    "start_delivery_async",
    "get_delivery_status",
    "cancel_delivery",
    "continue_delivery",
    "review_delivery",
    "revise_delivery",
    "approve_delivery",
]


if __name__ == "__main__":
    main()
