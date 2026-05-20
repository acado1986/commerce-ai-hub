"""Audit helpers for run events."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from agent.orchestrator.state import DeliveryHubState


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def append_audit_event(
    state: DeliveryHubState,
    stage: str,
    event: str,
    details: dict[str, Any] | None = None,
) -> list[dict[str, Any]]:
    entry = {
        "ts": utc_now_iso(),
        "stage": stage,
        "event": event,
        "details": details or {},
    }
    current = list(state.get("audit_log", []))
    current.append(entry)
    return current


def append_llm_usage(
    state: DeliveryHubState,
    stage: str,
    artifact: str | None,
    usage: dict[str, Any],
) -> list[dict[str, Any]]:
    current = list(state.get("llm_usage", []))
    current.append(
        {
            "ts": utc_now_iso(),
            "stage": stage,
            "artifact": artifact,
            **usage,
        }
    )
    return current


def summarize_llm_usage(entries: list[dict[str, Any]]) -> dict[str, int | None]:
    totals: dict[str, int] = {
        "input_tokens": 0,
        "output_tokens": 0,
        "total_tokens": 0,
    }
    seen = {key: False for key in totals}
    for entry in entries:
        for key in totals:
            value = entry.get(key)
            if value is not None:
                totals[key] += int(value)
                seen[key] = True
    return {key: totals[key] if seen[key] else None for key in totals}
