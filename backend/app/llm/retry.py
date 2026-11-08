"""Shared plumbing for real LLM providers: a client-side rate limiter and retry/backoff timing.

Both take their clock and sleep as parameters so tests run instantly and deterministically.
"""
import random
import re
import time
from collections.abc import Callable

RETRYABLE_STATUS = {408, 409, 429, 500, 502, 503, 504, 529}
MAX_WAIT_SECONDS = 60.0


class RateLimiter:
    """Allows at most `rpm` calls per minute by spacing them. rpm <= 0 disables it."""

    def __init__(self, rpm: float, clock: Callable[[], float] = time.monotonic,
                 sleep: Callable[[float], None] = time.sleep) -> None:
        self.interval = 60.0 / rpm if rpm and rpm > 0 else 0.0
        self._clock, self._sleep = clock, sleep
        self._next = 0.0

    def wait(self) -> float:
        """Block until the next call is allowed. Returns how long we waited."""
        if not self.interval:
            return 0.0
        now = self._clock()
        wait = max(0.0, self._next - now)
        if wait:
            self._sleep(wait)
        self._next = max(now, self._next) + self.interval
        return wait


_RETRY_DELAY_BODY = re.compile(r'"retryDelay"\s*:\s*"(\d+(?:\.\d+)?)s"')


def retry_after_seconds(headers: dict | None, body: str = "") -> float | None:
    """How long the server asked us to wait: the Retry-After header, or Google's retryDelay in the error body."""
    if headers:
        for k, v in headers.items():
            if k.lower() == "retry-after":
                try:
                    return float(v)
                except (TypeError, ValueError):
                    break
    m = _RETRY_DELAY_BODY.search(body or "")
    return float(m.group(1)) if m else None


def backoff_delay(attempt: int, server_hint: float | None = None, base: float = 1.0,
                  rng: Callable[[], float] = random.random) -> float:
    """Seconds to wait before retry number `attempt` (1-based). Honours the server's hint, adds jitter, capped."""
    exp = base * (2 ** (attempt - 1))
    delay = max(exp, server_hint or 0.0)
    return min(delay + rng() * min(1.0, base), MAX_WAIT_SECONDS)
