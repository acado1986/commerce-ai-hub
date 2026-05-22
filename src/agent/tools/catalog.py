"""Scoped tool definitions for role-based delivery agents."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class ToolSpec:
    name: str
    description: str
    side_effect: bool = False
    approval_required: bool = False

    def prompt_line(self) -> str:
        flags: list[str] = []
        if self.side_effect:
            flags.append("side-effectful")
        if self.approval_required:
            flags.append("approval required")
        suffix = f" ({', '.join(flags)})" if flags else ""
        return f"- {self.name}: {self.description}{suffix}"


TOOL_CATALOG: dict[str, ToolSpec] = {
    "read_input_artifact": ToolSpec(
        name="read_input_artifact",
        description="Read the original request and intake artifacts for the current run.",
    ),
    "read_prior_artifacts": ToolSpec(
        name="read_prior_artifacts",
        description="Read artifacts produced by earlier workflow stages.",
    ),
    "read_agent_profile": ToolSpec(
        name="read_agent_profile",
        description="Use the assigned role profile, SOP, quality checklist, and output contract.",
    ),
    "read_adobe_knowledge": ToolSpec(
        name="read_adobe_knowledge",
        description="Consult local Adobe Commerce and Adobe App Builder knowledge notes.",
    ),
    "generate_markdown_artifact": ToolSpec(
        name="generate_markdown_artifact",
        description="Generate the requested markdown artifact for this deterministic stage.",
    ),
    "write_run_artifact": ToolSpec(
        name="write_run_artifact",
        description="Persist the generated artifact inside artifacts/runs/<run_id>/.",
        side_effect=True,
    ),
    "record_audit_event": ToolSpec(
        name="record_audit_event",
        description="Record stage completion, errors, and model usage in the run audit log.",
        side_effect=True,
    ),
    "request_human_approval": ToolSpec(
        name="request_human_approval",
        description="Stop the workflow and request human approval before gated actions.",
        side_effect=True,
        approval_required=True,
    ),
    "modify_source_code": ToolSpec(
        name="modify_source_code",
        description="Modify application source code.",
        side_effect=True,
        approval_required=True,
    ),
    "create_pull_request": ToolSpec(
        name="create_pull_request",
        description="Create a pull request in a source control system.",
        side_effect=True,
        approval_required=True,
    ),
    "deploy": ToolSpec(
        name="deploy",
        description="Deploy code or configuration to an environment.",
        side_effect=True,
        approval_required=True,
    ),
}

BASE_TOOLS = [
    "read_input_artifact",
    "read_agent_profile",
    "generate_markdown_artifact",
    "write_run_artifact",
    "record_audit_event",
]

AGENT_TOOL_ALLOWLIST: dict[str, list[str]] = {
    "business_analyst_agent.md": [
        *BASE_TOOLS,
        "read_prior_artifacts",
    ],
    "solution_architect_agent.md": [
        *BASE_TOOLS,
        "read_prior_artifacts",
        "read_adobe_knowledge",
    ],
    "workflow_planner_agent.md": [
        *BASE_TOOLS,
        "read_prior_artifacts",
        "read_adobe_knowledge",
    ],
    "qa_agent.md": [
        *BASE_TOOLS,
        "read_prior_artifacts",
        "read_adobe_knowledge",
    ],
    "documentation_agent.md": [
        *BASE_TOOLS,
        "read_prior_artifacts",
    ],
}

FORBIDDEN_MVP_TOOLS = [
    "modify_source_code",
    "create_pull_request",
    "deploy",
]


def tools_for_agent(profile_filename: str) -> list[ToolSpec]:
    names = AGENT_TOOL_ALLOWLIST.get(profile_filename)
    if names is None:
        names = AGENT_TOOL_ALLOWLIST.get(Path(profile_filename).name, BASE_TOOLS)
    return [TOOL_CATALOG[name] for name in names]


def forbidden_tools_for_mvp() -> list[ToolSpec]:
    return [TOOL_CATALOG[name] for name in FORBIDDEN_MVP_TOOLS]
