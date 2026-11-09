"""Configurable, context-aware OTP parsing with ambiguity and redaction controls."""

from __future__ import annotations

import re
import string
from dataclasses import dataclass
from datetime import datetime, timezone
from html.parser import HTMLParser
from typing import Any


class AmbiguousCodeError(ValueError):
    pass


class ExpiredCodeError(ValueError):
    pass


@dataclass(frozen=True)
class OTPRules:
    expected_length: int | None = None
    allowed_characters: str = string.ascii_uppercase + string.digits
    sender: str | None = None
    subject: str | None = None
    max_age_seconds: int = 600
    expected_application: str | None = None
    expected_test_run: str | None = None

    def __post_init__(self):
        if self.expected_length is not None and not 4 <= self.expected_length <= 12:
            raise ValueError("Expected OTP length must be between 4 and 12")
        if not self.allowed_characters or not 1 <= self.max_age_seconds <= 86400:
            raise ValueError("OTP allowed characters and age bounds are invalid")


class _TextExtractor(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.parts: list[str] = []
        self._ignored_depth = 0

    def handle_starttag(self, tag: str, attrs: list) -> None:
        if tag.lower() in {"script", "style"}:
            self._ignored_depth += 1
        elif tag.lower() in {"br", "p", "div", "li", "tr"}:
            self.parts.append(" ")

    def handle_endtag(self, tag: str) -> None:
        if tag.lower() in {"script", "style"} and self._ignored_depth:
            self._ignored_depth -= 1
        elif tag.lower() in {"p", "div", "li", "tr"}:
            self.parts.append(" ")

    def handle_data(self, data: str) -> None:
        if not self._ignored_depth:
            self.parts.append(data)


class VerificationCodeParser:
    # Candidates are considered only near authentication-related context.
    CONTEXT = re.compile(
        r"(?:verification|confirmation|security|one[- ]time|otp|login|access)"
        r"(?:\s+(?:code|token))?\s*(?:is|:|=|-)?\s*([A-Z0-9]{4,12})(?![A-Z0-9])",
        re.IGNORECASE,
    )

    @staticmethod
    def _text(value: str | bytes | None) -> str:
        if value is None:
            return ""
        if isinstance(value, bytes):
            try:
                return value.decode("utf-8")
            except UnicodeDecodeError as exc:
                raise ValueError("Message content is not valid UTF-8") from exc
        if not isinstance(value, str):
            raise ValueError("Message content must be text")
        return value

    @classmethod
    def html_to_text(cls, html: str | bytes) -> str:
        parser = _TextExtractor()
        parser.feed(cls._text(html))
        parser.close()
        return " ".join("".join(parser.parts).split())

    @staticmethod
    def _timestamp(value: str) -> datetime:
        try:
            parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
        except (ValueError, AttributeError) as exc:
            raise ValueError("Message timestamp is invalid") from exc
        return parsed.replace(tzinfo=timezone.utc) if parsed.tzinfo is None else parsed

    @staticmethod
    def redact(text: str) -> str:
        """Redact contextual OTP values from reports without selecting one."""

        def replace(match: re.Match) -> str:
            value = match.group(1)
            return match.group(0).replace(value, "[REDACTED]")

        return VerificationCodeParser.CONTEXT.sub(replace, text)

    def _valid_candidate(self, candidate: str, rules: OTPRules) -> bool:
        candidate = candidate.upper()
        if rules.expected_length is not None and len(candidate) != rules.expected_length:
            return False
        if any(character not in rules.allowed_characters.upper() for character in candidate):
            return False
        if candidate.isdigit():
            return 4 <= len(candidate) <= 8
        return (
            6 <= len(candidate) <= 10
            and any(character.isalpha() for character in candidate)
            and any(character.isdigit() for character in candidate)
        )

    def candidates(self, text: str | bytes, rules: OTPRules | None = None) -> list[str]:
        selected_rules = rules or OTPRules()
        content = self._text(text)
        # Deduplicate repeated delivery of the same value without hiding distinct codes.
        return list(dict.fromkeys(
            match.group(1).upper()
            for match in self.CONTEXT.finditer(content)
            if self._valid_candidate(match.group(1), selected_rules)
        ))

    def extract(
        self,
        text: str | bytes,
        html: str | bytes | None = None,
        rules: OTPRules | None = None,
    ) -> str | None:
        plain = self._text(text)
        if html:
            plain += "\n" + self.html_to_text(html)
        candidates = self.candidates(plain, rules)
        if len(candidates) > 1:
            raise AmbiguousCodeError("Multiple different verification codes found")
        return candidates[0] if candidates else None

    def extract_from_message(
        self,
        message: Any,
        rules: OTPRules | None = None,
        *,
        now: datetime | None = None,
    ) -> str | None:
        selected_rules = rules or OTPRules()
        if selected_rules.sender and message.sender.casefold() != selected_rules.sender.casefold():
            return None
        if selected_rules.subject and selected_rules.subject.casefold() not in message.subject.casefold():
            return None
        current = now or datetime.now(timezone.utc)
        combined = "\n".join((message.subject, self._text(message.text), self.html_to_text(message.html) if message.html else ""))
        for expected in (selected_rules.expected_application, selected_rules.expected_test_run):
            if expected and expected.casefold() not in combined.casefold():
                return None
        try:
            code = self.extract(message.subject + "\n" + message.text, message.html, selected_rules)
        except TypeError as exc:
            raise ValueError("Message content is malformed") from exc
        if not code:
            return None
        if message.expires_at and self._timestamp(message.expires_at) <= current:
            raise ExpiredCodeError("Message expired")
        if message.received_at and self._timestamp(message.received_at) <= current:
            age = (current - self._timestamp(message.received_at)).total_seconds()
            if age > selected_rules.max_age_seconds:
                raise ExpiredCodeError("Message exceeded the allowed OTP age")
        return code
