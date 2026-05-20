"""Artifact review and revision helpers."""

from __future__ import annotations

import json
from pathlib import Path

from agent.llm import (
    deployment_for_revision,
    get_model,
    invoke_model,
    model_name_for_deployment,
    response_content,
    response_usage,
)
from agent.observability import langchain_trace_config

MODIFIABLE_ARTIFACTS = {
    "requirements.md",
    "architecture.md",
    "implementation-plan.md",
    "qa-plan.md",
    "review-checklist.md",
    "ticket-comment.md",
}


def revise_artifacts(
    artifact_paths: dict[str, str],
    instruction: str,
    timeout: int,
) -> list[str]:
    deployment = deployment_for_revision()
    model_name = model_name_for_deployment(deployment)
    model = get_model(timeout=timeout, deployment=deployment)
    run_id = _run_id_from_paths(artifact_paths)
    modified: list[str] = []
    usage_entries: list[dict] = []
    for name, raw_path in artifact_paths.items():
        if name not in MODIFIABLE_ARTIFACTS:
            continue
        path = Path(raw_path)
        if not path.exists():
            continue
        current = path.read_text(encoding="utf-8")
        prompt = (
            "Revise this delivery artifact according to the reviewer instruction. "
            "Preserve useful detail and return markdown only.\n\n"
            f"Artifact: {name}\n"
            f"Reviewer instruction:\n{instruction}\n\n"
            f"Current artifact:\n{current}"
        )
        response = invoke_model(
            model,
            prompt,
            langchain_trace_config(
                trace_name="ai-delivery-hub-revision",
                run_id=run_id,
                source_type="review",
                stage="revision",
                artifact=name,
                model=model_name,
            ),
        )
        content = response_content(response)
        path.write_text(content, encoding="utf-8")
        usage_entries.append(
            {
                "stage": "revision",
                "artifact": name,
                **response_usage(response, requested_model=model_name),
            }
        )
        modified.append(name)
    if modified:
        run_dir = Path(next(iter(artifact_paths.values()))).parent
        modification_log = run_dir / "modifications.json"
        modification_log.write_text(
            json.dumps(
                {
                    "instruction": instruction,
                    "modified_files": modified,
                    "llm_usage": usage_entries,
                },
                indent=2,
                sort_keys=True,
            ),
            encoding="utf-8",
        )
    return modified


def _run_id_from_paths(artifact_paths: dict[str, str]) -> str | None:
    if not artifact_paths:
        return None
    first_path = Path(next(iter(artifact_paths.values())))
    return first_path.parent.name if first_path.parent.name else None
