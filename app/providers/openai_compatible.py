"""OpenAI and OpenAI-compatible Chat Completions adapter."""

from __future__ import annotations

import os
from urllib.parse import urlparse

from ._http import request_json
from .base import AIProvider, ChatResponse, Message, ProviderError


class OpenAICompatibleProvider(AIProvider):
    def __init__(
        self,
        api_key: str,
        model: str,
        *,
        base_url: str = "https://api.openai.com/v1",
        timeout: float = 30,
        name: str = "openai",
    ):
        if not api_key:
            raise ProviderError(f"{name} requires an API key in the server environment")
        parsed = urlparse(base_url)
        if parsed.scheme != "https" and parsed.hostname not in {"localhost", "127.0.0.1", "::1"}:
            raise ProviderError("Custom provider URL must use HTTPS (except on loopback)")
        self.api_key = api_key
        self.model = model
        self.base_url = base_url.rstrip("/")
        self.timeout = timeout
        self.name = name

    def generate(self, messages: list[Message], system_prompt: str | None = None) -> ChatResponse:
        request_messages = list(messages)
        if system_prompt:
            request_messages.insert(0, {"role": "system", "content": system_prompt})
        result = request_json(
            "POST",
            f"{self.base_url}/chat/completions",
            headers={"Authorization": f"Bearer {self.api_key}"},
            payload={"model": self.model, "messages": request_messages},
            timeout=self.timeout,
        )
        try:
            content = result["choices"][0]["message"]["content"]
        except (KeyError, IndexError, TypeError) as exc:
            raise ProviderError("OpenAI-compatible response did not contain message content") from exc
        if not isinstance(content, str):
            raise ProviderError("OpenAI-compatible message content was not text")
        return ChatResponse(content, str(result.get("model", self.model)), result.get("usage", {}))


class OpenAIProvider(OpenAICompatibleProvider):
    def __init__(self, model: str, timeout: float = 30):
        super().__init__(
            os.getenv("OPENAI_API_KEY", ""),
            model,
            base_url="https://api.openai.com/v1",
            timeout=timeout,
            name="openai",
        )
