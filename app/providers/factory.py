"""Provider selection and non-secret configuration/capability status."""

from __future__ import annotations

import os

from app.config import Settings

from .anthropic import AnthropicProvider
from .base import AIProvider, ProviderError
from .gemini import GeminiProvider
from .mock import MockProvider
from .openai_compatible import OpenAICompatibleProvider, OpenAIProvider


PROVIDER_NAMES = ("mock", "openai", "anthropic", "gemini", "openai-compatible")


def create_provider(name: str, settings: Settings) -> AIProvider:
    normalized = name.strip().lower()
    if normalized == "mock":
        return MockProvider()
    if normalized == "openai":
        return OpenAIProvider(settings.openai_model, settings.request_timeout)
    if normalized == "anthropic":
        return AnthropicProvider(settings.anthropic_model, settings.request_timeout)
    if normalized == "gemini":
        return GeminiProvider(settings.gemini_model, settings.request_timeout)
    if normalized == "openai-compatible":
        if not settings.compatible_base_url:
            raise ProviderError("openai-compatible requires OPENAI_COMPATIBLE_BASE_URL", category="missing_configuration")
        return OpenAICompatibleProvider(
            os.getenv("OPENAI_COMPATIBLE_API_KEY", ""),
            settings.compatible_model,
            base_url=settings.compatible_base_url,
            timeout=settings.request_timeout,
            name=normalized,
        )
    raise ProviderError(f"Unknown provider: {normalized}. Choose from {', '.join(PROVIDER_NAMES)}", category="unsupported_operation")


def available_providers(settings: Settings) -> list[dict]:
    """Expose configuration booleans/model names/capabilities, never secrets."""

    def item(identifier: str, label: str, configured: bool, model: str, external: bool) -> dict:
        return {
            "id": identifier,
            "label": label,
            "configured": configured,
            "model": model,
            "external": external,
            "connection_status": "not_tested",
            "capabilities": {
                "chat": True,
                "system_prompt": True,
                "usage": True,
                "streaming": False,
                "connection_test": "local" if identifier == "mock" else "model-get",
            },
        }

    return [
        item("mock", "Offline mock", True, "mock-1", False),
        item("openai", "OpenAI GPT", bool(os.getenv("OPENAI_API_KEY")), settings.openai_model, True),
        item("anthropic", "Anthropic Claude", bool(os.getenv("ANTHROPIC_API_KEY")), settings.anthropic_model, True),
        item("gemini", "Google Gemini", bool(os.getenv("GEMINI_API_KEY")), settings.gemini_model, True),
        item(
            "openai-compatible",
            "OpenAI-compatible",
            bool(os.getenv("OPENAI_COMPATIBLE_API_KEY") and settings.compatible_base_url),
            settings.compatible_model,
            True,
        ),
    ]
