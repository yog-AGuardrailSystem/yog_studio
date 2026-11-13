"""YOG runtime guard -- STANDALONE: ships next to the patched agent file together with yog.py and policy.yog.

    from yog_runtime import yog_guard

    @mcp.tool()
    @yog_guard("unlock_door")
    def unlock_door(door_id: str): ...

Every call is checked against the approved policy BEFORE the tool body runs. DENY raises YogDenied.
Settings (environment): YOG_POLICY (path, default ./policy.yog), YOG_ACTOR (default "agent"),
YOG_NOW="<hour>,<day>" to pin the clock for demos/tests (e.g. "3,sat").
Engine: the Python reference (yog.py, shipped next to this file) by default. Set YOG_YOGC=<path to yogc> to have the
engine team's C compiler decide instead (built from engine/c_front in the Studio repo). Once YOG_YOGC is set, any problem
with it (missing binary, timeout, crash, unexpected output) is a DENY: there is no silent fallback to Python.
Contract with Studio (docs/conventions.md): decision predicate is can_<tool>(Actor, Resource); resource is the
first string argument (normalised) or "item"; context facts are hour(now,H), day(now,D), arg(tool,param,V).
This module must NOT import anything from Studio's `app` package.
"""
import functools
import hashlib
import importlib.util
import inspect
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import threading
from datetime import datetime
from pathlib import Path

_HERE = Path(__file__).resolve().parent
_DAYS = ["mon", "tue", "wed", "thu", "fri", "sat", "sun"]
_engine = None
_c_policy = None          # private copy of the approved policy for yogc (later edits to policy.yog cannot reach it)
_C_TIMEOUT_S = 5
_KEYWORDS = {"fact", "rule", "allow", "deny", "query", "not"}
_BARE = re.compile(r"[a-z][a-z0-9_]*\Z")
_UNSAFE = re.compile(r"[\x00-\x1f\x7f\"\\;|]")
# The engine adds and removes the request's facts on shared state while it decides, so two threads deciding at once
# could see each other's facts. Decisions are therefore serialised.
_lock = threading.RLock()


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


class _Unrepresentable(ValueError):
    """An argument the engine cannot represent faithfully: the call is denied, never rounded or merged."""


def _value(v):
    if v is None:
        return None
    if isinstance(v, bool):
        return 1 if v else 0
    if isinstance(v, int):
        return v
    if isinstance(v, float):
        if v != v or v in (float("inf"), float("-inf")) or v != int(v):
            raise _Unrepresentable(f"{v!r} is not a whole number and cannot be compared exactly; pass a whole number")
        return int(v)
    if isinstance(v, (list, tuple, dict, set)):
        return len(v)
    if isinstance(v, str) and ("/" in v or "\\" in v or ".." in v):
        raise _Unrepresentable("a path-like value cannot be matched exactly (different paths would normalise to the same name)")
    return _ident(v)


def facts_from_call(tool, args, hour, day):
    out = [f"hour(now, {int(hour) % 24})", f"day(now, {_ident(day)})"]
    t = _ident(tool)
    for name, raw in args.items():
        try:
            v = _value(raw)
        except _Unrepresentable as e:
            raise _Unrepresentable(f"argument {name!r}: {e}") from e
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


def _digest(data: bytes) -> str:
    """SHA-256 with Windows line endings read as Unix ones, so a policy that an editor or git re-saved with CRLF still
    matches the hash of the approved text (any other edit changes the hash)."""
    return hashlib.sha256(data.replace(b"\r\n", b"\n")).hexdigest()


def policy_sha256() -> str:
    """SHA-256 of the policy file this guard loads (hex)."""
    path = Path(os.environ.get("YOG_POLICY", _HERE / "policy.yog"))
    return _digest(path.read_bytes())


def _load():
    global _engine
    with _lock:
        if _engine is None:
            yog = _yog()
            path = Path(os.environ.get("YOG_POLICY", _HERE / "policy.yog"))
            data = path.read_bytes()
            pin = os.environ.get("YOG_POLICY_SHA256", "").strip().lower()
            if pin and _digest(data) != pin:
                raise RuntimeError("policy file does not match YOG_POLICY_SHA256 (it was changed after approval)")
            _engine = (yog, yog.Engine(yog.Parser(yog.tokenize(data.decode("utf-8"))).parse()))
            if os.environ.get("YOG_YOGC"):
                global _c_policy
                fd, name = tempfile.mkstemp(prefix="yog-policy-", suffix=".yog")
                with os.fdopen(fd, "wb") as fh:
                    fh.write(data)
                _c_policy = name
        return _engine


def _canon(fact) -> str:
    """One parsed context fact -> text that is safe to hand to yogc. yogc splits its context on every `;`, even inside
    quotes, so values that could smuggle a second fact are refused (the guard then denies). Same rules as Studio's
    CEngineAdapter (a test keeps them equal)."""
    out = []
    for a in fact.args:
        v = getattr(a, "val", None)
        if type(a).__name__ != "Const" or isinstance(v, bool):
            raise ValueError("context facts must be ground")
        if isinstance(v, int):
            out.append(str(v))
        elif _BARE.match(v) and v not in _KEYWORDS:
            out.append(v)
        elif _UNSAFE.search(v):
            raise ValueError("a context value contains a character the C engine cannot carry safely")
        else:
            out.append(f'"{v}"')
    return f"{fact.pred}({', '.join(out)})"


def _check_c(yogc: str, actor: str, action: str, resource: str, atoms) -> dict:
    """Decide with the C engine (`yogc check`, arguments passed as argv, never through a shell)."""
    for v in (actor, action, resource):
        if not v or "\x00" in v or v.startswith("--"):
            raise ValueError("an empty or option-like actor/action/resource cannot be passed to yogc")
    if not shutil.which(yogc) and not Path(yogc).is_file():
        raise FileNotFoundError(f"YOG_YOGC={yogc} does not exist")
    cmd = [yogc, "check", _c_policy, actor, action, resource, "--trace"]
    ctx = ";".join("fact " + _canon(f) for f in atoms)
    if ctx:
        cmd += ["--context", ctx]
    p = subprocess.run(cmd, stdin=subprocess.DEVNULL, capture_output=True, timeout=_C_TIMEOUT_S)
    lines = p.stdout.decode("utf-8", "replace").splitlines()
    head = lines[0] if lines else ""
    kind, _, reason = head.partition("|")
    if p.returncode not in (0, 3) or kind not in ("ALLOW", "DENY"):
        err = p.stderr.decode("utf-8", "replace").strip().splitlines()
        raise RuntimeError(f"C engine: {err[-1] if err else 'exit status ' + str(p.returncode)}")
    return {"decision": kind, "reason": reason, "trace": [ln[2:] for ln in lines[1:] if ln.startswith("> ")]}


def _log(tool: str, args: dict, hour: int, day: str, result: dict) -> None:
    """Optional decision log (YOG_LOG=<file>): one JSON line per decision. Argument values are stored normalised, the
    same form the policy saw, not raw. Best effort: logging can never change a decision."""
    path = os.environ.get("YOG_LOG")
    if not path:
        return
    try:
        row = {"at": datetime.now().isoformat(timespec="seconds"), "tool": tool,
               "args": {_ident(k): _value(v) for k, v in args.items() if _value(v) is not None},
               "hour": hour, "day": day, "decision": result["decision"], "reason": result["reason"]}
        with _lock, open(path, "a", encoding="utf-8") as fh:
            fh.write(json.dumps(row, sort_keys=True) + "\n")
    except Exception:                            # noqa: BLE001
        pass


def check(tool: str, args: dict, actor: str | None = None) -> dict:
    """Decide one call. Fails CLOSED: any engine/policy problem is a DENY."""
    hour, day = 0, "mon"
    try:
        yog, engine = _load()
        hour, day = _clock()
        resource = next((_ident(v) for v in args.values() if isinstance(v, str)), "item")
        atoms = []
        for text in facts_from_call(tool, args, hour, day):
            atoms += yog.Parser(yog.tokenize("fact " + text)).parse().facts
        who, action = actor or os.environ.get("YOG_ACTOR", "agent"), "can_" + _ident(tool)
        yogc = os.environ.get("YOG_YOGC")
        if yogc:
            result = _check_c(yogc, who, action, resource, atoms)
        else:
            with _lock:
                result = engine.check(who, action, resource, atoms)
    except Exception as e:                       # noqa: BLE001 -- a guard must never fail open
        result = {"decision": "DENY", "reason": f"guard error, failing closed: {type(e).__name__}: {e}", "trace": []}
    _log(tool, args, hour, day, result)
    return result


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


def selftest() -> int:
    """`python yog_runtime.py --selftest`: does the guard load its policy, and does it fail closed? Exit code 0 = fine."""
    problems = []
    try:
        yog, engine = _load()
        print(f"policy: {os.environ.get('YOG_POLICY', _HERE / 'policy.yog')}  sha256 {policy_sha256()[:16]}...")
        print(f"decision rules: {sum(len(v) for v in engine.decisions.values())}")
        print("engine: " + (f"C (yogc at {os.environ['YOG_YOGC']})" if os.environ.get("YOG_YOGC") else "Python reference (yog.py)"))
    except Exception as e:                       # noqa: BLE001
        problems.append(f"the policy did not load: {e}")
    r = check("zz_tool_that_has_no_rule", {})
    if r["decision"] != "DENY":
        problems.append("a tool with no rule was not denied")
    else:
        print("unknown tool is denied: ok")
    for p in problems:
        print("FAIL:", p)
    print("selftest", "FAILED" if problems else "passed")
    return 1 if problems else 0


if __name__ == "__main__":
    if "--selftest" in sys.argv:
        raise SystemExit(selftest())
    print(__doc__)
