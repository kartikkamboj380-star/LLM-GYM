"""Google Gemini generateContent adapter (server-side credentials only)."""

from __future__ import annotations

import os
from urllib.parse import quote

from ._http import request_json
from .base import AIProvider, ChatResponse, Message, ProviderError


class GeminiProvider(AIProvider):
    name = "gemini"

    def __init__(self, model: str, timeout: float = 30):
        self.api_key = os.getenv("GEMINI_API_KEY", "")
        if not self.api_key:
            raise ProviderError("gemini requires GEMINI_API_KEY in the server environment")
        self.model = model
        self.timeout = timeout

    def generate(self, messages: list[Message], system_prompt: str | None = None) -> ChatResponse:
        contents = [
            {
                "role": "model" if message["role"] == "assistant" else "user",
                "parts": [{"text": message["content"]}],
            }
            for message in messages
            if message["role"] in {"user", "assistant"}
        ]
        payload: dict = {"contents": contents}
        if system_prompt:
            payload["systemInstruction"] = {"parts": [{"text": system_prompt}]}
        model_path = quote(self.model, safe="")
        result = request_json(
            "POST",
            f"https://generativelanguage.googleapis.com/v1beta/models/{model_path}:generateContent",
            headers={"x-goog-api-key": self.api_key},
            payload=payload,
            timeout=self.timeout,
        )
        try:
            content = "\n".join(
                part["text"]
                for candidate in result["candidates"][:1]
                for part in candidate["content"]["parts"]
                if "text" in part
            )
        except (KeyError, IndexError, TypeError) as exc:
            raise ProviderError("Gemini response did not contain text content") from exc
        if not content:
            raise ProviderError("Gemini returned no text (it may have blocked the response)")
        return ChatResponse(content, self.model, result.get("usageMetadata", {}))
