"""Policy loading and checks."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml

POLICIES_DIR = Path(__file__).resolve().parents[3] / "policies"


def load_policy(name: str) -> dict[str, Any]:
    path = POLICIES_DIR / name
    with path.open("r", encoding="utf-8") as f:
        data = yaml.safe_load(f) or {}
    return data


def confidence_requires_review(confidence_score: float) -> bool:
    policy = load_policy("confidence-policy.yaml")
    threshold = float(policy.get("min_confidence", 0.7))
    return confidence_score < threshold
