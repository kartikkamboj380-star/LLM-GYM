"""In-memory, reserved-domain email simulator. It never sends real email."""

from __future__ import annotations

import secrets
import string
import threading
import uuid
from datetime import datetime, timezone

from .base import EmailMessage, EmailProvider, Inbox


class MockEmailProvider(EmailProvider):
    name = "mock"

    def __init__(self):
        self._inboxes: dict[str, Inbox] = {}
        self._messages: dict[str, list[EmailMessage]] = {}
        self._condition = threading.Condition()

    @staticmethod
    def _now() -> str:
        return datetime.now(timezone.utc).isoformat(timespec="milliseconds").replace("+00:00", "Z")

    def create_inbox(self) -> Inbox:
        inbox = Inbox(
            id=str(uuid.uuid4()),
            address=f"test-{uuid.uuid4().hex[:10]}@example.test",
            provider=self.name,
            created_at=self._now(),
        )
        with self._condition:
            self._inboxes[inbox.id] = inbox
            self._messages[inbox.id] = []
        return inbox

    def send_message(self, inbox_id: str, sender: str, subject: str, text: str) -> EmailMessage:
        if not text.strip() and not subject.strip():
            raise ValueError("A mock message needs a subject or body")
        message = EmailMessage(
            id=str(uuid.uuid4()),
            inbox_id=inbox_id,
            sender=sender.strip()[:200] or "tests@example.test",
            subject=subject.strip()[:300],
            text=text.strip()[:20_000],
            received_at=self._now(),
        )
        with self._condition:
            if inbox_id not in self._inboxes:
                raise KeyError("Mock inbox not found")
            self._messages[inbox_id].insert(0, message)
            self._condition.notify_all()
        return message

    def send_demo_verification(self, inbox_id: str, code_type: str = "numeric") -> EmailMessage:
        if code_type == "numeric":
            code = "".join(secrets.choice(string.digits) for _ in range(6))
        elif code_type == "alphanumeric":
            alphabet = "ABCDEFGHJKLMNPQRSTUVWXYZ23456789"
            code = "T" + "".join(secrets.choice(alphabet) for _ in range(5))
        else:
            raise ValueError("Code type must be numeric or alphanumeric")
        return self.send_message(
            inbox_id,
            "verification@example.test",
            "LLM-GYM local test",
            f"Your verification code is {code}. This simulated code expires in 10 minutes. No real email was sent.",
        )

    def get_messages(self, inbox_id: str) -> list[EmailMessage]:
        with self._condition:
            if inbox_id not in self._inboxes:
                raise KeyError("Mock inbox not found")
            return list(self._messages[inbox_id])
