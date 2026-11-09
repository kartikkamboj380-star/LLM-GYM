"""Small standard-library JSON HTTP helper shared by provider adapters."""

from __future__ import annotations

import json
import os
import urllib.error
import urllib.request
from typing import Any

from .base import ProviderError


def redact_secrets(text: str) -> str:
    redacted = text
    for name, value in os.environ.items():
        if value and len(value) >= 6 and any(part in name.upper() for part in ("KEY", "TOKEN", "SECRET", "PASSWORD")):
            redacted = redacted.replace(value, "[redacted]")
    return redacted


def request_json(
    method: str,
    url: str,
    *,
    headers: dict[str, str] | None = None,
    payload: dict[str, Any] | None = None,
    timeout: float = 30,
) -> dict[str, Any]:
    body = json.dumps(payload).encode("utf-8") if payload is not None else None
    request = urllib.request.Request(
        url,
        data=body,
        method=method,
        headers={"Accept": "application/json", "Content-Type": "application/json", **(headers or {})},
    )
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            raw = response.read().decode("utf-8")
    except urllib.error.HTTPError as exc:
        # Keep upstream detail useful but bounded; credentials are never placed in URLs.
        detail = exc.read().decode("utf-8", errors="replace")[:500]
        try:
            parsed = json.loads(detail)
            detail = str(parsed.get("error", parsed))[:500]
        except (json.JSONDecodeError, TypeError):
            pass
        raise ProviderError(redact_secrets(f"Provider returned HTTP {exc.code}: {detail}")) from exc
    except (urllib.error.URLError, TimeoutError, OSError) as exc:
        raise ProviderError(redact_secrets(f"Provider network error: {exc.reason if hasattr(exc, 'reason') else exc}")) from exc
    try:
        result = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise ProviderError("Provider returned invalid JSON") from exc
    if not isinstance(result, dict):
        raise ProviderError("Provider returned an unexpected response")
    return result
