"""Business logic for chat workflow composition."""

from __future__ import annotations

import uuid
from pathlib import Path
from typing import Any

from langchain_core.messages import AIMessage, BaseMessage
from langgraph.graph import END, START, MessagesState, StateGraph

from agent.nodes.chat_approval import chat_approval_node
from agent.observability import traced_graph
from agent.orchestrator.graph import build_workflow_builder
from agent.orchestrator.router import route_after_approval
from agent.orchestrator.state import (
    DeliveryHubState,
    PlatformType,
    RequestType,
    RiskLevel,
)

APPROVAL_HELP_TEXT = (
    "Awaiting approval. Reply with `approve`, `reject`, "
    "or `modify: <changes>`."
)


class WorkflowChatState(MessagesState, total=False):
    """Chat state extending delivery workflow state with message history."""

    run_id: str
    source_type: str
    source_id: str | None
    input_text: str
    request_type: RequestType
    platforms: list[PlatformType]
    confidence_score: float
    risk_level: RiskLevel
    current_stage: str
    approval_status: str
    artifact_paths: dict[str, str]
    errors: list[dict[str, Any]]
    audit_log: list[dict[str, Any]]
    llm_usage: list[dict[str, Any]]
    llm_usage_totals: dict[str, int | None]
    next_action: str
    classification_rationale: str
    mapped_request_type: str
    solution_profile: dict[str, Any]
    approval_stage: str | None
    revision_stage: str | None
    revision_instruction: str | None
    approval_request: dict[str, Any] | None
    approval_decision: dict[str, Any] | None
    chat_reply: str


def last_user_text(state: WorkflowChatState) -> str:
    """Extract the latest user-authored message text from chat history."""
    messages = state.get("messages", [])
    if not messages:
        return ""

    for message in reversed(messages):
        if is_user_message(message):
            return message_text(message.content)

    return ""


def is_user_message(message: BaseMessage) -> bool:
    """Return true when message was authored by the user."""
    message_type = getattr(message, "type", "")
    if message_type == "human":
        return True
    return message_type == "chat" and getattr(message, "role", "") == "user"


def message_text(content: Any) -> str:
    """Normalize mixed message content payloads into plain text."""
    if isinstance(content, str):
        return content.strip()
    if isinstance(content, list):
        parts: list[str] = []
        for item in content:
            if isinstance(item, str):
                text = item.strip()
            elif isinstance(item, dict):
                if item.get("type") == "text":
                    text = str(item.get("text", "")).strip()
                else:
                    text = ""
            else:
                text = str(item).strip()
            if text:
                parts.append(text)
        return "\n".join(parts).strip()
    if isinstance(content, dict):
        return str(content.get("text", "")).strip()
    return str(content).strip()


def format_interrupt(payload: dict[str, Any] | None) -> str:
    """Format approval instructions for chat response."""
    payload = payload or {}
    stage = payload.get("approval_stage", "unknown")
    artifacts = payload.get("artifact_paths", {})
    lines = [
        f"Approval required for stage: {stage}",
        "Reply with one of:",
        "- approve",
        "- reject",
        "- modify: <what to change>",
    ]
    artifact_name, artifact_text = review_markdown(payload)
    if artifact_name and artifact_text:
        lines.extend(
            [
                "",
                f"Review `{artifact_name}`:",
                "```markdown",
                artifact_text,
                "```",
            ]
        )
    if artifacts:
        lines.append("")
        lines.append("Artifacts:")
        for name, path in artifacts.items():
            lines.append(f"- {name}: {path}")
    return "\n".join(lines)


def review_markdown(payload: dict[str, Any]) -> tuple[str, str]:
    """Pick a markdown artifact for inline review, preferring current stage."""
    stage = str(payload.get("approval_stage", "")).strip()
    artifacts = payload.get("artifact_paths", {})
    preferred_names = [f"{stage}.md"] if stage else []

    for name in preferred_names:
        path = artifacts.get(name)
        if path:
            text = read_markdown_artifact(path)
            if text:
                return name, text

    for name, path in artifacts.items():
        if not name.endswith(".md"):
            continue
        text = read_markdown_artifact(path)
        if text:
            return name, text
    return "", ""


def read_markdown_artifact(path: str) -> str:
    """Read a markdown artifact body for chat display."""
    try:
        return Path(path).read_text(encoding="utf-8").strip()
    except OSError:
        return ""


def format_completion(result: dict[str, Any]) -> str:
    """Format completion summary for chat response."""
    artifacts = result.get("artifact_paths", {})
    lines = ["Workflow completed."]
    if artifacts:
        lines.append("Artifacts:")
        for name, path in artifacts.items():
            lines.append(f"- {name}: {path}")
    totals = result.get("llm_usage_totals")
    if totals:
        lines.append(
            "Token totals: "
            f"input={totals.get('input_tokens')}, "
            f"output={totals.get('output_tokens')}, "
            f"total={totals.get('total_tokens')}"
        )
    return "\n".join(lines)


def parse_approval_command(text: str) -> tuple[str, str]:
    """Parse approve/reject/modify commands."""
    normalized = text.strip()
    lower = normalized.lower()
    if lower == "approve":
        return "approve", ""
    if lower == "reject":
        return "reject", ""
    if lower.startswith("modify:"):
        return "modify", normalized.split(":", 1)[1].strip()
    if lower.startswith("modify "):
        return "modify", normalized.split(" ", 1)[1].strip()
    return "invalid", ""


def next_run_id(state: WorkflowChatState) -> str:
    """Generate chat run id if missing."""
    return state.get("run_id") or f"chat-{uuid.uuid4()}"


def approval_decision_from_text(text: str) -> tuple[str, dict[str, Any] | None]:
    """Map user text into approval decision payload."""
    action, instruction = parse_approval_command(text)
    if action == "invalid":
        return APPROVAL_HELP_TEXT, None
    if action == "modify":
        return "", {"action": "modify", "instruction": instruction}
    return "", {"action": action}


def workflow_entry_route(state: DeliveryHubState) -> str:
    """Route chat turn to approval or intake stage."""
    return "approval" if is_approval_turn(state) else "intake"


def route_after_chat_approval(state: DeliveryHubState) -> str:
    """After approval node, either end chat turn or continue workflow."""
    if state.get("next_action") == "awaiting_approval":
        return "end"
    return route_after_approval(state)


def is_approval_turn(state: WorkflowChatState) -> bool:
    """Return true when current turn is for an approval decision."""
    next_action = str(state.get("next_action", "")).strip()
    if next_action in {"awaiting_approval", "human_review"}:
        return True
    if state.get("approval_status") == "pending":
        return True
    return bool(state.get("approval_request"))


workflow_builder = build_workflow_builder(
    approval_action=chat_approval_node,
    entry_route=workflow_entry_route,
    after_approval_route=route_after_chat_approval,
)
workflow_graph = workflow_builder.compile(
    name="AI Delivery Hub Workflow (Chat Subgraph)"
)


def prepare_turn_node(state: WorkflowChatState) -> WorkflowChatState:
    """Prepare workflow input or approval decision for the current chat turn."""
    text = last_user_text(state)
    if is_approval_turn(state):
        reply, approval_decision = approval_decision_from_text(text)
        return {
            "chat_reply": reply,
            "approval_decision": approval_decision,
        }

    return {
        "chat_reply": "",
        "approval_decision": None,
        "run_id": next_run_id(state),
        "source_type": "studio_chat",
        "source_id": None,
        "input_text": text,
    }


def route_after_prepare(state: WorkflowChatState) -> str:
    """Route to direct response when validation message is ready."""
    return "respond" if state.get("chat_reply") else "workflow"


def respond_node(state: WorkflowChatState) -> WorkflowChatState:
    """Produce assistant chat response from workflow state."""
    reply = state.get("chat_reply")
    if not reply:
        if is_approval_turn(state):
            reply = format_interrupt(state.get("approval_request"))
        else:
            reply = format_completion(state)
    return {
        "chat_reply": "",
        "messages": [AIMessage(content=reply)],
    }


builder = StateGraph(WorkflowChatState)
builder.add_node("prepare_turn", prepare_turn_node)
builder.add_node("workflow", workflow_graph, input_schema=DeliveryHubState)
builder.add_node("respond", respond_node)
builder.add_edge(START, "prepare_turn")
builder.add_conditional_edges(
    "prepare_turn",
    route_after_prepare,
    {"workflow": "workflow", "respond": "respond"},
)
builder.add_edge("workflow", "respond")
builder.add_edge("respond", END)

chat_graph = traced_graph(
    builder.compile(name="AI Delivery Hub Workflow (Chat)"),
    trace_name="ai-delivery-hub-chat",
)
