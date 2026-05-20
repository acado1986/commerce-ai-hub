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


def _azure_prices_pages(filter_expr: str) -> list[dict[str, Any]]:
    query = urllib.parse.urlencode(
        {
            "api-version": "2023-01-01-preview",
            "$filter": filter_expr,
        }
    )
    url = f"{RETAIL_API}?{query}"
    items: list[dict[str, Any]] = []
    while url:
        page = _http_json(url)
        items.extend(page.get("Items") or [])
        url = page.get("NextPageLink")
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
            "matchPattern": f"(?i)^({re.escape(model_name)})$",
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


def _upsert_langfuse_model(
    base_url: str,
    auth_header: str,
    *,
    model_name: str,
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
        input_price_per_token=input_price_per_token,
        output_price_per_token=output_price_per_token,
    )


def sync() -> None:
    _load_env()
    region = os.getenv("AZURE_OPENAI_PRICING_REGION", "eastus2")

    mappings = {
        "gpt-5.1": {
            "input": _required("AZURE_PRICE_REGEX_GPT_5_1_INPUT"),
            "output": _required("AZURE_PRICE_REGEX_GPT_5_1_OUTPUT"),
        },
        "gpt-5-mini": {
            "input": _required("AZURE_PRICE_REGEX_GPT_5_MINI_INPUT"),
            "output": _required("AZURE_PRICE_REGEX_GPT_5_MINI_OUTPUT"),
        },
        "gpt-5.4": {
            "input": _required("AZURE_PRICE_REGEX_GPT_5_4_INPUT"),
            "output": _required("AZURE_PRICE_REGEX_GPT_5_4_OUTPUT"),
        },
    }

    items = _azure_prices_pages("serviceName eq 'Foundry Models'")

    langfuse_base = _required("LANGFUSE_BASE_URL").strip('"')
    public_key = _required("LANGFUSE_PUBLIC_KEY").strip('"')
    secret_key = _required("LANGFUSE_SECRET_KEY").strip('"')
    auth_header = _langfuse_auth_header(public_key, secret_key)

    for model_name, patterns in mappings.items():
        input_per_million = _find_latest_price(items, patterns["input"], region)
        output_per_million = _find_latest_price(items, patterns["output"], region)
        input_per_token = input_per_million / 1_000_000
        output_per_token = output_per_million / 1_000_000
        _upsert_langfuse_model(
            langfuse_base,
            auth_header,
            model_name=model_name,
            input_price_per_token=input_per_token,
            output_price_per_token=output_per_token,
        )
        print(
            f"Synced {model_name}: input={input_per_million}/1M, output={output_per_million}/1M (region={region})"
        )


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    _ = parser.parse_args()
    try:
        sync()
    except Exception as exc:  # pragma: no cover
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
