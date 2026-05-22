"""State model for AI Delivery Hub."""

from __future__ import annotations

from typing import Any, Literal, TypedDict

RequestType = Literal[
    "implementation",
    "architecture",
    "offer",
    "proposal",
    "bug_investigation",
    "documentation",
    "qa",
    "research",
]

PlatformType = Literal["adobe_commerce", "app_builder", "generic"]
RiskLevel = Literal["low", "medium", "high"]
ApprovalStatus = Literal["not_required", "pending", "approved", "rejected", "blocked"]


class DeliveryHubState(TypedDict, total=False):
    run_id: str
    source_type: str
    source_id: str | None
    input_text: str
    timeout: int
    request_type: RequestType
    platforms: list[PlatformType]
    confidence_score: float
    risk_level: RiskLevel
    current_stage: str
    approval_status: ApprovalStatus
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
