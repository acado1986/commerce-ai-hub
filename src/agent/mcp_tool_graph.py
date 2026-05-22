"""LangGraph MCP tool entrypoint with explicit schemas.

This graph is exposed by LangGraph Server at `/mcp` and delegates to the
existing delivery workflow actions.
"""

from __future__ import annotations

import json
from typing import Any, Literal

from langgraph.graph import END, START, StateGraph
from typing_extensions import TypedDict

from agent.mcp_server import (
    approve_delivery,
    continue_delivery,
    plan_delivery,
    review_delivery,
    revise_delivery,
)
from agent.observability import traced_graph


ActionType = Literal["plan", "continue", "review", "revise", "approve"]
ContinueActionType = Literal["continue", "revise", "approve", "reject"]


class MCPToolInput(TypedDict, total=False):
    action: ActionType
    input_text: str
    run_id: str
    continue_action: ContinueActionType
    instruction: str
    approved: bool
    reviewer_note: str
    source_type: str
    timeout: int


class MCPToolOutput(TypedDict, total=False):
    run_id: str
    status: str
    current_stage: str | None
    completed_stage: str | None
    next_stage: str | None
    approval_status: str | None
    next_action: str | None
    artifact_dir: str | None
    artifact_paths: dict[str, str]
    errors: list[dict]
    approval_payload: dict | None
    message: str | None
    error: str | None
    modified_files: list[str]
    approval_request: dict | None
    approval_decision: dict | None


class MCPToolState(MCPToolInput, MCPToolOutput, total=False):
    pass


ALLOWED_ACTIONS: set[str] = {"plan", "continue", "review", "revise", "approve"}
ALLOWED_CONTINUE_ACTIONS: set[str] = {"continue", "revise", "approve", "reject"}
OUTPUT_FIELDS: set[str] = {
    "run_id",
    "status",
    "current_stage",
    "completed_stage",
    "next_stage",
    "approval_status",
    "next_action",
    "artifact_dir",
    "artifact_paths",
    "errors",
    "approval_payload",
    "message",
    "error",
    "modified_files",
    "approval_request",
    "approval_decision",
}


def _parse_payload(raw: str) -> dict[str, Any]:
    try:
        payload = json.loads(raw)
        if isinstance(payload, dict):
            return payload
    except json.JSONDecodeError:
        pass
    return {"status": "failed", "error": "Invalid JSON payload returned by delegated action."}


def _error(message: str) -> MCPToolState:
    return {"status": "failed", "error": message}


def _normalize_timeout(raw_timeout: Any, default: int = 900) -> int:
    try:
        timeout = int(raw_timeout)
    except (TypeError, ValueError):
        return default
    return timeout if timeout > 0 else default


def _normalize_output(payload: dict[str, Any]) -> MCPToolState:
    return {key: value for key, value in payload.items() if key in OUTPUT_FIELDS}


def delivery_mcp_action_node(state: MCPToolState) -> MCPToolState:
    action = str(state.get("action", "")).strip()
    if action not in ALLOWED_ACTIONS:
        return _error("action must be one of: plan, continue, review, revise, approve.")

    timeout = _normalize_timeout(state.get("timeout"), default=900)

    if action == "plan":
        input_text = state.get("input_text", "").strip()
        if not input_text:
            return _error("input_text is required when action='plan'.")
        return _normalize_output(
            _parse_payload(
            plan_delivery(
                input_text=input_text,
                source_type=state.get("source_type", "mcp"),
                timeout=timeout,
            )
        )
        )

    run_id = state.get("run_id", "").strip()
    if not run_id:
        return _error("run_id is required for this action.")

    if action == "continue":
        continue_action = str(state.get("continue_action", "continue")).strip()
        if continue_action not in ALLOWED_CONTINUE_ACTIONS:
            return _error("continue_action must be one of: continue, revise, approve, reject.")
        return _normalize_output(
            _parse_payload(
            continue_delivery(
                run_id=run_id,
                action=continue_action,
                instruction=state.get("instruction", ""),
                timeout=timeout,
            )
        )
        )

    if action == "review":
        return _normalize_output(_parse_payload(review_delivery(run_id=run_id)))

    if action == "revise":
        instruction = state.get("instruction", "").strip()
        if not instruction:
            return _error("instruction is required when action='revise'.")
        return _normalize_output(
            _parse_payload(
            revise_delivery(
                run_id=run_id,
                instruction=instruction,
                timeout=timeout,
            )
        )
        )

    if action == "approve":
        return _normalize_output(
            _parse_payload(
            approve_delivery(
                run_id=run_id,
                approved=bool(state.get("approved", True)),
                reviewer_note=state.get("reviewer_note", ""),
                timeout=timeout,
            )
        )
        )


builder = StateGraph(
    MCPToolState,
    input_schema=MCPToolInput,
    output_schema=MCPToolOutput,
)
builder.add_node("delivery_mcp_action", delivery_mcp_action_node)
builder.add_edge(START, "delivery_mcp_action")
builder.add_edge("delivery_mcp_action", END)

delivery_mcp_graph = traced_graph(
    builder.compile(name="AI Delivery Hub MCP Tool"),
    trace_name="ai-delivery-hub-mcp",
)
