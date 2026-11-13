"""Abuse and cost guards for a public deployment. In-process and simple on purpose (CLAUDE.md: no extra services).

  * RateLimiter   token bucket per client (and per group), used by the middleware for every write request and by the
                  live-AI path with a much smaller allowance
  * LiveBudget    caps live-LLM requests per UTC day so a public site cannot burn the operator's quota
  * body cap      requests that announce a huge body are refused before they are read

All limits come from the environment (defaults are generous for a single user and tight for a crowd):
  RATE_LIMIT_PER_MIN (120)   LIVE_RATE_PER_MIN (6)   LIVE_LLM_DAILY_CAP (300)   MAX_BODY_BYTES (1_500_000)
  TRUST_PROXY (on when running on Render): use the first X-Forwarded-For address as the client
"""
import ipaddress
import os
import threading
import time
from collections.abc import Callable
from datetime import datetime, timezone

from fastapi import HTTPException, Request

from app.core import metrics


def _num(name: str, default: float) -> float:
    try:
        return float(os.getenv(name, default))
    except ValueError:
        return float(default)


class RateLimiter:
    """Token bucket: `per_min` requests a minute, refilled continuously, burst up to `per_min`."""

    MAX_KEYS = 20000

    def __init__(self, clock: Callable[[], float] = time.monotonic) -> None:
        self._clock = clock
        self._buckets: dict[tuple[str, str], tuple[float, float]] = {}     # key -> (tokens, last refill)
        self._lock = threading.Lock()

    def allow(self, group: str, client: str, per_min: float) -> tuple[bool, float]:
        """(allowed, seconds until a token is available)."""
        if per_min <= 0:
            return True, 0.0
        now = self._clock()
        key = (group, client)
        with self._lock:
            tokens, last = self._buckets.get(key, (per_min, now))
            tokens = min(per_min, tokens + (now - last) * per_min / 60.0)
            if tokens >= 1.0:
                self._buckets[key] = (tokens - 1.0, now)
                ok, wait = True, 0.0
            else:
                self._buckets[key] = (tokens, now)
                ok, wait = False, (1.0 - tokens) * 60.0 / per_min
            if len(self._buckets) > self.MAX_KEYS:                          # forget the stalest clients
                for k, _ in sorted(self._buckets.items(), key=lambda kv: kv[1][1])[: self.MAX_KEYS // 10]:
                    del self._buckets[k]
        return ok, wait


class LiveBudget:
    """Live-LLM requests per UTC day. Resets when the date changes; a restart also resets it (documented)."""

    def __init__(self, today: Callable[[], str] | None = None) -> None:
        self._today = today or (lambda: datetime.now(timezone.utc).strftime("%Y-%m-%d"))
        self._day, self._used = self._today(), 0
        self._lock = threading.Lock()

    def spend(self, cap: int) -> bool:
        with self._lock:
            day = self._today()
            if day != self._day:
                self._day, self._used = day, 0
            if cap > 0 and self._used >= cap:
                return False
            self._used += 1
            return True

    def snapshot(self, cap: int) -> dict:
        with self._lock:
            return {"day": self._day, "used": self._used, "cap": cap}


limiter = RateLimiter()
budget = LiveBudget()


def client_ip(request: Request) -> str:
    """The client address used as the rate-limit key.

    Behind a trusted proxy the proxy appends the address it saw to X-Forwarded-For, so the RIGHT-MOST entry is the one
    the proxy vouches for; everything to its left was written by the client and is ignored (taking the left-most entry
    let a client rotate it for a fresh bucket per request, or name a victim's address). The value must parse as an IP
    address, which also bounds the key's length; anything else falls back to the socket peer."""
    trust = os.getenv("TRUST_PROXY")
    trusted = (trust.strip().lower() in ("1", "true", "yes", "on")) if trust is not None else bool(os.getenv("RENDER"))
    if trusted:
        fwd = request.headers.get("x-forwarded-for", "")
        last = fwd.rsplit(",", 1)[-1].strip()
        if last:
            try:
                return str(ipaddress.ip_address(last))
            except ValueError:
                pass
    return request.client.host if request.client else "unknown"


def too_many(wait: float, what: str) -> HTTPException:
    return HTTPException(status_code=429, detail=f"{what} Try again in {max(1, round(wait))} s.",
                         headers={"Retry-After": str(max(1, round(wait)))})


def live_guard(request: Request) -> None:
    """Call before any request that will spend live-LLM quota. Raises 429 with a message the UI shows as is."""
    ok, wait = limiter.allow("live", client_ip(request), _num("LIVE_RATE_PER_MIN", 6))
    if not ok:
        metrics.inc("live_refused")
        raise too_many(wait, "Live AI is rate limited to protect the server's quota.")
    cap = int(_num("LIVE_LLM_DAILY_CAP", 300))
    if not budget.spend(cap):
        metrics.inc("live_refused")
        raise HTTPException(status_code=429, detail="The live AI budget for today is used up. Switch to Offline mode, or try again tomorrow.",
                            headers={"Retry-After": "3600"})
    metrics.inc("live_calls")
