"""Provide the Ollama transport boundary for the research workflow."""

from typing import Any

import httpx


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
        payload["format"] == schema

    response = await client.post("/api/chat", json=payload)
    response.raise_for_status()  # inspect HTTP status of response
    result = response.json()  # parse response(HTTPX object) to json

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
