"""Shared generation helpers."""

from __future__ import annotations

from pathlib import Path

from langchain_core.runnables import RunnableConfig

from agent.agent_runtime import build_artifact_agent
from agent.llm import (
    deployment_for_artifact,
    get_model,
    invoke_model,
    model_name_for_deployment,
    response_content,
    response_usage,
)
from agent.nodes.common import write_text_artifact
from agent.observability import with_stage_trace_config
from agent.orchestrator.audit import append_audit_event, append_llm_usage
from agent.orchestrator.state import DeliveryHubState

DEFAULT_AGENT_BY_ARTIFACT = {
    "requirements.md": "business_analyst_agent.md",
    "architecture.md": "solution_architect_agent.md",
    "implementation-plan.md": "workflow_planner_agent.md",
    "review-checklist.md": "workflow_planner_agent.md",
    "qa-plan.md": "qa_agent.md",
    "ticket-comment.md": "documentation_agent.md",
}


def _artifact_context(state: DeliveryHubState, names: list[str]) -> str:
    blocks: list[str] = []
    artifact_paths = state.get("artifact_paths", {})
    for name in names:
        raw_path = artifact_paths.get(name)
        if not raw_path:
            continue
        path = Path(raw_path)
        if not path.exists():
            continue
        blocks.append(f"## {name}\n{path.read_text(encoding='utf-8').strip()}")
    return "\n\n".join(blocks)


def generate_markdown(
    state: DeliveryHubState,
    stage: str,
    artifact_name: str,
    instruction: str,
    agent_profile: str | None = None,
    context_artifacts: list[str] | None = None,
    config: RunnableConfig | None = None,
) -> DeliveryHubState:
    errors = list(state.get("errors", []))
    artifacts = dict(state.get("artifact_paths", {}))
    try:
        deployment = deployment_for_artifact(artifact_name, state.get("risk_level"))
        model_name = model_name_for_deployment(deployment)
        model = get_model(deployment=deployment)
        profile_name = agent_profile or DEFAULT_AGENT_BY_ARTIFACT.get(artifact_name)
        artifact_agent = build_artifact_agent(profile_name) if profile_name else None
        handoff_context = _artifact_context(state, context_artifacts or [])
        print(f"[llm] generate {artifact_name}", flush=True)
        revision_note = ""
        if state.get("revision_stage") == stage and state.get("revision_instruction"):
            revision_note = (
                "\n\nRevision requested by reviewer:\n"
                f"{state.get('revision_instruction')}\n"
                "Address this feedback directly while preserving the document's scope."
            )

        prompt = (
            "You are a specialized delivery agent inside a deterministic LangGraph workflow.\n"
            "The orchestrator controls stage order, side effects, approvals, and auditability.\n"
            "You must communicate through the requested artifact only, not open-ended chat.\n\n"
            f"{artifact_agent.prompt_context() if artifact_agent else 'Agent profile: <none>'}\n\n"
            "Workflow context:\n"
            f"Stage: {stage}\n"
            f"Target artifact: {artifact_name}\n"
            f"Request type: {state.get('request_type')}\n"
            f"Mapped workflow: {state.get('mapped_request_type')}\n"
            f"Platforms: {state.get('platforms', [])}\n"
            f"Input:\n{state.get('input_text', '')}\n\n"
            f"Prior artifact handoff context:\n{handoff_context or '<none>'}\n\n"
            f"Instruction:\n{instruction}{revision_note}\n"
            "Return markdown only. Do not propose code execution, pull requests, merges, "
            "deployments, ticket closure, or side-effectful actions."
        )
        response = invoke_model(
            model,
            prompt,
            with_stage_trace_config(
                config,
                stage=stage,
                artifact=artifact_name,
                model=model_name,
            ),
        )
        content = response_content(response)
        usage = response_usage(response, requested_model=model_name)
    except Exception as exc:  # noqa: BLE001
        errors.append({"stage": stage, "error": str(exc)})
        return {
            **state,
            "current_stage": stage,
            "approval_status": "blocked",
            "next_action": "human_review",
            "errors": errors,
            "audit_log": append_audit_event(state, stage, "failed", {"error": str(exc)}),
        }

    artifacts.update(write_text_artifact(state, artifact_name, content))
    llm_usage = append_llm_usage(state, stage, artifact_name, usage)
    agent_details = (
        {
            "name": artifact_agent.name,
            "profile": artifact_agent.profile_filename,
            "allowed_tools": [tool.name for tool in artifact_agent.allowed_tools],
        }
        if artifact_agent
        else None
    )
    return {
        **state,
        "current_stage": stage,
        "approval_stage": stage,
        "revision_stage": None,
        "revision_instruction": None,
        "approval_status": "pending",
        "next_action": "human_review",
        "artifact_paths": artifacts,
        "errors": errors,
        "llm_usage": llm_usage,
        "audit_log": append_audit_event(
            state,
            stage,
            "completed",
            {"artifact": artifact_name, "agent": agent_details, "llm_usage": usage},
        ),
    }
