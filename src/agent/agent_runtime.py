"""Runtime representation for deterministic delivery agents."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Iterable

from agent.agent_profiles import load_agent_profile, resolve_agent_profile_path
from agent.tools.catalog import ToolSpec, forbidden_tools_for_mvp, tools_for_agent


@dataclass(frozen=True)
class ArtifactAgent:
    name: str
    profile_filename: str
    profile: str
    allowed_tools: list[ToolSpec]
    forbidden_tools: list[ToolSpec]

    def prompt_context(self) -> str:
        allowed = "\n".join(tool.prompt_line() for tool in self.allowed_tools)
        forbidden = "\n".join(tool.prompt_line() for tool in self.forbidden_tools)
        return (
            f"Agent name: {self.name}\n"
            f"Agent profile file: {self.profile_filename}\n\n"
            f"Agent profile:\n{self.profile}\n\n"
            f"Allowed tools for this agent:\n{allowed}\n\n"
            f"Forbidden MVP tools:\n{forbidden}\n\n"
            "Tool-use rule: you may reason from allowed tool outputs already provided "
            "by the orchestrator, but you must not claim to have executed tools directly."
        )


def _agent_name(profile_filename: str) -> str:
    return Path(profile_filename).stem.replace("_", " ").title().replace(" ", "")


def build_artifact_agent(
    profile_filename: str,
    platform_candidates: Iterable[str] | None = None,
) -> ArtifactAgent:
    resolved_profile = resolve_agent_profile_path(
        profile_filename, platform_candidates=platform_candidates
    )
    return ArtifactAgent(
        name=_agent_name(resolved_profile),
        profile_filename=resolved_profile,
        profile=load_agent_profile(resolved_profile),
        allowed_tools=tools_for_agent(resolved_profile),
        forbidden_tools=forbidden_tools_for_mvp(),
    )
