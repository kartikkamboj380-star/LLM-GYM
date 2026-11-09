"""Provider-neutral chat types and errors."""

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


class ProviderError(RuntimeError):
    """A safe provider error that never intentionally includes credentials."""


class AIProvider(ABC):
    name: str

    @abstractmethod
    def generate(self, messages: list[Message], system_prompt: str | None = None) -> ChatResponse:
        """Generate one assistant response from an authorized conversation."""
