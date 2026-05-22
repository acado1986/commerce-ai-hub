"""Business logic for the delivery hub interactive CLI."""

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
SOURCE_TYPE = "manual_prompt"


def build_parser() -> argparse.ArgumentParser:
    """Build CLI argument parser."""
    parser = argparse.ArgumentParser()
    parser.add_argument("--input", help="Path to input markdown/text")
    parser.add_argument(
        "--interactive",
        action="store_true",
        help="Prompt in terminal; supports @path/to/file.md",
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
        help="Automatically approve each current stage at approval gates",
    )
    return parser


def resolve_request_text(args: argparse.Namespace) -> str:
    """Resolve request text from --input, --paste, or interactive prompt."""
    if args.input:
        return Path(args.input).read_text(encoding="utf-8")
    if args.paste:
        print("Paste your request. Finish with Ctrl+D.", flush=True)
        return sys.stdin.read()
    raw = input("Request (or @path/to/file.md): ")
    if raw.startswith("@"):
        return Path(raw[1:].strip()).read_text(encoding="utf-8")
    return raw


def compact_result(result: dict[str, Any]) -> str:
    """Format final workflow state for compact CLI output."""
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
    """Stream graph updates and return the latest state payload."""
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
    """Print approval summary for current stage."""
    print("\nApproval required")
    print(f"run_id: {payload.get('run_id')}")
    print(f"request_type: {payload.get('request_type')}")
    print(f"risk_level: {payload.get('risk_level')}")
    print("artifacts:")
    for name, path in payload.get("artifact_paths", {}).items():
        print(f"  {name}: {path}")


def approval_decision_note() -> str:
    """Read optional reviewer note from stdin."""
    return input("Reviewer note (optional): ").strip()


async def ask_approval(
    result: dict[str, Any],
    approve_all: bool,
    timeout: int,
) -> dict[str, Any] | None:
    """Request and validate approval decision when graph interrupts."""
    interrupts = result.get("__interrupt__")
    if not interrupts:
        return None
    payload = interrupts[0].value if interrupts else {}
    print_approval_payload(payload)
    if approve_all:
        print("Auto-approving current stage at each approval gate.", flush=True)
        return {
            "approved": True,
            "reviewer_note": "Approved current stage via --approve-all.",
        }
    modified_files: list[str] = []
    while True:
        answer = input("Choose: [a]pprove, [m]odify files, [r]eject: ").strip().lower()
        if answer in {"a", "approve", "y", "yes"}:
            return {
                "approved": True,
                "reviewer_note": approval_decision_note(),
                "modified_files": modified_files,
            }
        if answer in {"r", "reject", "n", "no"}:
            return {
                "approved": False,
                "reviewer_note": approval_decision_note(),
                "modified_files": modified_files,
            }
        if not answer:
            print("Please choose a, m, or r.")
            continue
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


def print_config_summary() -> None:
    """Print non-secret model/tracing configuration values."""
    for name, value in azure_config_summary().items():
        print(f"{name}={value}")
    for name, value in langfuse_config_summary().items():
        print(f"{name}={value}")


def cli_run_config(run_id: str) -> dict[str, Any]:
    """Build traced graph config for a CLI execution."""
    return langgraph_config(
        thread_id=f"cli-{run_id}",
        run_id=run_id,
        source_type="cli",
        trace_name="ai-delivery-hub-cli",
    )


async def stream_graph(
    graph_input: dict[str, Any] | Command,
    config: dict[str, Any],
    timeout: int,
) -> dict[str, Any]:
    """Execute one graph stream turn with a timeout."""
    return await asyncio.wait_for(
        print_progress(
            cli_graph.astream(
                graph_input,
                config=config,
                stream_mode="updates",
            )
        ),
        timeout=timeout,
    )


async def run_cli() -> None:
    """Run the interactive delivery hub CLI."""
    args = build_parser().parse_args()
    if args.check_config:
        print_config_summary()
        return

    text = resolve_request_text(args)
    if not text.strip():
        raise SystemExit("No request text provided.")

    print("Running delivery hub graph...", flush=True)
    run_id = str(uuid.uuid4())
    config = cli_run_config(run_id)

    try:
        result = await stream_graph(
            {
                "run_id": run_id,
                "input_text": text,
                "source_type": SOURCE_TYPE,
                "timeout": args.timeout,
            },
            config=config,
            timeout=args.timeout,
        )
        while True:
            decision = await ask_approval(result, args.approve_all, args.timeout)
            if decision is None:
                break
            print("Resuming graph with approval decision...", flush=True)
            result = await stream_graph(
                Command(resume=decision),
                config=config,
                timeout=args.timeout,
            )
    finally:
        flush_langfuse()

    print("\nResult")
    print(compact_result(result))
