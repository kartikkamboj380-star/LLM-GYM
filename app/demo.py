"""Independent local registration demo for authorized end-to-end testing."""

from __future__ import annotations

import re
import secrets
import threading
import uuid
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone

from .email import MockEmailProvider


@dataclass
class DemoSession:
    id: str
    inbox_id: str
    code: str
    expires_at: datetime
    status: str = "waiting"
    attempts: int = 0


class RegistrationDemo:
    def __init__(self, email: MockEmailProvider, code_factory=None):
        self.email = email
        self.code_factory = code_factory or (lambda: "".join(secrets.choice("0123456789") for _ in range(6)))
        self._sessions: dict[str, DemoSession] = {}
        self._lock = threading.Lock()

    @staticmethod
    def _now() -> datetime:
        return datetime.now(timezone.utc)

    def start(self, address: str, inbox_id: str, scenario: str = "valid") -> dict:
        address = address.strip()
        if len(address) > 254 or not re.fullmatch(r"[^\s@]+@[^\s@]+\.[^\s@]+", address):
            raise ValueError("Enter a valid email address")
        if scenario not in {"valid", "expired"}:
            raise ValueError("Demo scenario must be valid or expired")
        inbox = self.email.get_inbox(inbox_id)
        if inbox.status == "expired":
            raise ValueError("The mock inbox is expired")
        if inbox.address.casefold() != address.casefold():
            raise ValueError("Email must match the selected mock inbox")
        session_id = str(uuid.uuid4())
        code = self.code_factory()
        expires = self._now() + timedelta(seconds=300)
        message = self.email.send_message(
            inbox_id,
            "demo@example.test",
            "LLM-GYM Local Demo",
            f"LLM-GYM Local Demo test run {session_id}: Your verification code is {code}. It expires in 5 minutes.",
        )
        if scenario == "expired":
            expires = self._now() - timedelta(seconds=1)
            message.expires_at = expires.isoformat(timespec="milliseconds").replace("+00:00", "Z")
        session = DemoSession(session_id, inbox_id, code, expires)
        with self._lock:
            self._sessions[session_id] = session
        return {
            "session_id": session_id,
            "status": session.status,
            "expires_at": expires.isoformat(timespec="milliseconds").replace("+00:00", "Z"),
            "scenario": scenario,
        }

    def verify(self, session_id: str, code: str) -> dict:
        if not isinstance(code, str) or not re.fullmatch(r"\d{6}", code):
            raise ValueError("Enter the six-digit demo code")
        with self._lock:
            session = self._sessions.get(session_id)
            if session is None:
                raise KeyError("Demo session not found")
            if session.status == "verified":
                return {"status": "verified", "attempts_remaining": 3 - session.attempts}
            if self._now() >= session.expires_at:
                session.status = "expired"
                session.code = ""
                return {"status": "expired", "attempts_remaining": 0}
            if session.status == "failed":
                return {"status": "failed", "attempts_remaining": 0}
            session.attempts += 1
            if secrets.compare_digest(session.code, code):
                session.status = "verified"
                session.code = ""
                return {"status": "verified", "attempts_remaining": 3 - session.attempts}
            if session.attempts >= 3:
                session.status = "failed"
            return {
                "status": "failed" if session.status == "failed" else "invalid",
                "attempts_remaining": max(0, 3 - session.attempts),
            }

    def cleanup(self, session_id: str) -> dict:
        with self._lock:
            session = self._sessions.pop(session_id, None)
        if session is None:
            raise KeyError("Demo session not found")
        try:
            self.email.delete_inbox(session.inbox_id)
            inbox_deleted = True
        except KeyError:
            inbox_deleted = False
        return {"cleaned": True, "inbox_deleted": inbox_deleted}
