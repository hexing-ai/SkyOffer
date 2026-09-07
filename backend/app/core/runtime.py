from __future__ import annotations

import asyncio
import time
from collections import defaultdict, deque
from collections.abc import Callable
from dataclasses import dataclass

from fastapi import Request


PROTECTED_POST_PATHS = frozenset(
    {
        "/api/v1/profile-analysis",
        "/api/v1/selection-advice",
    }
)


@dataclass(frozen=True, slots=True)
class RateLimitDecision:
    allowed: bool
    remaining: int
    retry_after_seconds: int


class InMemoryRateLimiter:
    """Small single-instance limiter for the public Beta model endpoints."""

    def __init__(
        self,
        *,
        requests: int,
        window_seconds: int,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        self.requests = requests
        self.window_seconds = window_seconds
        self.clock = clock
        self._events: dict[str, deque[float]] = defaultdict(deque)
        self._lock = asyncio.Lock()

    async def consume(self, key: str) -> RateLimitDecision:
        now = self.clock()
        cutoff = now - self.window_seconds
        async with self._lock:
            events = self._events[key]
            while events and events[0] <= cutoff:
                events.popleft()
            if len(events) >= self.requests:
                retry_after = max(1, int(self.window_seconds - (now - events[0]) + 0.999))
                return RateLimitDecision(False, 0, retry_after)
            events.append(now)
            return RateLimitDecision(True, self.requests - len(events), 0)


def request_client_key(request: Request, *, trust_proxy_headers: bool) -> str:
    if trust_proxy_headers:
        forwarded = request.headers.get("x-forwarded-for", "")
        first = forwarded.split(",", 1)[0].strip()
        if first:
            return first
    return request.client.host if request.client else "unknown"
