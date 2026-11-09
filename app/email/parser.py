"""Controlled extraction of numeric and mixed alphanumeric test codes."""

from __future__ import annotations

import re


class VerificationCodeParser:
    # A code must be near authentication-related context; arbitrary numbers are ignored.
    CONTEXT = re.compile(
        r"(?:verification|confirmation|security|one[- ]time|otp|login|access)"
        r"(?:\s+(?:code|token))?\s*(?:is|:|=|-)?\s*([A-Z0-9]{4,10})(?![A-Z0-9])",
        re.IGNORECASE,
    )

    def extract(self, text: str) -> str | None:
        if not text:
            return None
        for match in self.CONTEXT.finditer(text):
            candidate = match.group(1).upper()
            if candidate.isdigit() and 4 <= len(candidate) <= 8:
                return candidate
            if 6 <= len(candidate) <= 10 and candidate.isalnum() and any(c.isalpha() for c in candidate) and any(c.isdigit() for c in candidate):
                return candidate
        return None
