"""Process-local counters for /status. No external service (CLAUDE.md principle 7); a restart resets them."""
import threading
import time
from collections import Counter

_counts: Counter[str] = Counter()
_lock = threading.Lock()
STARTED = time.time()


def inc(name: str, n: int = 1) -> None:
    with _lock:
        _counts[name] += n


def snapshot() -> dict:
    with _lock:
        return {"uptime_s": int(time.time() - STARTED), **dict(sorted(_counts.items()))}


def reset() -> None:                      # tests
    with _lock:
        _counts.clear()
