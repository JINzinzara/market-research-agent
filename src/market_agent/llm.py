"""Provide the Ollama transport boundary for the research workflow."""

from copy import deepcopy
from decimal import Decimal
from typing import Any

import httpx

ASTRA_MODEL = "gpt-6-astra"
ASTRA_PRICE_SOURCE = "https://developers.openai.com/api/docs/models/gpt-6-astra"


async def call_openai(client: httpx.AsyncClient, messages: list[dict[str, str]], schema: dict) -> dict:
    """Return the Responses envelope; parse afterward so incomplete usage is retained."""
    strict_schema = deepcopy(schema)
    strict_schema["required"] = list(strict_schema["properties"])
    for value in strict_schema["properties"].values():
        value.pop("default", None)
    response = await client.post("/v1/responses", json={
        "model": ASTRA_MODEL, "input": messages, "store": False,
        "reasoning": {"effort": "low"}, "max_output_tokens": 1024,
        "text": {"format": {"type": "json_schema", "name": "research_plan",
                              "strict": True, "schema": strict_schema}},
    })
    response.raise_for_status()
    raw = response.json()
    if not isinstance(raw, dict):
        raise ValueError("OpenAI response must be an object")
    return raw


def openai_output_text(raw: dict) -> str:
    if raw.get("status") != "completed":
        raise RuntimeError(f"OpenAI response did not complete: {raw.get('status')}")
    output = raw.get("output")
    if not isinstance(output, list):
        raise ValueError("OpenAI output must be an array")
    texts = []
    for item in output:
        if not isinstance(item, dict) or item.get("type") != "message":
            continue
        blocks = item.get("content", [])
        if not isinstance(blocks, list):
            raise ValueError("OpenAI message content must be an array")
        for block in blocks:
            if not isinstance(block, dict):
                raise ValueError("invalid OpenAI content block")
            if block.get("type") == "refusal":
                raise RuntimeError("OpenAI refused the planning request")
            if block.get("type") == "output_text" and isinstance(block.get("text"), str):
                texts.append(block["text"])
    content = "".join(texts)
    if not content.strip():
        raise RuntimeError("OpenAI response contains no usable text")
    return content


def without_reasoning(raw: dict) -> dict:
    safe = deepcopy(raw)
    if isinstance(safe.get("message"), dict):
        safe["message"].pop("thinking", None)
    if isinstance(safe.get("output"), list):
        safe["output"] = [item for item in safe["output"] if not isinstance(item, dict) or item.get("type") != "reasoning"]
    return safe


def usage_metadata(raw: dict, provider: str) -> dict:
    """Normalize observed counts and a dated Standard text-price estimate, not a bill."""
    if provider == "ollama":
        return {**{key: raw.get(key) for key in ("prompt_eval_count", "eval_count", "total_duration")},
                "input_tokens": raw.get("prompt_eval_count"), "output_tokens": raw.get("eval_count"),
                "estimated_api_cost_usd": 0, "cost_basis": "local Ollama; operating cost unmeasured"}
    usage = raw.get("usage") if isinstance(raw.get("usage"), dict) else {}
    inputs, outputs = usage.get("input_tokens"), usage.get("output_tokens")
    details = usage.get("input_tokens_details") or {}
    cached = details.get("cached_tokens") if isinstance(details, dict) else None
    estimated = None
    if all(type(value) is int and value >= 0 for value in (inputs, outputs, cached)) and cached <= inputs:
        estimated = float((Decimal(inputs - cached) * 10 + Decimal(cached) + Decimal(outputs) * 50) / 1_000_000)
    output_details = usage.get("output_tokens_details")
    return {"input_tokens": inputs, "output_tokens": outputs, "cached_input_tokens": cached,
            "reasoning_tokens": output_details.get("reasoning_tokens") if isinstance(output_details, dict) else None,
            "estimated_api_cost_usd": estimated, "pricing_checked": "2026-10-16",
            "pricing_source": ASTRA_PRICE_SOURCE,
            "cost_basis": "GPT-6 Astra Standard text estimate, $10/$1/$50 per million uncached/cached/output tokens; cache-write premiums, other fees and tax excluded. Reasoning is already part of output tokens."}


async def call_llm(
    client: httpx.AsyncClient,
    model: str,
    messages: list[dict[str, str]],
    schema: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Send a non-streaming chat request to a local Ollama model.

    Optionally request structured output using a JSON Schema.
    Validate the response envelope and preserve the complete response
    for downstream parsing, evaluation, and usage tracking.

    Args:
        client: Async HTTP client configured with the Ollama base URL
            and request timeout. The caller manages its lifetime.
        model: Name of the local Ollama model to use.
        messages: Ordered chat messages containing role and content.
        schema: Optional JSON Schema passed to Ollama's format field.

    Returns:
        Complete Ollama response containing the assistant message
        and any usage or timing fields reported by the server.
    """
    if not isinstance(model, str) or not model.strip():
        raise ValueError("model must be a non-empty string")
    if not isinstance(messages, list) or not messages:
        raise ValueError("messages must be a non-empty list")

    payload = {
        "model": model,
        "messages": messages,
        "stream": False,
        "think": False,
        "options": {"temperature": 0},
        "keep_alive": "10m",
    }
    if schema is not None:
        payload["format"] = schema

    response = await client.post("/api/chat", json=payload)
    response.raise_for_status()
    result = response.json()

    if not isinstance(result, dict):
        raise ValueError("Ollama response must be a dictionary")
    message = result.get("message")
    if not isinstance(message, dict):
        raise ValueError("Ollama message must be a dictionary")
    if result.get("done") is not True:
        raise RuntimeError("Ollama response did not complete")
    content = message.get("content")
    if not isinstance(content, str) or not content.strip():
        raise RuntimeError("Ollama response contains no usable content")

    return result
