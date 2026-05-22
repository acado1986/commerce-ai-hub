"""Shared in-memory runtime state for MCP delivery runs."""

from __future__ import annotations

from typing import Any

PENDING_RUNS: dict[str, dict[str, Any]] = {}
BACKGROUND_JOBS: dict[str, dict[str, Any]] = {}
