"""Optional Langfuse tracing helpers for LangGraph and LangChain runs."""

from __future__ import annotations

import os
from collections.abc import Sequence
from contextlib import nullcontext
from typing import Any

from agent.llm import load_environment


def _normalize_langfuse_environment() -> None:
    load_environment()
    if os.getenv("LANGFUSE_HOST") and not os.getenv("LANGFUSE_BASE_URL"):
        os.environ["LANGFUSE_BASE_URL"] = os.environ["LANGFUSE_HOST"]


def langfuse_enabled() -> bool:
    _normalize_langfuse_environment()
    enabled = os.getenv("LANGFUSE_ENABLED", "true").lower()
    if enabled in {"0", "false", "no", "off"}:
        return False
    return bool(os.getenv("LANGFUSE_PUBLIC_KEY") and os.getenv("LANGFUSE_SECRET_KEY"))


def langfuse_manual_generations_enabled() -> bool:
    """Return whether model calls should be recorded as explicit generations."""
    _normalize_langfuse_environment()
    enabled = os.getenv("LANGFUSE_MANUAL_GENERATIONS", "true").lower()
    return enabled not in {"0", "false", "no", "off"}


def langfuse_capture_io_enabled() -> bool:
    """Return whether prompt and response bodies should be sent to Langfuse."""
    _normalize_langfuse_environment()
    enabled = os.getenv("LANGFUSE_CAPTURE_IO", "true").lower()
    return enabled not in {"0", "false", "no", "off"}


def langfuse_config_summary() -> dict[str, str]:
    _normalize_langfuse_environment()
    public_key = os.getenv("LANGFUSE_PUBLIC_KEY")
    secret_key = os.getenv("LANGFUSE_SECRET_KEY")
    return {
        "LANGFUSE_ENABLED": str(langfuse_enabled()),
        "LANGFUSE_MANUAL_GENERATIONS": str(langfuse_manual_generations_enabled()),
        "LANGFUSE_CAPTURE_IO": str(langfuse_capture_io_enabled()),
        "LANGFUSE_BASE_URL": os.getenv("LANGFUSE_BASE_URL", "<missing>"),
        "LANGFUSE_HOST": os.getenv("LANGFUSE_HOST", "<not set>"),
        "LANGFUSE_PUBLIC_KEY": (
            f"<set length={len(public_key)}>" if public_key else "<missing>"
        ),
        "LANGFUSE_SECRET_KEY": (
            f"<set length={len(secret_key)}>" if secret_key else "<missing>"
        ),
    }


def langfuse_usage_details(usage: dict[str, Any]) -> dict[str, int]:
    """Map normalized app usage to Langfuse usage detail keys."""
    details: dict[str, int] = {}
    if usage.get("input_tokens") is not None:
        details["input"] = int(usage["input_tokens"])
    if usage.get("output_tokens") is not None:
        details["output"] = int(usage["output_tokens"])
    if usage.get("total_tokens") is not None:
        details["total"] = int(usage["total_tokens"])
    return details


def _float_env(name: str) -> float | None:
    raw_value = os.getenv(name)
    if raw_value in {None, ""}:
        return None
    return float(raw_value)


def langfuse_cost_details(usage: dict[str, Any]) -> dict[str, float]:
    """Estimate Langfuse cost details from optional per-1K token rates."""
    _normalize_langfuse_environment()
    input_rate = _float_env("LANGFUSE_INPUT_COST_PER_1K_TOKENS_USD")
    output_rate = _float_env("LANGFUSE_OUTPUT_COST_PER_1K_TOKENS_USD")
    details: dict[str, float] = {}
    if input_rate is not None and usage.get("input_tokens") is not None:
        details["input"] = int(usage["input_tokens"]) * input_rate / 1000
    if output_rate is not None and usage.get("output_tokens") is not None:
        details["output"] = int(usage["output_tokens"]) * output_rate / 1000
    if details:
        details["total"] = sum(details.values())
    return details


def langfuse_generation_context(
    *,
    name: str,
    model: str | None,
    input_value: Any,
    metadata: dict[str, Any] | None = None,
):
    """Create a Langfuse generation context manager when tracing is active."""
    if not langfuse_enabled() or not langfuse_manual_generations_enabled():
        return nullcontext(None)
    from langfuse import get_client

    captured_input = input_value if langfuse_capture_io_enabled() else None
    return get_client().start_as_current_observation(
        as_type="generation",
        name=name,
        model=model,
        input=captured_input,
        metadata=metadata,
    )


def langchain_callbacks() -> list[Any]:
    if not langfuse_enabled():
        return []

    try:
        from langfuse.langchain import CallbackHandler
    except ImportError as exc:
        raise RuntimeError(
            "LANGFUSE_PUBLIC_KEY and LANGFUSE_SECRET_KEY are set, but the "
            "Langfuse LangChain integration dependencies are missing. Run "
            "`uv sync` to install them."
        ) from exc

    return [CallbackHandler()]


def _dedupe(values: Sequence[str]) -> list[str]:
    seen: set[str] = set()
    result: list[str] = []
    for value in values:
        if value and value not in seen:
            seen.add(value)
            result.append(value)
    return result


def langchain_trace_config(
    *,
    trace_name: str,
    run_id: str | None = None,
    source_type: str | None = None,
    stage: str | None = None,
    artifact: str | None = None,
    model: str | None = None,
    tags: Sequence[str] | None = None,
    metadata: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Build a LangChain RunnableConfig fragment for Langfuse tracing."""
    callbacks = langchain_callbacks()
    if not callbacks:
        return {}

    trace_tags = _dedupe(
        [
            "ai-delivery-hub",
            *(tags or []),
            *(["mcp"] if source_type == "mcp" else []),
            *(["cli"] if source_type in {"cli", "manual_prompt"} else []),
            *(["studio"] if source_type == "studio" else []),
            *(["stage:" + stage] if stage else []),
            *(["artifact:" + artifact] if artifact else []),
        ]
    )
    trace_metadata: dict[str, Any] = {
        "application": "ai-delivery-hub",
        "source_type": source_type,
        "delivery_run_id": run_id,
        "stage": stage,
        "artifact": artifact,
        "model": model,
    }
    if run_id:
        trace_metadata["langfuse_session_id"] = run_id
    trace_metadata.update(metadata or {})
    return {
        "callbacks": callbacks,
        "run_name": trace_name,
        "tags": trace_tags,
        "metadata": {k: v for k, v in trace_metadata.items() if v is not None},
    }


def langgraph_config(
    *,
    thread_id: str,
    run_id: str | None = None,
    source_type: str | None = None,
    trace_name: str = "ai-delivery-hub-workflow",
    tags: Sequence[str] | None = None,
    metadata: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Build config for checkpointed LangGraph invocations."""
    config: dict[str, Any] = {"configurable": {"thread_id": thread_id}}
    config.update(
        langchain_trace_config(
            trace_name=trace_name,
            run_id=run_id,
            source_type=source_type,
            tags=tags,
            metadata=metadata,
        )
    )
    return config


def with_stage_trace_config(
    parent_config: dict[str, Any] | None,
    *,
    stage: str,
    artifact: str | None = None,
    model: str | None = None,
) -> dict[str, Any] | None:
    """Add stage metadata to an inherited LangChain config."""
    if parent_config is None and not langfuse_enabled():
        return None

    config: dict[str, Any] = dict(parent_config or {})
    if not config.get("callbacks"):
        callbacks = langchain_callbacks()
        if callbacks:
            config["callbacks"] = callbacks
    metadata = dict(config.get("metadata") or {})
    configurable = dict(config.get("configurable") or {})
    thread_id = configurable.get("thread_id")
    if thread_id and "langfuse_session_id" not in metadata:
        metadata["langfuse_session_id"] = thread_id
    if thread_id and "delivery_thread_id" not in metadata:
        metadata["delivery_thread_id"] = thread_id
    metadata.update(
        {
            "stage": stage,
            "artifact": artifact,
            "model": model,
        }
    )
    tags = _dedupe(
        [
            *(config.get("tags") or []),
            f"stage:{stage}",
            *(["artifact:" + artifact] if artifact else []),
        ]
    )
    config["run_name"] = f"ai-delivery-hub:{stage}"
    config["metadata"] = {k: v for k, v in metadata.items() if v is not None}
    config["tags"] = tags
    return config


def traced_graph(compiled_graph: Any, *, trace_name: str) -> Any:
    """Attach default callbacks to Studio/server graph imports."""
    config = langchain_trace_config(trace_name=trace_name, source_type="studio")
    return compiled_graph.with_config(config) if config else compiled_graph


def flush_langfuse() -> None:
    """Flush traces before short-lived CLI/MCP processes exit."""
    if not langfuse_enabled():
        return
    try:
        from langfuse import get_client
    except ImportError:
        return
    get_client().flush()
