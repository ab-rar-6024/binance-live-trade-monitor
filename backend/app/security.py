"""Small protections for running the API anywhere other than your own PC: request and connection limits."""

import os
import threading
import time
from collections import defaultdict, deque
from typing import Deque, Dict, Optional

TRUST_PROXY = os.environ.get("API_TRUST_PROXY", "0") == "1"


class RateLimiter:
    """At most `limit` requests per `window` seconds for each key (sliding window). A limit of 0 turns it off."""

    def __init__(self, limit: int, window: float = 60.0) -> None:
        self.limit, self.window = limit, window
        self._hits: Dict[str, Deque[float]] = defaultdict(deque)
        self._lock = threading.Lock()

    def allow(self, key: str, now: Optional[float] = None) -> bool:
        if self.limit <= 0:
            return True
        now = time.monotonic() if now is None else now
        with self._lock:
            hits = self._hits[key]
            while hits and now - hits[0] > self.window:
                hits.popleft()
            if len(hits) >= self.limit:
                return False
            hits.append(now)
            if len(self._hits) > 5000:  # forget idle clients so memory cannot grow without bound
                for k in [k for k, v in self._hits.items() if not v or now - v[-1] > self.window]:
                    del self._hits[k]
            return True


class ConnectionLimiter:
    """At most `limit` open connections (WebSockets) per key."""

    def __init__(self, limit: int) -> None:
        self.limit = limit
        self._open: Dict[str, int] = defaultdict(int)
        self._lock = threading.Lock()

    def acquire(self, key: str) -> bool:
        with self._lock:
            if self.limit > 0 and self._open[key] >= self.limit:
                return False
            self._open[key] += 1
            return True

    def release(self, key: str) -> None:
        with self._lock:
            self._open[key] = max(0, self._open[key] - 1)
            if self._open[key] == 0:
                del self._open[key]


def client_ip(scope_client, forwarded_for: Optional[str]) -> str:
    """The caller's address. X-Forwarded-For is only believed when API_TRUST_PROXY=1 (i.e. behind your own proxy)."""
    if TRUST_PROXY and forwarded_for:
        return forwarded_for.split(",")[0].strip()
    return scope_client[0] if scope_client else "unknown"
