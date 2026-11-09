"""Provider-neutral chat types, capabilities, and normalized errors."""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any


Message = dict[str, str]


@dataclass
class ChatResponse:
    content: str
    model: str
    usage: dict[str, Any] = field(default_factory=dict)
    truncated: bool = False
    finish_reason: str | None = None


class ProviderError(RuntimeError):
    """A bounded provider error that never intentionally includes credentials."""

    def __init__(
        self,
        message: str,
        *,
        category: str = "provider_error",
        status: int | None = None,
        retryable: bool = False,
        retry_after: int | None = None,
    ):
        super().__init__(message)
        self.category = category
        self.status = status
        self.retryable = retryable
        self.retry_after = retry_after


class AIProvider(ABC):
    name: str
    model: str

    @abstractmethod
    def generate(self, messages: list[Message], system_prompt: str | None = None) -> ChatResponse:
        """Generate one assistant response from an authorized conversation."""

    def capabilities(self) -> dict:
        return {
            "chat": True,
            "system_prompt": True,
            "usage": True,
            "streaming": False,
            "connection_test": "model-get",
        }

    def test_connection(self) -> dict:
        raise ProviderError(
            f"{self.name} does not support connection testing",
            category="unsupported_operation",
        )
