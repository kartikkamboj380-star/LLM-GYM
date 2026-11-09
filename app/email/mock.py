"""In-memory lifecycle-complete email simulator. It never sends real email."""

from __future__ import annotations

import re
import secrets
import string
import threading
import uuid
from datetime import datetime, timedelta, timezone

from app.providers.base import ProviderError

from .base import EmailMessage, EmailProvider, EmailProviderRateLimit, Inbox
from .parser import ExpiredCodeError


class MockEmailProvider(EmailProvider):
    name = "mock"
    FAILURE_MODES = {"none", "provider_error", "rate_limit", "timeout"}

    def __init__(self):
        self._inboxes: dict[str, Inbox] = {}
        self._messages: dict[str, list[EmailMessage]] = {}
        self._failure_modes: dict[str, str] = {}
        self._cancel_events: dict[str, threading.Event] = {}
        self._condition = threading.Condition()

    @staticmethod
    def _datetime_now() -> datetime:
        return datetime.now(timezone.utc)

    @classmethod
    def _now(cls) -> str:
        return cls._format_time(cls._datetime_now())

    @staticmethod
    def _format_time(value: datetime) -> str:
        return value.isoformat(timespec="milliseconds").replace("+00:00", "Z")

    def capabilities(self) -> dict:
        return {
            "create": True,
            "inbox_info": True,
            "list_messages": True,
            "get_message": True,
            "delete": True,
            "expiration": True,
            "cancellation": True,
            "failure_simulation": sorted(self.FAILURE_MODES),
            "rate_limit_simulation": True,
            "real_delivery": False,
            "default_ttl_seconds": 900,
        }

    def health(self) -> dict:
        degraded = any(mode == "provider_error" for mode in self._failure_modes.values())
        return {"provider": self.name, "status": "degraded" if degraded else "ok", "external": False, "real_delivery": False}

    def create_inbox(self, ttl_seconds: int = 900, local_part: str | None = None) -> Inbox:
        if not 0 <= ttl_seconds <= 86400:
            raise ValueError("Mock inbox TTL must be between 0 and 86400 seconds")
        if local_part is None:
            local_part = f"test-{uuid.uuid4().hex[:10]}"
        if not re.fullmatch(r"[a-z0-9][a-z0-9._-]{0,63}", local_part):
            raise ValueError("Mock local part must use 1-64 lowercase letters, digits, dot, underscore, or dash")
        created = self._datetime_now()
        inbox = Inbox(
            id=str(uuid.uuid4()),
            address=f"{local_part}@example.test",
            provider=self.name,
            created_at=self._format_time(created),
            expires_at=self._format_time(created + timedelta(seconds=ttl_seconds)),
            status="created",
        )
        with self._condition:
            self._inboxes[inbox.id] = inbox
            self._messages[inbox.id] = []
            self._failure_modes[inbox.id] = "none"
        return inbox

    def get_inbox(self, inbox_id: str) -> Inbox:
        with self._condition:
            inbox = self._require_inbox(inbox_id)
            if inbox.expires_at and datetime.fromisoformat(inbox.expires_at.replace("Z", "+00:00")) <= self._datetime_now():
                inbox.status = "expired"
            elif inbox.status != "waiting":
                inbox.status = "message_received" if self._messages[inbox_id] else "active"
            return inbox

    def _require_inbox(self, inbox_id: str) -> Inbox:
        if inbox_id not in self._inboxes:
            raise KeyError("Mock inbox not found")
        return self._inboxes[inbox_id]

    def send_message(
        self,
        inbox_id: str,
        sender: str,
        subject: str,
        text: str,
        *,
        html: str | None = None,
        ttl_seconds: int = 600,
    ) -> EmailMessage:
        if not text.strip() and not subject.strip() and not (html or "").strip():
            raise ValueError("A mock message needs a subject, text, or HTML body")
        if not 1 <= ttl_seconds <= 86400:
            raise ValueError("Mock message TTL must be between 1 and 86400 seconds")
        received = self._datetime_now()
        message = EmailMessage(
            id=str(uuid.uuid4()),
            inbox_id=inbox_id,
            sender=sender.strip()[:200] or "tests@example.test",
            subject=subject.strip()[:300],
            text=text.strip()[:20_000],
            received_at=self._format_time(received),
            expires_at=self._format_time(received + timedelta(seconds=ttl_seconds)),
            html=html.strip()[:20_000] if html else None,
        )
        with self._condition:
            inbox = self._require_inbox(inbox_id)
            if self.get_inbox(inbox_id).status == "expired":
                raise ExpiredCodeError("Cannot deliver to an expired mock inbox") from None
            self._messages[inbox_id].insert(0, message)
            inbox.status = "message_received"
            self._condition.notify_all()
        return message

    def send_demo_verification(self, inbox_id: str, code_type: str = "numeric", *, html: bool = False) -> EmailMessage:
        if code_type == "numeric":
            code = "".join(secrets.choice(string.digits) for _ in range(6))
        elif code_type == "alphanumeric":
            alphabet = "ABCDEFGHJKLMNPQRSTUVWXYZ23456789"
            characters = [secrets.choice(alphabet) for _ in range(5)]
            if not any(character.isdigit() for character in characters):
                characters[secrets.randbelow(len(characters))] = secrets.choice(string.digits)
            code = "T" + "".join(characters)
        else:
            raise ValueError("Code type must be numeric or alphanumeric")
        text = f"Your verification code is {code}. This simulated code expires in 10 minutes. No real email was sent."
        return self.send_message(
            inbox_id,
            "verification@example.test",
            "LLM-GYM local test",
            text if not html else "",
            html=f"<html><body><p>{text}</p></body></html>" if html else None,
        )

    def get_messages(self, inbox_id: str) -> list[EmailMessage]:
        with self._condition:
            self._require_inbox(inbox_id)
            if self.get_inbox(inbox_id).status == "expired":
                return list(self._messages[inbox_id])
            mode = self._failure_modes[inbox_id]
            if mode == "provider_error":
                raise ProviderError("Simulated mock provider failure")
            if mode == "rate_limit":
                raise EmailProviderRateLimit(1)
            if mode == "timeout":
                return []
            return list(self._messages[inbox_id])

    def set_failure_mode(self, inbox_id: str, mode: str) -> dict:
        if mode not in self.FAILURE_MODES:
            raise ValueError(f"Failure mode must be one of {', '.join(sorted(self.FAILURE_MODES))}")
        with self._condition:
            self._require_inbox(inbox_id)
            self._failure_modes[inbox_id] = mode
        return {"inbox_id": inbox_id, "failure_mode": mode}

    def cancel_poll(self, inbox_id: str) -> bool:
        with self._condition:
            self._require_inbox(inbox_id)
            event = self._cancel_events.get(inbox_id)
            if event:
                event.set()
                return True
            return False

    def poll_for_code(self, inbox_id: str, **kwargs) -> dict:
        event = threading.Event()
        with self._condition:
            self._require_inbox(inbox_id)
            self._cancel_events[inbox_id] = event
            if self.get_inbox(inbox_id).status != "expired":
                self._inboxes[inbox_id].status = "waiting"
        try:
            return super().poll_for_code(inbox_id, cancel_event=event, **kwargs)
        finally:
            with self._condition:
                self._cancel_events.pop(inbox_id, None)
                if inbox_id in self._inboxes:
                    self._inboxes[inbox_id].status = "active"
                    self.get_inbox(inbox_id)

    def delete_inbox(self, inbox_id: str) -> Inbox:
        with self._condition:
            inbox = self._require_inbox(inbox_id)
            inbox.status = "deleted"
            self.cancel_poll(inbox_id)
            self._messages.pop(inbox_id, None)
            self._failure_modes.pop(inbox_id, None)
            self._inboxes.pop(inbox_id, None)
            return inbox
