"""Provider selection and non-secret configuration status."""

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
            raise ProviderError("openai-compatible requires OPENAI_COMPATIBLE_BASE_URL")
        return OpenAICompatibleProvider(
            os.getenv("OPENAI_COMPATIBLE_API_KEY", ""),
            settings.compatible_model,
            base_url=settings.compatible_base_url,
            timeout=settings.request_timeout,
            name=normalized,
        )
    raise ProviderError(f"Unknown provider: {normalized}. Choose from {', '.join(PROVIDER_NAMES)}")


def available_providers(settings: Settings) -> list[dict]:
    """Expose configuration booleans and model names, never secret values."""

    return [
        {"id": "mock", "label": "Offline mock", "configured": True, "model": "mock-1", "external": False},
        {"id": "openai", "label": "OpenAI GPT", "configured": bool(os.getenv("OPENAI_API_KEY")), "model": settings.openai_model, "external": True},
        {"id": "anthropic", "label": "Anthropic Claude", "configured": bool(os.getenv("ANTHROPIC_API_KEY")), "model": settings.anthropic_model, "external": True},
        {"id": "gemini", "label": "Google Gemini", "configured": bool(os.getenv("GEMINI_API_KEY")), "model": settings.gemini_model, "external": True},
        {
            "id": "openai-compatible",
            "label": "OpenAI-compatible",
            "configured": bool(os.getenv("OPENAI_COMPATIBLE_API_KEY") and settings.compatible_base_url),
            "model": settings.compatible_model,
            "external": True,
        },
    ]
