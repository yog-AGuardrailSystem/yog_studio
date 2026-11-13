"""Disk quota for visitor data under data/sessions/. A visitor needs no account, so without a cap anyone could keep
saving policies until the server's disk is full. Two limits, both environment-tunable:

  SESSION_MAX_BYTES  what one visitor may store (default 10 MB)
  SESSIONS_MAX_BYTES what all visitors together may store (default 500 MB)

Only NEW writes are refused (QuotaExceeded -> HTTP 507); reading and deciding keep working. Before refusing because the
global ceiling is reached, expired sessions are removed once."""
import os
import threading
import time
from pathlib import Path

from app.core import config, session

_lock = threading.Lock()
_cache: dict = {"at": 0.0, "bytes": 0}
GLOBAL_CACHE_SECONDS = 30.0


class QuotaExceeded(Exception):
    """Storage limit reached; the message is safe to show to the visitor."""


def _limit(name: str, default: int) -> int:
    try:
        return max(0, int(os.getenv(name, str(default))))
    except ValueError:
        return default


def dir_bytes(path: Path) -> int:
    total = 0
    if not path.is_dir():
        return 0
    for f in path.rglob("*"):
        try:
            if f.is_file() and not f.is_symlink():
                total += f.stat().st_size
        except OSError:
            continue
    return total


def _global_bytes(force: bool = False) -> int:
    with _lock:
        now = time.monotonic()
        if force or now - _cache["at"] > GLOBAL_CACHE_SECONDS:
            _cache.update(at=now, bytes=dir_bytes(config.DATA_DIR / "sessions"))
        return _cache["bytes"]


def session_root(path: Path) -> Path | None:
    """The data/sessions/<sid> folder a path lives in, or None when it is not a visitor folder (tests, local dev)."""
    try:
        rel = path.resolve().relative_to((config.DATA_DIR / "sessions").resolve())
    except (ValueError, OSError):
        return None
    return (config.DATA_DIR / "sessions" / rel.parts[0]) if rel.parts and session.valid(rel.parts[0]) else None


def check_room(path: Path, adding: int) -> None:
    """Raise QuotaExceeded when writing `adding` more bytes into this visitor's folder would break a limit."""
    root = session_root(path)
    if root is None:
        return
    if dir_bytes(root) + adding > _limit("SESSION_MAX_BYTES", 10 * 1024 * 1024):
        raise QuotaExceeded("Your saved data is full (each visitor may keep about 10 MB). It expires on its own after a few days.")
    ceiling = _limit("SESSIONS_MAX_BYTES", 500 * 1024 * 1024)
    if _global_bytes() + adding > ceiling:
        session.cleanup_sessions()
        if _global_bytes(force=True) + adding > ceiling:
            raise QuotaExceeded("The server's storage for visitor data is full right now. Try again later.")
    with _lock:
        _cache["bytes"] += adding
