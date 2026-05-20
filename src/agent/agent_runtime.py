"""Runtime representation for deterministic delivery agents."""

from __future__ import annotations

from dataclasses import dataclass

from agent.agent_profiles import load_agent_profile
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
    return profile_filename.removesuffix(".md").replace("_", " ").title().replace(" ", "")


def build_artifact_agent(profile_filename: str) -> ArtifactAgent:
    return ArtifactAgent(
        name=_agent_name(profile_filename),
        profile_filename=profile_filename,
        profile=load_agent_profile(profile_filename),
        allowed_tools=tools_for_agent(profile_filename),
        forbidden_tools=forbidden_tools_for_mvp(),
    )
