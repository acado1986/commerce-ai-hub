"""Agent profile loading for role-based artifact generation."""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path


def repo_root() -> Path:
    return Path(__file__).resolve().parents[2]


@lru_cache(maxsize=32)
def load_agent_profile(filename: str) -> str:
    """Load a markdown agent definition from the repository agents directory."""
    path = repo_root() / "agents" / filename
    if not path.exists():
        raise FileNotFoundError(f"Agent profile not found: {path}")
    return path.read_text(encoding="utf-8").strip()
