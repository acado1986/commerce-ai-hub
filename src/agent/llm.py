"""LangChain chat model integration utilities."""

from __future__ import annotations

import inspect
import os
from pathlib import Path
from typing import Any

from dotenv import load_dotenv
from langchain_core.language_models.chat_models import BaseChatModel
from langchain_openai import AzureChatOpenAI, ChatOpenAI


def response_content(response: Any) -> str:
    content = getattr(response, "content", response)
    return content if isinstance(content, str) else str(content)


def _invoke_model_raw(
    model: Any,
    prompt: str,
    config: dict[str, Any] | None = None,
) -> Any:
    if not config:
        return model.invoke(prompt)
    try:
        signature = inspect.signature(model.invoke)
    except (TypeError, ValueError):
        signature = None
    if signature and "config" not in signature.parameters:
        return model.invoke(prompt)
    return model.invoke(prompt, config=config)


def _config_without_callbacks(config: dict[str, Any] | None) -> dict[str, Any] | None:
    if not config:
        return config
    clean_config = dict(config)
    clean_config.pop("callbacks", None)
    return clean_config


def invoke_model(model: Any, prompt: str, config: dict[str, Any] | None = None) -> Any:
    """Invoke a LangChain model and record explicit Langfuse generation usage."""
    try:
        from agent.observability import (
            langfuse_capture_io_enabled,
            langfuse_cost_details,
            langfuse_generation_context,
            langfuse_manual_generations_enabled,
            langfuse_usage_details,
        )
    except ImportError:
        return _invoke_model_raw(model, prompt, config)

    if not langfuse_manual_generations_enabled():
        return _invoke_model_raw(model, prompt, config)

    metadata = dict((config or {}).get("metadata") or {})
    generation_name = str((config or {}).get("run_name") or "ai-delivery-hub:model")
    requested_model = metadata.get("model") or getattr(model, "model_name", None)
    with langfuse_generation_context(
        name=generation_name,
        model=requested_model,
        input_value=prompt,
        metadata=metadata,
    ) as generation:
        response = _invoke_model_raw(model, prompt, _config_without_callbacks(config))
        if generation is not None:
            usage = response_usage(response, requested_model=requested_model)
            output = response_content(response) if langfuse_capture_io_enabled() else None
            generation.update(
                output=output,
                model=usage.get("model") or requested_model,
                usage_details=langfuse_usage_details(usage) or None,
                cost_details=langfuse_cost_details(usage) or None,
            )
    return response


def _token_value(payload: dict[str, Any], *names: str) -> int | None:
    for name in names:
        value = payload.get(name)
        if value is not None:
            return int(value)
    return None


def response_usage(response: Any, requested_model: str | None = None) -> dict[str, Any]:
    """Normalize token metadata from LangChain chat responses."""
    usage = getattr(response, "usage", None) or {}
    usage_metadata = getattr(response, "usage_metadata", None) or {}
    response_metadata = getattr(response, "response_metadata", None) or {}
    token_usage = response_metadata.get("token_usage") or response_metadata.get("usage") or {}
    raw_usage = usage or usage_metadata or token_usage

    input_tokens = _token_value(
        raw_usage,
        "input_tokens",
        "prompt_tokens",
        "prompt",
    )
    output_tokens = _token_value(
        raw_usage,
        "output_tokens",
        "completion_tokens",
        "completion",
    )
    total_tokens = _token_value(raw_usage, "total_tokens", "total")
    if total_tokens is None and input_tokens is not None and output_tokens is not None:
        total_tokens = input_tokens + output_tokens

    response_model = (
        getattr(response, "model", None)
        or response_metadata.get("model_name")
        or response_metadata.get("model")
        or requested_model
        or os.getenv("AZURE_OPENAI_DEPLOYMENT")
    )
    provider = getattr(response, "provider", None) or "azure_openai"
    return {
        "provider": provider,
        "model": response_model,
        "input_tokens": input_tokens,
        "output_tokens": output_tokens,
        "total_tokens": total_tokens,
        "raw_usage": raw_usage,
    }


def env_path() -> Path:
    return Path(__file__).resolve().parents[2] / ".env"


def _env_name_suffix(value: str) -> str:
    return "".join(char if char.isalnum() else "_" for char in value).upper()


def load_environment() -> None:
    load_dotenv(dotenv_path=env_path())


def azure_config_summary() -> dict[str, str]:
    load_environment()
    key = os.getenv("AZURE_OPENAI_API_KEY")
    return {
        "AZURE_OPENAI_ENDPOINT": os.getenv("AZURE_OPENAI_ENDPOINT", "<missing>"),
        "AZURE_OPENAI_DEPLOYMENT": os.getenv("AZURE_OPENAI_DEPLOYMENT", "<missing>"),
        "AZURE_OPENAI_MODEL_NAME": os.getenv(
            "AZURE_OPENAI_MODEL_NAME",
            "<uses deployment name>",
        ),
        "AZURE_OPENAI_CLASSIFICATION_DEPLOYMENT": os.getenv(
            "AZURE_OPENAI_CLASSIFICATION_DEPLOYMENT",
            "<uses AZURE_OPENAI_DEPLOYMENT>",
        ),
        "AZURE_OPENAI_REQUIREMENTS_DEPLOYMENT": os.getenv(
            "AZURE_OPENAI_REQUIREMENTS_DEPLOYMENT",
            "<uses AZURE_OPENAI_DEPLOYMENT>",
        ),
        "AZURE_OPENAI_ARCHITECTURE_DEPLOYMENT": os.getenv(
            "AZURE_OPENAI_ARCHITECTURE_DEPLOYMENT",
            "<uses AZURE_OPENAI_DEPLOYMENT>",
        ),
        "AZURE_OPENAI_PLANNING_DEPLOYMENT": os.getenv(
            "AZURE_OPENAI_PLANNING_DEPLOYMENT",
            "<uses AZURE_OPENAI_DEPLOYMENT>",
        ),
        "AZURE_OPENAI_REVIEW_DEPLOYMENT": os.getenv(
            "AZURE_OPENAI_REVIEW_DEPLOYMENT",
            "<uses AZURE_OPENAI_PLANNING_DEPLOYMENT>",
        ),
        "AZURE_OPENAI_QA_DEPLOYMENT": os.getenv(
            "AZURE_OPENAI_QA_DEPLOYMENT",
            "<uses AZURE_OPENAI_DEPLOYMENT>",
        ),
        "AZURE_OPENAI_DOCUMENTATION_DEPLOYMENT": os.getenv(
            "AZURE_OPENAI_DOCUMENTATION_DEPLOYMENT",
            "<uses AZURE_OPENAI_DEPLOYMENT>",
        ),
        "AZURE_OPENAI_REVISION_DEPLOYMENT": os.getenv(
            "AZURE_OPENAI_REVISION_DEPLOYMENT",
            "<uses AZURE_OPENAI_DEPLOYMENT>",
        ),
        "AZURE_OPENAI_DRAFT_DEPLOYMENT": os.getenv(
            "AZURE_OPENAI_DRAFT_DEPLOYMENT",
            "<uses AZURE_OPENAI_DEPLOYMENT>",
        ),
        "AZURE_OPENAI_API_VERSION": os.getenv(
            "AZURE_OPENAI_API_VERSION", "2024-12-01-preview"
        ),
        "AZURE_OPENAI_API_KEY": f"<set length={len(key)}>" if key else "<missing>",
    }


def _uses_openai_compatible_endpoint(endpoint: str) -> bool:
    return "/openai/v1" in endpoint.rstrip("/")


def _openai_v1_base_url(endpoint: str) -> str:
    return endpoint.rstrip("/") + "/"


def _apim_headers(api_key: str) -> dict[str, str]:
    return {
        "api-key": api_key,
        "Ocp-Apim-Subscription-Key": api_key,
    }


def _base_deployment() -> str | None:
    load_environment()
    return os.getenv("AZURE_OPENAI_DEPLOYMENT")


def deployment_from_env(name: str, fallback: str | None = None) -> str:
    load_environment()
    deployment = os.getenv(name) or fallback or _base_deployment()
    if not deployment:
        raise RuntimeError(
            "Azure OpenAI deployment configuration is required. "
            f"Set {name} or AZURE_OPENAI_DEPLOYMENT."
        )
    return deployment


def deployment_for_classification() -> str:
    return deployment_from_env("AZURE_OPENAI_CLASSIFICATION_DEPLOYMENT")


def deployment_for_artifact(artifact_name: str, risk_level: str | None = None) -> str:
    if artifact_name == "requirements.md":
        return deployment_from_env("AZURE_OPENAI_REQUIREMENTS_DEPLOYMENT")
    if artifact_name == "architecture.md":
        return deployment_from_env("AZURE_OPENAI_ARCHITECTURE_DEPLOYMENT")
    if artifact_name == "implementation-plan.md":
        return deployment_from_env("AZURE_OPENAI_PLANNING_DEPLOYMENT")
    if artifact_name == "review-checklist.md":
        planning = deployment_from_env("AZURE_OPENAI_PLANNING_DEPLOYMENT")
        if risk_level == "high":
            return deployment_from_env("AZURE_OPENAI_REVIEW_DEPLOYMENT", planning)
        return os.getenv("AZURE_OPENAI_REVIEW_DEPLOYMENT") or planning
    if artifact_name == "qa-plan.md":
        return deployment_from_env("AZURE_OPENAI_QA_DEPLOYMENT")
    if artifact_name == "ticket-comment.md":
        return deployment_from_env("AZURE_OPENAI_DOCUMENTATION_DEPLOYMENT")
    return deployment_from_env("AZURE_OPENAI_DEPLOYMENT")


def deployment_for_revision() -> str:
    return deployment_from_env("AZURE_OPENAI_REVISION_DEPLOYMENT")


def deployment_for_draft() -> str:
    return deployment_from_env("AZURE_OPENAI_DRAFT_DEPLOYMENT")


def model_name_for_deployment(deployment: str | None) -> str | None:
    """Resolve the model name Langfuse should use for cost attribution."""
    load_environment()
    if not deployment:
        return os.getenv("AZURE_OPENAI_MODEL_NAME")
    return (
        os.getenv(f"LANGFUSE_MODEL_NAME_{_env_name_suffix(deployment)}")
        or os.getenv(f"AZURE_OPENAI_MODEL_NAME_{_env_name_suffix(deployment)}")
        or os.getenv("AZURE_OPENAI_MODEL_NAME")
        or deployment
    )


def get_model(
    timeout: int = 60,
    deployment: str | None = None,
) -> BaseChatModel:
    load_environment()
    endpoint = os.getenv("AZURE_OPENAI_ENDPOINT")
    selected_deployment = deployment or os.getenv("AZURE_OPENAI_DEPLOYMENT")
    api_key = os.getenv("AZURE_OPENAI_API_KEY")
    api_version = os.getenv("AZURE_OPENAI_API_VERSION", "2024-12-01-preview")
    missing = [
        name
        for name, value in {
            "AZURE_OPENAI_ENDPOINT": endpoint,
            "AZURE_OPENAI_DEPLOYMENT": selected_deployment,
            "AZURE_OPENAI_API_KEY": api_key,
        }.items()
        if not value
    ]
    if missing:
        raise RuntimeError(
            "Azure OpenAI configuration is required for MVP generation flow. "
            f"Missing: {', '.join(missing)}."
        )
    if _uses_openai_compatible_endpoint(endpoint):
        return ChatOpenAI(
            model=selected_deployment,
            base_url=_openai_v1_base_url(endpoint),
            api_key=api_key,
            default_headers=_apim_headers(api_key),
            timeout=timeout,
            max_retries=1,
        )
    return AzureChatOpenAI(
        azure_endpoint=endpoint,
        azure_deployment=selected_deployment,
        model=model_name_for_deployment(selected_deployment),
        api_key=api_key,
        api_version=api_version,
        timeout=timeout,
        max_retries=1,
    )
