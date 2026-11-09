"""Anthropic Messages API adapter (server-side credentials only)."""

from __future__ import annotations

import os

from ._http import request_json
from .base import AIProvider, ChatResponse, Message, ProviderError


class AnthropicProvider(AIProvider):
    name = "anthropic"

    def __init__(self, model: str, timeout: float = 30):
        self.api_key = os.getenv("ANTHROPIC_API_KEY", "")
        if not self.api_key:
            raise ProviderError("anthropic requires ANTHROPIC_API_KEY in the server environment")
        self.model = model
        self.timeout = timeout

    def generate(self, messages: list[Message], system_prompt: str | None = None) -> ChatResponse:
        payload: dict = {
            "model": self.model,
            "max_tokens": int(os.getenv("AI_MAX_OUTPUT_TOKENS", "1024")),
            "messages": [message for message in messages if message["role"] in {"user", "assistant"}],
        }
        if system_prompt:
            payload["system"] = system_prompt
        result = request_json(
            "POST",
            "https://api.anthropic.com/v1/messages",
            headers={"x-api-key": self.api_key, "anthropic-version": "2023-06-01"},
            payload=payload,
            timeout=self.timeout,
        )
        try:
            content = "\n".join(
                block["text"] for block in result["content"] if block.get("type") == "text"
            )
        except (KeyError, TypeError) as exc:
            raise ProviderError("Anthropic response did not contain text content") from exc
        if not content:
            raise ProviderError("Anthropic returned an empty response")
        return ChatResponse(content, str(result.get("model", self.model)), result.get("usage", {}))
