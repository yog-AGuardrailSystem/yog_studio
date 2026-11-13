"""Anonymous per-visitor sessions (no accounts, CLAUDE.md principle 7).

Why: approved policies and the device simulator used to be global, so on a public site one visitor would see (and
drive) another visitor's policies. Each browser now gets a random id in an HttpOnly cookie; its policies live in
data/sessions/<id>/ and its device simulator is its own. The id is a capability, not an identity: whoever holds the
cookie sees that data, and nobody else does. Data is disposable and expires (SESSION_TTL_DAYS, default 7).
"""
import os
import re
import secrets
import shutil
import threading
import time
from pathlib import Path

from fastapi import Request

from app.core import config

COOKIE = "yog_sid"
MAX_AGE = 30 * 24 * 3600
SID_RE = re.compile(r"[0-9a-f]{32}\Z")        # \Z, not $: `$` also matches before a trailing newline
ANONYMOUS = "0" * 32             # requests that never went through the middleware (direct calls, tests)
_CLEANUP_EVERY = 3600.0
_last_cleanup = 0.0
_lock = threading.Lock()


def new_sid() -> str:
    return secrets.token_hex(16)


def valid(sid: str | None) -> bool:
    return bool(sid and SID_RE.match(sid))


def acceptable_cookie(sid: str | None) -> bool:
    """A cookie value the middleware will honour: well formed, and not the shared fallback id (a client could otherwise
    send yog_sid=000...0 and land in the directory used by requests that bypass the middleware)."""
    return valid(sid) and sid != ANONYMOUS


def session_id(request: Request) -> str:
    sid = getattr(request.state, "sid", None)
    return sid if valid(sid) else ANONYMOUS


def session_dir(sid: str) -> Path:
    if not valid(sid):                       # also blocks path traversal
        raise ValueError("invalid session id")
    return config.DATA_DIR / "sessions" / sid


def policies_dir(request: Request) -> Path:
    return session_dir(session_id(request)) / "policies"


def ttl_days() -> float:
    try:
        return float(os.getenv("SESSION_TTL_DAYS", "7"))
    except ValueError:
        return 7.0


def cleanup_sessions(max_age_days: float | None = None, now: float | None = None) -> int:
    """Delete session folders untouched for longer than the TTL. Returns how many were removed."""
    root = config.DATA_DIR / "sessions"
    if not root.is_dir():
        return 0
    limit = (max_age_days if max_age_days is not None else ttl_days()) * 86400
    now = now if now is not None else time.time()
    removed = 0
    for d in root.iterdir():
        try:
            if d.is_dir() and valid(d.name) and now - _newest_mtime(d) > limit:
                shutil.rmtree(d, ignore_errors=True)
                removed += 1
        except OSError:
            continue
    return removed


def _newest_mtime(d: Path) -> float:
    newest = d.stat().st_mtime
    for f in d.rglob("*"):
        try:
            newest = max(newest, f.stat().st_mtime)
        except OSError:
            pass
    return newest


def maybe_cleanup(now: float | None = None) -> int:
    """At most once an hour (called when a new visitor arrives), so expiry needs no scheduler."""
    global _last_cleanup
    t = now if now is not None else time.time()
    with _lock:
        if t - _last_cleanup < _CLEANUP_EVERY:
            return 0
        _last_cleanup = t
    return cleanup_sessions(now=t)
