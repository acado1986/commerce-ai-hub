#!/usr/bin/env python3
"""Sync Langfuse model prices from Azure Retail Prices API."""

from __future__ import annotations

import argparse
import base64
import json
import os
import re
import sys
import urllib.parse
import urllib.request
from pathlib import Path
from typing import Any

from dotenv import load_dotenv

RETAIL_API = "https://prices.azure.com/api/retail/prices"


def _env_path() -> Path:
    return Path(__file__).resolve().parents[1] / ".env"


def _load_env() -> None:
    load_dotenv(dotenv_path=_env_path())


def _required(name: str) -> str:
    value = os.getenv(name)
    if not value:
        raise RuntimeError(f"Missing required env var: {name}")
    return value


def _http_json(url: str, *, method: str = "GET", headers: dict[str, str] | None = None, body: dict[str, Any] | None = None) -> dict[str, Any]:
    payload = None if body is None else json.dumps(body).encode("utf-8")
    request = urllib.request.Request(url=url, method=method, headers=headers or {}, data=payload)
    with urllib.request.urlopen(request, timeout=60) as response:
        return json.loads(response.read().decode("utf-8"))


def _azure_prices_pages(filter_expr: str, *, max_pages: int | None = None) -> list[dict[str, Any]]:
    query = urllib.parse.urlencode(
        {
            "api-version": "2023-01-01-preview",
            "$filter": filter_expr,
        }
    )
    url = f"{RETAIL_API}?{query}"
    items: list[dict[str, Any]] = []
    page_number = 0
    while url:
        page_number += 1
        if max_pages is not None and page_number > max_pages:
            break
        page = _http_json(url)
        page_items = page.get("Items") or []
        items.extend(page_items)
        print(
            f"Fetched Azure prices page {page_number}: +{len(page_items)} items (total={len(items)})",
            flush=True,
        )
        url = page.get("NextPageLink")
    if max_pages is not None and url:
        print(
            f"Stopped early after {max_pages} pages; more Azure pages are available.",
            flush=True,
        )
    return items


def _find_latest_price(items: list[dict[str, Any]], meter_regex: str, region: str) -> float:
    pattern = re.compile(meter_regex, re.IGNORECASE)
    filtered = [
        i
        for i in items
        if i.get("type") == "Consumption"
        and i.get("armRegionName") == region
        and pattern.search(str(i.get("meterName", "")))
    ]
    if not filtered:
        raise RuntimeError(
            f"No Azure price match for regex={meter_regex!r} in region={region!r}."
        )
    filtered.sort(key=lambda x: str(x.get("effectiveStartDate") or ""), reverse=True)
    return float(filtered[0]["retailPrice"])


def _langfuse_auth_header(public_key: str, secret_key: str) -> str:
    token = base64.b64encode(f"{public_key}:{secret_key}".encode("utf-8")).decode("utf-8")
    return f"Basic {token}"


def _langfuse_list_models(base_url: str, auth_header: str) -> list[dict[str, Any]]:
    data = _http_json(
        f"{base_url.rstrip('/')}/api/public/models?limit=100",
        headers={"Authorization": auth_header},
    )
    return data.get("data") or []


def _langfuse_create_model(
    base_url: str,
    auth_header: str,
    *,
    model_name: str,
    match_pattern: str,
    input_price_per_token: float,
    output_price_per_token: float,
) -> None:
    _http_json(
        f"{base_url.rstrip('/')}/api/public/models",
        method="POST",
        headers={
            "Authorization": auth_header,
            "Content-Type": "application/json",
        },
        body={
            "modelName": model_name,
            "matchPattern": match_pattern,
            "unit": "TOKENS",
            "inputPrice": input_price_per_token,
            "outputPrice": output_price_per_token,
        },
    )


def _langfuse_delete_model(base_url: str, auth_header: str, model_id: str) -> None:
    _http_json(
        f"{base_url.rstrip('/')}/api/public/models/{model_id}",
        method="DELETE",
        headers={"Authorization": auth_header},
    )


def _prune_suffix_models(
    base_url: str,
    auth_header: str,
    *,
    base_model_names: set[str],
) -> None:
    models = _langfuse_list_models(base_url, auth_header)
    for model in models:
        model_name = str(model.get("modelName") or "")
        if model.get("isLangfuseManaged", True):
            continue
        for base_name in base_model_names:
            if model_name.startswith(f"{base_name}-"):
                _langfuse_delete_model(base_url, auth_header, str(model["id"]))
                print(f"Deleted suffix model definition: {model_name}", flush=True)
                break


def _upsert_langfuse_model(
    base_url: str,
    auth_header: str,
    *,
    model_name: str,
    match_pattern: str,
    input_price_per_token: float,
    output_price_per_token: float,
) -> None:
    models = _langfuse_list_models(base_url, auth_header)
    for model in models:
        if model.get("modelName") == model_name and not model.get("isLangfuseManaged", True):
            _langfuse_delete_model(base_url, auth_header, str(model["id"]))
    _langfuse_create_model(
        base_url,
        auth_header,
        model_name=model_name,
        match_pattern=match_pattern,
        input_price_per_token=input_price_per_token,
        output_price_per_token=output_price_per_token,
    )


def _parse_model_list(value: str | None) -> set[str] | None:
    if not value:
        return None
    selected = {item.strip() for item in value.split(",") if item.strip()}
    return selected or None


def sync(*, max_pages: int | None = None, selected_models: set[str] | None = None) -> None:
    _load_env()
    region = os.getenv("AZURE_OPENAI_PRICING_REGION", "eastus2")
    exact_suffix = os.getenv("LANGFUSE_EXACT_MODEL_SUFFIX", "false").lower() not in {
        "0",
        "false",
        "no",
    }
    prune_suffix_models = os.getenv("LANGFUSE_PRUNE_SUFFIX_MODELS", "true").lower() not in {
        "0",
        "false",
        "no",
    }
    skip_missing_azure_price = os.getenv("AZURE_SKIP_MISSING_PRICE", "true").lower() not in {
        "0",
        "false",
        "no",
    }

    mappings = {
        "gpt-5.1": {
            "model_name": os.getenv("LANGFUSE_MODEL_NAME_GPT_5_1", "gpt-5.1"),
            "input": _required("AZURE_PRICE_REGEX_GPT_5_1_INPUT"),
            "output": _required("AZURE_PRICE_REGEX_GPT_5_1_OUTPUT"),
            "match_pattern": r"(?i)^gpt-5\.1(?:[-:].+)?$",
            "azure_filter": "serviceName eq 'Foundry Models' and contains(meterName, 'GPT 5.1')",
        },
        "gpt-5-mini": {
            "model_name": os.getenv("LANGFUSE_MODEL_NAME_GPT_5_MINI", "gpt-5-mini"),
            "input": _required("AZURE_PRICE_REGEX_GPT_5_MINI_INPUT"),
            "output": _required("AZURE_PRICE_REGEX_GPT_5_MINI_OUTPUT"),
            "match_pattern": r"(?i)^gpt-5-mini(?:[-:].+)?$",
            "azure_filter": "serviceName eq 'Foundry Models' and contains(meterName, 'GPT 5 Mini')",
        },
        "gpt-5.4": {
            "model_name": os.getenv("LANGFUSE_MODEL_NAME_GPT_5_4", "gpt-5.4"),
            "input": _required("AZURE_PRICE_REGEX_GPT_5_4_INPUT"),
            "output": _required("AZURE_PRICE_REGEX_GPT_5_4_OUTPUT"),
            "match_pattern": r"(?i)^gpt-5\.4(?:[-:].+)?$",
            "azure_filter": "serviceName eq 'Foundry Models' and contains(meterName, 'GPT 5.4')",
        },
    }
    for cfg in mappings.values():
        if exact_suffix:
            cfg["match_pattern"] = rf"(?i)^({re.escape(str(cfg['model_name']))})$"
    if selected_models is not None:
        unknown = sorted(selected_models - set(mappings))
        if unknown:
            raise RuntimeError(
                f"Unknown model(s): {', '.join(unknown)}. Valid values: {', '.join(sorted(mappings))}"
            )
        mappings = {name: cfg for name, cfg in mappings.items() if name in selected_models}
        if not mappings:
            raise RuntimeError("No models selected after filtering.")

    langfuse_base = _required("LANGFUSE_BASE_URL").strip('"')
    public_key = _required("LANGFUSE_PUBLIC_KEY").strip('"')
    secret_key = _required("LANGFUSE_SECRET_KEY").strip('"')
    auth_header = _langfuse_auth_header(public_key, secret_key)
    if prune_suffix_models and not exact_suffix:
        base_names = {str(cfg["model_name"]) for cfg in mappings.values()}
        _prune_suffix_models(
            langfuse_base,
            auth_header,
            base_model_names=base_names,
        )

    for _, patterns in mappings.items():
        model_name = str(patterns["model_name"])
        items = _azure_prices_pages(patterns["azure_filter"], max_pages=max_pages)
        try:
            input_per_million = _find_latest_price(items, patterns["input"], region)
            output_per_million = _find_latest_price(items, patterns["output"], region)
        except RuntimeError as exc:
            if skip_missing_azure_price:
                print(f"WARN: Skipping {model_name}: {exc}", flush=True)
                continue
            raise
        input_per_token = input_per_million / 1_000_000
        output_per_token = output_per_million / 1_000_000
        _upsert_langfuse_model(
            langfuse_base,
            auth_header,
            model_name=model_name,
            match_pattern=patterns["match_pattern"],
            input_price_per_token=input_per_token,
            output_price_per_token=output_per_token,
        )
        print(
            f"Synced {model_name}: input={input_per_million}/1M, output={output_per_million}/1M (region={region})"
        )


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--max-pages",
        type=int,
        default=0,
        help="Limit Azure Retail API pagination for debugging (0 means no limit).",
    )
    parser.add_argument(
        "--models",
        default="",
        help="Comma-separated model keys to sync (for example: gpt-5.4,gpt-5-mini).",
    )
    args = parser.parse_args()
    try:
        selected_models = _parse_model_list(args.models) or _parse_model_list(
            os.getenv("AZURE_SYNC_MODELS")
        )
        sync(
            max_pages=args.max_pages or None,
            selected_models=selected_models,
        )
    except Exception as exc:  # pragma: no cover
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
