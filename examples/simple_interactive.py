"""Minimal interactive Azure OpenAI example."""

from __future__ import annotations

import argparse
import asyncio
import uuid

from agent.llm import (
    azure_config_summary,
    get_model,
    invoke_model,
    model_name_for_deployment,
)
from agent.observability import (
    flush_langfuse,
    langchain_trace_config,
    langfuse_config_summary,
)

DEFAULT_TIMEOUT_SECONDS = 45


def ask_model(prompt: str, timeout: int) -> str:
    model = get_model(timeout=timeout)
    run_id = str(uuid.uuid4())
    model_name = model_name_for_deployment(None)
    response = invoke_model(
        model,
        "Answer briefly and practically. User request:\n\n" + prompt.strip(),
        langchain_trace_config(
            trace_name="ai-delivery-hub-simple-prompt",
            run_id=run_id,
            source_type="cli",
            stage="simple_prompt",
            model=model_name,
        ),
    )
    return response.content if isinstance(response.content, str) else str(response.content)


async def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--timeout",
        type=int,
        default=DEFAULT_TIMEOUT_SECONDS,
        help="Maximum seconds to wait for the model call",
    )
    parser.add_argument(
        "--check-config",
        action="store_true",
        help="Print Azure OpenAI config summary without exposing the API key",
    )
    args = parser.parse_args()
    if args.check_config:
        for name, value in azure_config_summary().items():
            print(f"{name}={value}")
        for name, value in langfuse_config_summary().items():
            print(f"{name}={value}")
        return

    prompt = input("Request: ").strip()
    if not prompt:
        raise SystemExit("No request text provided.")

    print("Calling Azure OpenAI...", flush=True)
    try:
        answer = await asyncio.wait_for(
            asyncio.to_thread(ask_model, prompt, args.timeout),
            timeout=args.timeout,
        )
    except TimeoutError as exc:
        raise SystemExit(
            f"Timed out after {args.timeout}s waiting for Azure OpenAI."
        ) from exc

    print("\nAnswer")
    print(answer)
    flush_langfuse()


if __name__ == "__main__":
    asyncio.run(main())
