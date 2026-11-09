"""Provider-neutral inbox types and bounded polling."""

from __future__ import annotations

import time
from abc import ABC, abstractmethod
from dataclasses import asdict, dataclass
from typing import Any

from .parser import VerificationCodeParser


@dataclass
class Inbox:
    id: str
    address: str
    provider: str
    created_at: str

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class EmailMessage:
    id: str
    inbox_id: str
    sender: str
    subject: str
    text: str
    received_at: str

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


class EmailProvider(ABC):
    name: str

    @abstractmethod
    def create_inbox(self) -> Inbox:
        """Create one authorized test inbox, subject to provider rules."""

    @abstractmethod
    def get_messages(self, inbox_id: str) -> list[EmailMessage]:
        """Return messages newest first."""

    def poll_for_code(
        self,
        inbox_id: str,
        *,
        timeout_seconds: float = 15,
        interval_seconds: float = 1,
        parser: VerificationCodeParser | None = None,
    ) -> dict:
        if not 0 <= timeout_seconds <= 60:
            raise ValueError("Email poll timeout must be between 0 and 60 seconds")
        if not 0.1 <= interval_seconds <= 10:
            raise ValueError("Email poll interval must be between 0.1 and 10 seconds")
        code_parser = parser or VerificationCodeParser()
        deadline = time.monotonic() + timeout_seconds
        attempts = 0
        while True:
            attempts += 1
            messages = self.get_messages(inbox_id)
            for message in messages:
                code = code_parser.extract(message.text) or code_parser.extract(message.subject)
                if code:
                    return {
                        "found": True,
                        "code": code,
                        "message_id": message.id,
                        "attempts": attempts,
                        "messages": [item.to_dict() for item in messages],
                    }
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                return {"found": False, "code": None, "attempts": attempts, "messages": [item.to_dict() for item in messages]}
            # Polling backoff is bounded; it is not used to wait for UI elements.
            time.sleep(min(interval_seconds, remaining))
