from __future__ import annotations

import time
from collections import OrderedDict, deque
from threading import Lock


class InMemoryRateLimiter:
    """Single-process sliding-window limiter with bounded key storage."""

    def __init__(
        self,
        limit: int = 60,
        window_seconds: int = 60,
        max_keys: int = 10_000,
    ) -> None:
        if limit < 1 or window_seconds < 1 or max_keys < 1:
            raise ValueError("Rate limiter settings must be positive.")
        self.limit = limit
        self.window_seconds = window_seconds
        self.max_keys = max_keys
        self._events: OrderedDict[str, deque[float]] = OrderedDict()
        self._lock = Lock()
        self._last_cleanup = 0.0
        self._cleanup_interval = min(float(window_seconds), 60.0)

    def _cleanup_expired_keys(self, now: float) -> None:
        cutoff = now - self.window_seconds
        expired_keys = []
        for key, events in self._events.items():
            while events and events[0] <= cutoff:
                events.popleft()
            if not events:
                expired_keys.append(key)
        for key in expired_keys:
            del self._events[key]
        self._last_cleanup = now

    def allow(self, key: str) -> bool:
        if not isinstance(key, str) or not key or len(key) > 256:
            return False

        now = time.monotonic()
        cutoff = now - self.window_seconds
        with self._lock:
            if now - self._last_cleanup >= self._cleanup_interval:
                self._cleanup_expired_keys(now)

            events = self._events.get(key)
            if events is None:
                if len(self._events) >= self.max_keys:
                    self._events.popitem(last=False)
                events = deque()
                self._events[key] = events
            else:
                self._events.move_to_end(key)

            while events and events[0] <= cutoff:
                events.popleft()
            if len(events) >= self.limit:
                return False
            events.append(now)
            return True


rate_limiter = InMemoryRateLimiter()
session_creation_limiter = InMemoryRateLimiter(
    limit=10,
    window_seconds=60,
    max_keys=10_000,
)
