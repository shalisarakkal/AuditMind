"""Process-local admission: sign-ins and pre-body uploads per client address.

Kept in memory, so per web-server process: with several processes each
counts its own. A shared store (the database) would be needed for that.
"""

import threading
import time
from collections import deque
from collections.abc import Callable

from app.core.config import settings


class SlidingWindowLimiter:
    def __init__(self, limit: Callable[[], int], window_seconds: float = 60, clock=time.monotonic,
                 max_keys: int = 10_000):
        self._limit, self._window, self._clock = limit, window_seconds, clock
        self._max_keys = max_keys
        self._hits: dict[str, deque[float]] = {}
        self._lock = threading.Lock()

    def hit(self, key: str) -> int | None:
        """Count an attempt; None if it's allowed, else the seconds until
        the next one is (for Retry-After)."""
        now = self._clock()
        with self._lock:
            if key not in self._hits and len(self._hits) >= self._max_keys:
                for stale in [k for k, v in self._hits.items() if not v or v[-1] <= now - self._window]:
                    del self._hits[stale]
                # Never evict live buckets (which would reset their limits) or
                # grow without bound under an address/key-cardinality attack.
                if len(self._hits) >= self._max_keys:
                    return max(1, int(self._window) + 1)
            hits = self._hits.setdefault(key, deque())
            while hits and hits[0] <= now - self._window:
                hits.popleft()
            if len(hits) >= self._limit():
                return max(1, int(hits[0] + self._window - now) + 1)
            hits.append(now)
            return None

    def reset(self) -> None:
        with self._lock:
            self._hits.clear()


login_limiter = SlidingWindowLimiter(lambda: settings.LOGIN_RATE_LIMIT_PER_MINUTE)
upload_limiter = SlidingWindowLimiter(lambda: settings.UPLOAD_RATE_LIMIT_PER_MINUTE)
