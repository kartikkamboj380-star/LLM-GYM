"""Small in-memory fixed-window limiter for a single-user local process."""

from __future__ import annotations

import math
import threading
import time
from collections import deque

from .errors import APIError


class InMemoryRateLimiter:
    def __init__(self):
        self._events: dict[str, deque[float]] = {}
        self._lock = threading.Lock()

    def enforce(self, bucket: str, identity: str, limit: int, window_seconds: float) -> None:
        if limit < 1 or not 1 <= window_seconds <= 3600:
            raise ValueError("Rate-limit configuration is invalid")
        now = time.monotonic()
        key = f"{bucket}:{identity}"
        with self._lock:
            events = self._events.setdefault(key, deque())
            cutoff = now - window_seconds
            while events and events[0] <= cutoff:
                events.popleft()
            if len(events) >= limit:
                retry_after = max(1, math.ceil(events[0] + window_seconds - now))
                raise APIError(
                    429,
                    "RATE_LIMITED",
                    f"Too many {bucket} requests. Retry in {retry_after} seconds.",
                    retryable=True,
                    retry_after=retry_after,
                )
            events.append(now)
            # Prevent idle identities from growing process memory without bound.
            if len(self._events) > 1000:
                for idle_key in [item for item, values in self._events.items() if not values or values[-1] <= cutoff]:
                    self._events.pop(idle_key, None)
