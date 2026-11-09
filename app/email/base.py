"""Provider-neutral inbox types, capabilities, and bounded OTP polling."""

from __future__ import annotations

import threading
import time
from abc import ABC, abstractmethod
from dataclasses import asdict, dataclass
from typing import Any

from app.providers.base import ProviderError

from .parser import AmbiguousCodeError, ExpiredCodeError, OTPRules, VerificationCodeParser


@dataclass
class Inbox:
    id: str
    address: str
    provider: str
    created_at: str
    expires_at: str | None = None
    status: str = "created"

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
    expires_at: str | None = None
    html: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    def sanitized_dict(self) -> dict[str, Any]:
        """Metadata for reports; never include body or a parsed OTP."""

        return {
            "id": self.id,
            "inbox_id": self.inbox_id,
            "sender": self.sender,
            "subject": self.subject,
            "received_at": self.received_at,
            "expires_at": self.expires_at,
        }


def sanitize_poll_result(result: dict) -> dict:
    """Create a report-safe result with metadata only and no OTP/body content."""

    return {
        "status": result.get("status", "unknown"),
        "code_detected": bool(result.get("found")),
        "attempts": result.get("attempts", 0),
        "messages": [
            {
                "id": message.get("id"),
                "sender": message.get("sender"),
                "subject": message.get("subject"),
                "received_at": message.get("received_at"),
                "expires_at": message.get("expires_at"),
            }
            for message in result.get("messages", [])
        ],
        "error": VerificationCodeParser.redact(str(result.get("error", ""))),
    }


class EmailProviderRateLimit(ProviderError):
    def __init__(self, retry_after: int = 1):
        super().__init__(f"Email provider rate limit reached; retry in {retry_after} second(s)")
        self.retry_after = retry_after


class EmailProvider(ABC):
    name: str

    @abstractmethod
    def create_inbox(self) -> Inbox:
        """Create one authorized test inbox, subject to provider rules."""

    @abstractmethod
    def get_messages(self, inbox_id: str) -> list[EmailMessage]:
        """Return messages newest first."""

    def capabilities(self) -> dict:
        return {"create": True, "list_messages": True, "delete": False, "expiration": False, "real_delivery": False}

    def health(self) -> dict:
        return {"provider": self.name, "status": "unknown", "external": False}

    def get_inbox(self, inbox_id: str) -> Inbox:
        raise ProviderError(f"{self.name} does not support inbox information")

    def get_message(self, inbox_id: str, message_id: str) -> EmailMessage:
        for message in self.get_messages(inbox_id):
            if message.id == message_id:
                return message
        raise KeyError("Email message not found")

    def delete_inbox(self, inbox_id: str) -> Inbox:
        raise ProviderError(f"{self.name} does not support inbox deletion")

    @staticmethod
    def _result(status: str, messages: list[EmailMessage], attempts: int, **extra: Any) -> dict:
        result = {
            "found": status == "verified",
            "status": status,
            "code": None,
            "attempts": attempts,
            "messages": [item.to_dict() for item in messages],
        }
        result.update(extra)
        return result

    def poll_for_code(
        self,
        inbox_id: str,
        *,
        timeout_seconds: float = 15,
        interval_seconds: float = 1,
        backoff_multiplier: float = 1.0,
        cancel_event: threading.Event | None = None,
        parser: VerificationCodeParser | None = None,
        rules: OTPRules | None = None,
    ) -> dict:
        if not 0 <= timeout_seconds <= 60:
            raise ValueError("Email poll timeout must be between 0 and 60 seconds")
        if not 0.1 <= interval_seconds <= 10:
            raise ValueError("Email poll interval must be between 0.1 and 10 seconds")
        if not 1 <= backoff_multiplier <= 2:
            raise ValueError("Email poll backoff must be between 1 and 2")
        code_parser = parser or VerificationCodeParser()
        deadline = time.monotonic() + timeout_seconds
        interval = interval_seconds
        attempts = 0
        messages: list[EmailMessage] = []
        if self.capabilities().get("expiration"):
            inbox = self.get_inbox(inbox_id)
            if inbox.status == "expired":
                return self._result("expired", messages, attempts, error="Inbox expired before polling")
        while True:
            if cancel_event and cancel_event.is_set():
                return self._result("cancelled", messages, attempts, error="Polling cancelled")
            attempts += 1
            messages = self.get_messages(inbox_id)
            matches: list[tuple[str, str]] = []
            expired_match = False
            ambiguous_message = False
            for message in messages:
                try:
                    code = code_parser.extract_from_message(message, rules)
                except AmbiguousCodeError:
                    ambiguous_message = True
                    continue
                except ExpiredCodeError:
                    expired_match = True
                    continue
                if code:
                    matches.append((code, message.id))
            distinct_codes = {code for code, _ in matches}
            if len(distinct_codes) > 1 or ambiguous_message:
                return self._result("ambiguous", messages, attempts, error="Multiple codes found; refine the OTP rules")
            if matches:
                code, message_id = matches[0]
                return self._result("verified", messages, attempts, code=code, message_id=message_id)
            if expired_match:
                return self._result("expired", messages, attempts, error="The matching message or code expired")
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                status = "not_found" if timeout_seconds == 0 else "timeout"
                return self._result(status, messages, attempts, error="No unambiguous active verification code found")
            if cancel_event and cancel_event.wait(min(interval, remaining)):
                return self._result("cancelled", messages, attempts, error="Polling cancelled")
            interval = min(10, interval * backoff_multiplier)
