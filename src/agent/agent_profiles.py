"""Agent profile loading for role-based artifact generation."""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path
from typing import Iterable


def repo_root() -> Path:
    return Path(__file__).resolve().parents[2]


@lru_cache(maxsize=32)
def load_agent_profile(filename: str) -> str:
    """Load a markdown agent definition from the repository agents directory."""
    path = repo_root() / "agents" / filename
    if not path.exists():
        raise FileNotFoundError(f"Agent profile not found: {path}")
    return path.read_text(encoding="utf-8").strip()


def resolve_agent_profile_path(
    filename: str,
    platform_candidates: Iterable[str] | None = None,
) -> str:
    """Resolve profile path with optional platform override fallback."""
    profile_path = Path(filename)
    if profile_path.parts and profile_path.parts[0] == "platforms":
        return filename

    agents_root = repo_root() / "agents"
    base_name = profile_path.name
    for platform in platform_candidates or ():
        normalized = str(platform).strip()
        if not normalized:
            continue
        candidate = Path("platforms") / normalized / base_name
        if (agents_root / candidate).exists():
            return str(candidate)
    return filename
