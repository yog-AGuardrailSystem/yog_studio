"""YOG runtime guard -- STANDALONE: ships next to the patched agent file together with yog.py and policy.yog.

    from yog_runtime import yog_guard

    @mcp.tool()
    @yog_guard("unlock_door")
    def unlock_door(door_id: str): ...

Every call is checked against the approved policy BEFORE the tool body runs. DENY raises YogDenied.
Settings (environment): YOG_POLICY (path, default ./policy.yog), YOG_ACTOR (default "agent"),
YOG_NOW="<hour>,<day>" to pin the clock for demos/tests (e.g. "3,sat").
Contract with Studio (docs/conventions.md): decision predicate is can_<tool>(Actor, Resource); resource is the
first string argument (normalised) or "item"; context facts are hour(now,H), day(now,D), arg(tool,param,V).
This module must NOT import anything from Studio's `app` package.
"""
import functools
import importlib.util
import inspect
import os
import re
import sys
from datetime import datetime
from pathlib import Path

_HERE = Path(__file__).resolve().parent
_DAYS = ["mon", "tue", "wed", "thu", "fri", "sat", "sun"]
_engine = None


class YogDenied(Exception):
    """Raised instead of running a tool the policy denies."""

    def __init__(self, tool: str, reason: str):
        super().__init__(f"YOG denied {tool}: {reason}")
        self.tool, self.reason = tool, reason


# ---- value normalisation (kept identical to Studio's app/core/facts.py; a test enforces equality) ----
def _ident(value) -> str:
    s = re.sub(r"[^a-z0-9]+", "_", str(value).strip().lower()).strip("_")
    if not s:
        return "empty"
    return f"v_{s}" if s[0].isdigit() else s


def _value(v):
    if v is None:
        return None
    if isinstance(v, bool):
        return 1 if v else 0
    if isinstance(v, int):
        return v
    if isinstance(v, float):
        return int(round(v))
    if isinstance(v, (list, tuple, dict, set)):
        return len(v)
    return _ident(v)


def facts_from_call(tool, args, hour, day):
    out = [f"hour(now, {int(hour) % 24})", f"day(now, {_ident(day)})"]
    t = _ident(tool)
    for name, raw in args.items():
        v = _value(raw)
        if v is not None:
            out.append(f"arg({t}, {_ident(name)}, {v})")
    return out


def _clock():
    pinned = os.environ.get("YOG_NOW")
    if pinned:
        h, d = pinned.split(",")
        return int(h), d.strip()
    now = datetime.now()
    return now.hour, _DAYS[now.weekday()]


def _yog():
    path = _HERE / "yog.py"
    spec = importlib.util.spec_from_file_location("yog_runtime_engine", path)
    mod = importlib.util.module_from_spec(spec)
    sys.modules["yog_runtime_engine"] = mod
    spec.loader.exec_module(mod)
    return mod


def _load():
    global _engine
    if _engine is None:
        yog = _yog()
        policy = Path(os.environ.get("YOG_POLICY", _HERE / "policy.yog"))
        _engine = (yog, yog.Engine(yog.Parser(yog.tokenize(policy.read_text(encoding="utf-8"))).parse()))
    return _engine


def check(tool: str, args: dict, actor: str | None = None) -> dict:
    """Decide one call. Fails CLOSED: any engine/policy problem is a DENY."""
    try:
        yog, engine = _load()
        hour, day = _clock()
        resource = next((_ident(v) for v in args.values() if isinstance(v, str)), "item")
        atoms = []
        for text in facts_from_call(tool, args, hour, day):
            atoms += yog.Parser(yog.tokenize("fact " + text)).parse().facts
        return engine.check(actor or os.environ.get("YOG_ACTOR", "agent"), "can_" + _ident(tool), resource, atoms)
    except Exception as e:                       # noqa: BLE001 -- a guard must never fail open
        return {"decision": "DENY", "reason": f"guard error, failing closed: {type(e).__name__}: {e}", "trace": []}


def yog_guard(tool_name: str):
    """Decorator. Place it directly above `def` (innermost). Works for sync and async functions."""

    def deco(fn):
        sig = inspect.signature(fn)

        def decide(args, kwargs):
            try:
                bound = sig.bind(*args, **kwargs)
                bound.apply_defaults()
                values = dict(bound.arguments)
            except TypeError:
                values = dict(kwargs)
            r = check(tool_name, values)
            if r["decision"] != "ALLOW":
                raise YogDenied(tool_name, r["reason"])

        if inspect.iscoroutinefunction(fn):
            @functools.wraps(fn)
            async def wrapper(*args, **kwargs):
                decide(args, kwargs)
                return await fn(*args, **kwargs)
        else:
            @functools.wraps(fn)
            def wrapper(*args, **kwargs):
                decide(args, kwargs)
                return fn(*args, **kwargs)
        return wrapper

    return deco
