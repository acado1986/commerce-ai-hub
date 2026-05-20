"""Interactive CLI for the delivery hub."""

from __future__ import annotations

import argparse
import asyncio
import sys
import uuid
from collections.abc import AsyncIterator
from pathlib import Path
from typing import Any

from langgraph.types import Command

from agent.artifact_review import revise_artifacts
from agent.llm import azure_config_summary
from agent.observability import (
    flush_langfuse,
    langfuse_config_summary,
    langgraph_config,
)
from agent.orchestrator.graph import cli_graph

DEFAULT_TIMEOUT_SECONDS = 90


def compact_result(result: dict[str, Any]) -> str:
    lines = [
        f"run_id: {result.get('run_id')}",
        f"stage: {result.get('current_stage')}",
        f"approval_status: {result.get('approval_status')}",
        f"next_action: {result.get('next_action')}",
    ]
    if result.get("errors"):
        lines.append(f"errors: {result['errors']}")
    artifact_paths = result.get("artifact_paths", {})
    if artifact_paths:
        lines.append("artifacts:")
        lines.extend(f"  {name}: {path}" for name, path in artifact_paths.items())
    if result.get("__interrupt__"):
        lines.append("interrupt: human approval required")
    return "\n".join(lines)


async def print_progress(events: AsyncIterator[dict[str, Any]]) -> dict[str, Any]:
    final: dict[str, Any] = {}
    async for event in events:
        if "__interrupt__" in event:
            final = event
            print("[stage] approval interrupt", flush=True)
            continue
        for node_name, node_state in event.items():
            print(f"[stage] {node_name}", flush=True)
            if isinstance(node_state, dict):
                final = node_state
    return final


def print_approval_payload(payload: dict[str, Any]) -> None:
    print("\nApproval required")
    print(f"run_id: {payload.get('run_id')}")
    print(f"request_type: {payload.get('request_type')}")
    print(f"risk_level: {payload.get('risk_level')}")
    print("artifacts:")
    for name, path in payload.get("artifact_paths", {}).items():
        print(f"  {name}: {path}")


async def ask_approval(
    result: dict[str, Any],
    approve_all: bool,
    timeout: int,
) -> dict[str, Any] | None:
    interrupts = result.get("__interrupt__")
    if not interrupts:
        return None
    payload = interrupts[0].value if interrupts else {}
    print_approval_payload(payload)
    if approve_all:
        print("Auto-approving all generated artifacts.", flush=True)
        return {
            "approved": True,
            "reviewer_note": "Approved all generated artifacts via --approve-all.",
        }
    modified_files: list[str] = []
    while True:
        answer = input("Choose: [a]pprove all, [m]odify files, [r]eject: ").strip().lower()
        if answer in {"a", "approve", "y", "yes"}:
            return {
                "approved": True,
                "reviewer_note": input("Reviewer note (optional): ").strip(),
                "modified_files": modified_files,
            }
        if answer in {"r", "reject", "n", "no", ""}:
            return {
                "approved": False,
                "reviewer_note": input("Reviewer note (optional): ").strip(),
                "modified_files": modified_files,
            }
        if answer in {"m", "modify"}:
            instruction = input("What should be changed in the generated files? ").strip()
            if not instruction:
                print("No modification instruction provided.")
                continue
            modified = await asyncio.to_thread(
                revise_artifacts,
                payload.get("artifact_paths", {}),
                instruction,
                timeout,
            )
            modified_files.extend(modified)
            print(f"Modified files: {', '.join(modified) if modified else 'none'}")
            print_approval_payload(payload)
            continue
        print("Use a, m, or r.")


async def run_cli() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--input", help="Path to input markdown/text")
    parser.add_argument(
        "--interactive",
        action="store_true",
        help="Prompt for one request line in the terminal",
    )
    parser.add_argument(
        "--paste",
        action="store_true",
        help="Read multi-line request text from stdin until Ctrl+D",
    )
    parser.add_argument(
        "--timeout",
        type=int,
        default=DEFAULT_TIMEOUT_SECONDS,
        help="Maximum seconds to wait for the graph run",
    )
    parser.add_argument(
        "--check-config",
        action="store_true",
        help="Print Azure OpenAI config summary without exposing the API key",
    )
    parser.add_argument(
        "--approve-all",
        action="store_true",
        help="Automatically approve all generated artifacts at the approval gate",
    )
    args = parser.parse_args()
    if args.check_config:
        for name, value in azure_config_summary().items():
            print(f"{name}={value}")
        for name, value in langfuse_config_summary().items():
            print(f"{name}={value}")
        return
    if args.input:
        text = Path(args.input).read_text(encoding="utf-8")
    elif args.paste:
        print("Paste your request. Finish with Ctrl+D.", flush=True)
        text = sys.stdin.read()
    else:
        text = input("Request: ")
    if not text.strip():
        raise SystemExit("No request text provided.")
    print("Running delivery hub graph...", flush=True)
    run_id = str(uuid.uuid4())
    config = langgraph_config(
        thread_id=f"cli-{run_id}",
        run_id=run_id,
        source_type="cli",
        trace_name="ai-delivery-hub-cli",
    )
    try:
        result = await asyncio.wait_for(
            print_progress(
                cli_graph.astream(
                    {
                        "run_id": run_id,
                        "input_text": text,
                        "source_type": "manual_prompt",
                    },
                    config=config,
                    stream_mode="updates",
                )
            ),
            timeout=args.timeout,
        )
        decision = await ask_approval(result, args.approve_all, args.timeout)
        if decision is not None:
            print("Resuming graph with approval decision...", flush=True)
            result = await asyncio.wait_for(
                print_progress(
                    cli_graph.astream(
                        Command(resume=decision),
                        config=config,
                        stream_mode="updates",
                    )
                ),
                timeout=args.timeout,
            )
    finally:
        flush_langfuse()
    print("\nResult")
    print(compact_result(result))


def main_sync() -> None:
    asyncio.run(run_cli())


if __name__ == "__main__":
    main_sync()
