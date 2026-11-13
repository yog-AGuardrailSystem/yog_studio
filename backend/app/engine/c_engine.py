"""CEngineAdapter: decisions made by the engine team's real C compiler/VM, run as a subprocess (`yogc`).

Why a subprocess and not ctypes (docs/decisions.md): upstream builds static libraries only, a crash in C must not take
the backend down, and it matches the existing lexdump bridge (c_lexer.py).

What C does and what it does not:
* C DECIDES (check / check_many / validate). Every failure mode (crash, timeout, wrong response count, an evaluation
  error reported by the VM) is a DENY, never an ALLOW and never a silent switch to the Python engine.
* The C API has no AST, predicate table, explain or plain-query call. Structure for the workbench/explainer comes from
  the Python reference parser; `explain()` re-derives the proof there and refuses to show it if the two engines
  disagree about the decision (docs/engine_issues.md).

Security: `yogc` builds request context by replacing EVERY `;` with a newline (even inside quoted strings) and its
batch protocol splits on `|` and whitespace and truncates lines at 4096 bytes. Passing caller text straight through
would let `arg(t,p,"x; fact role(agent, admin)")` add an authority fact. So each context item is parsed with the
reference parser (exactly one ground fact), re-serialised canonically, and anything that cannot be represented
safely is refused (DENY). Actor/action/resource values that the line protocol cannot carry go through argv instead.

Selecting it: YOG_ENGINE=c. The binary is $YOG_YOGC, or built from engine/c_front/ (see c_build.py).
"""
import atexit
import hashlib
import re
import shutil
import subprocess
import tempfile
import threading
from collections import OrderedDict
from pathlib import Path

from app.engine.adapter import (AskResult, CheckResult, CompileInfo, EngineAdapter, EngineError, QuerySpec,
                                WhyResult)
from app.engine.c_build import find_tool
from app.engine.diagnostics import classify
from app.engine.python_prototype import PythonPrototypeAdapter, _parse_text

BATCH_TIMEOUT_BASE_S = 5.0          # per yogc process
BATCH_TIMEOUT_PER_REQUEST_S = 0.05
BATCH_TIMEOUT_MAX_S = 60.0
MAX_LINE_BYTES = 3500               # yogc reads 4096-byte lines; stay well under so a line is never split in two
MAX_BATCH = 500                     # requests per process
CACHE_SIZE = 16
KEYWORDS = {"fact", "rule", "allow", "deny", "query", "not"}
_BARE = re.compile(r"[a-z][a-z0-9_]*\Z")
_BAD_VALUE = re.compile(r"[\x00-\x1f\x7f\"\\;|]")
_WS = re.compile(r"[\s\x00-\x1f\x7f|]")
_ERR_LINE = re.compile(r"^(\d+):(\d+): error: (.*)$")

FAIL = "engine error, failing closed: "


class CEngineUnavailable(RuntimeError):
    pass


class CompileError(EngineError):
    """A policy the C compiler rejected. `line`/`column` are 1-based (0 when C gave none)."""

    def __init__(self, message: str, line: int = 0, column: int = 0):
        super().__init__(f"line {line}: {message}" if line else message)
        self.message, self.line, self.column = message, line, column


class _Refused(Exception):
    """A request Studio will not hand to the C engine (fail closed with this reason)."""


# ------------------------------------------------------------------ context guard (G3)
def _render_const(val) -> str:
    if isinstance(val, bool):
        raise _Refused("boolean value in a context fact")
    if isinstance(val, int):
        return str(val)
    if isinstance(val, str):
        if _BARE.match(val) and val not in KEYWORDS:
            return val
        if _BAD_VALUE.search(val):
            raise _Refused("a context value contains a character the C engine cannot carry safely "
                           "(quote, backslash, ';', '|' or a control character)")
        return f'"{val}"'
    raise _Refused(f"unsupported context value {val!r}")


def canonical_context(context: list[str] | None) -> list[str]:
    """Each item must be exactly one ground fact (EngineError otherwise, like the Python adapter); returns
    `pred(a, b)` strings that are safe to embed. Raises _Refused for values C cannot carry."""
    out: list[str] = []
    for text in context or []:
        text = text.strip()
        if not text:
            continue
        try:
            facts = _parse_text("fact " + text).facts
        except EngineError as e:
            raise EngineError(f"bad context fact {text!r}: {e}") from e
        if len(facts) != 1:
            raise EngineError(f"bad context fact {text!r}: expected exactly one fact")
        f = facts[0]
        if any(type(a).__name__ != "Const" for a in f.args):
            raise EngineError(f"bad context fact {text!r}: facts must be ground (no variables)")
        out.append(f"{f.pred}({', '.join(_render_const(a.val) for a in f.args)})")
    return out


def _line_safe(value: str) -> bool:
    return bool(value) and not _WS.search(value) and not value.startswith("--")


# ------------------------------------------------------------------ process plumbing
class _Policies:
    """Policy text -> file on disk, keyed by SHA-256, bounded LRU. Also remembers compile failures."""

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._dir: Path | None = None
        self._items: OrderedDict[str, tuple[Path | None, CompileError | None]] = OrderedDict()

    def _tmp(self) -> Path:
        if self._dir is None:
            self._dir = Path(tempfile.mkdtemp(prefix="yog-c-"))
            atexit.register(shutil.rmtree, self._dir, ignore_errors=True)
        return self._dir

    def get(self, policy: str, yogc: Path) -> Path:
        if "\x00" in policy:
            raise CompileError("policy contains a NUL byte")
        key = hashlib.sha256(policy.encode("utf-8", "surrogatepass")).hexdigest()
        with self._lock:
            hit = self._items.get(key)
            if hit is None:
                hit = self._compile(policy, key, yogc)
                self._items[key] = hit
                while len(self._items) > CACHE_SIZE:
                    _, (old, _e) = self._items.popitem(last=False)
                    if old is not None:
                        old.unlink(missing_ok=True)
            else:
                self._items.move_to_end(key)
        path, err = hit
        if err is not None:
            raise err
        return path

    def _compile(self, policy: str, key: str, yogc: Path) -> tuple[Path | None, CompileError | None]:
        path = self._tmp() / f"{key}.yog"
        path.write_bytes(policy.encode("utf-8", "surrogatepass"))
        try:
            p = subprocess.run([str(yogc), "batch", str(path)], stdin=subprocess.DEVNULL, capture_output=True,
                               timeout=BATCH_TIMEOUT_BASE_S)
        except subprocess.TimeoutExpired:
            path.unlink(missing_ok=True)
            raise CompileError("the C compiler did not finish within the time limit")   # raised, so never cached
        if p.returncode == 0:
            return path, None
        path.unlink(missing_ok=True)
        stderr = p.stderr.decode("utf-8", "replace").strip()
        last = stderr.splitlines()[-1] if stderr else "compile error"
        last = last.replace(str(path) + ":", "", 1)
        m = _ERR_LINE.match(last)
        if p.returncode == 1 and m:
            return None, CompileError(m.group(3), int(m.group(1)), int(m.group(2)))
        return None, CompileError(last[:300])


def _parse_responses(stdout: str, trace: bool) -> list[tuple[str, str, list[str]]]:
    """`DECISION|reason` [`> trace` ...] `--` blocks -> [(decision|'ERROR', text, trace lines)]."""
    blocks: list[tuple[str, str, list[str]]] = []
    head: str | None = None
    lines: list[str] = []
    for raw in stdout.split("\n"):
        if raw == "--":
            if head is None:
                blocks.append(("ERROR", "malformed response", []))
            else:
                kind, _, rest = head.partition("|")
                blocks.append((kind if kind in ("ALLOW", "DENY") else "ERROR", rest, lines))
            head, lines = None, []
        elif head is None:
            if raw:
                head = raw
        elif raw.startswith("> "):
            lines.append(raw[2:])
        elif raw == ">":
            lines.append("")
    return blocks


def _fail(msg: str) -> CheckResult:
    return CheckResult(decision="DENY", reason=FAIL + msg, trace=[])


# ------------------------------------------------------------------ the adapter
class CEngineAdapter(EngineAdapter):
    ENV_BIN = "YOG_YOGC"

    @classmethod
    def available(cls) -> bool:
        return find_tool("yogc") is not None

    def __init__(self) -> None:
        self._yogc = find_tool("yogc")
        if self._yogc is None:
            raise CEngineUnavailable(
                f"C engine not available: set {self.ENV_BIN} to a built yogc, or install a C compiler so Studio can "
                "build engine/c_front/. Falling back to the Python prototype is never automatic (app/api/deps.py).")
        self._policies = _Policies()
        self._ref = PythonPrototypeAdapter()          # structure only (see module docstring)

    # -- decisions -------------------------------------------------------
    def check(self, policy, actor, action, resource, context=None) -> CheckResult:
        return self.check_many(policy, [(actor, action, resource, context)])[0]

    def check_many(self, policy: str, requests: list[tuple]) -> list[CheckResult]:
        path = self._policies.get(policy, self._yogc)          # CompileError (an EngineError) if it does not compile
        results: list[CheckResult | None] = [None] * len(requests)
        batchable: list[tuple[int, str]] = []                  # (index, protocol line)
        for i, (actor, action, resource, context) in enumerate(requests):
            try:
                ctx = canonical_context(context)               # EngineError for malformed context, _Refused for unsafe
                ctx_text = ";".join("fact " + c for c in ctx)
                if len(ctx_text) > 100_000:
                    raise _Refused("context is too large")
                if all(_line_safe(v) for v in (actor, action, resource)):
                    line = f"{actor} {action} {resource}" + (f"|{ctx_text}" if ctx_text else "")
                    if len(line.encode("utf-8")) <= MAX_LINE_BYTES:
                        batchable.append((i, line))
                        continue
                results[i] = self._check_argv(path, actor, action, resource, ctx_text)
            except _Refused as e:
                results[i] = _fail(str(e))
        for start in range(0, len(batchable), MAX_BATCH):
            chunk = batchable[start:start + MAX_BATCH]
            for (i, _), r in zip(chunk, self._run_batch(path, [ln for _, ln in chunk])):
                results[i] = r
        return results  # type: ignore[return-value]

    def _run_batch(self, path: Path, lines: list[str]) -> list[CheckResult]:
        timeout = min(BATCH_TIMEOUT_MAX_S, BATCH_TIMEOUT_BASE_S + BATCH_TIMEOUT_PER_REQUEST_S * len(lines))
        try:
            p = subprocess.run([str(self._yogc), "batch", str(path), "--trace"],
                               input=("\n".join(lines) + "\n").encode("utf-8"), capture_output=True, timeout=timeout)
        except subprocess.TimeoutExpired:
            return [_fail(f"the C engine did not answer within {timeout:.0f}s") for _ in lines]
        except OSError as e:
            return [_fail(f"could not run the C engine ({e})") for _ in lines]
        if p.returncode != 0:
            return [_fail(f"the C engine exited with status {p.returncode}") for _ in lines]
        blocks = _parse_responses(p.stdout.decode("utf-8", "replace"), True)
        if len(blocks) != len(lines):
            return [_fail(f"the C engine returned {len(blocks)} answers for {len(lines)} requests") for _ in lines]
        return [self._to_result(*b) for b in blocks]

    def _check_argv(self, path: Path, actor: str, action: str, resource: str, ctx_text: str) -> CheckResult:
        for v in (actor, action, resource):
            if not v or "\x00" in v or v.startswith("--"):
                return _fail("an empty, NUL-containing or option-like actor/action/resource cannot be passed safely")
        cmd = [str(self._yogc), "check", str(path), actor, action, resource, "--trace"]
        if ctx_text:
            cmd += ["--context", ctx_text]
        try:
            p = subprocess.run(cmd, stdin=subprocess.DEVNULL, capture_output=True, timeout=BATCH_TIMEOUT_BASE_S)
        except subprocess.TimeoutExpired:
            return _fail(f"the C engine did not answer within {BATCH_TIMEOUT_BASE_S:.0f}s")
        except OSError as e:
            return _fail(f"could not run the C engine ({e})")
        out = p.stdout.decode("utf-8", "replace")
        blocks = _parse_responses(out + ("--\n" if out else ""), True)
        if p.returncode not in (0, 3) or len(blocks) != 1:
            msg = p.stderr.decode("utf-8", "replace").strip().splitlines()
            return _fail(msg[-1][:200] if msg else f"the C engine exited with status {p.returncode}")
        return self._to_result(*blocks[0])

    @staticmethod
    def _to_result(kind: str, text: str, trace: list[str]) -> CheckResult:
        if kind == "ERROR":
            return _fail(text or "evaluation error")
        return CheckResult(decision=kind, reason=text, trace=trace)    # type: ignore[arg-type]

    def validate(self, policy: str) -> list[str]:
        try:
            self._policies.get(policy, self._yogc)
        except EngineError as e:
            return [str(e)]
        return []

    def compile_error(self, policy: str) -> CompileError | None:
        """Structured form of validate() for diagnostics (line + column)."""
        try:
            self._policies.get(policy, self._yogc)
        except CompileError as e:
            return e
        return None

    # -- structure: the reference parser (C has no AST / predicate / explain API) ----------
    def program_info(self, policy: str) -> dict:
        return self._ref.program_info(policy)

    def compile_info(self, policy: str) -> CompileInfo:
        """Tokens / AST / predicates from the reference parser; the verdict and the diagnostic from C (with a column)."""
        info = self._ref.compile_info(policy)
        err = self.compile_error(policy)
        if err is None:
            return info.model_copy(update={"ok": True, "diagnostics": []})
        known = {(p.name, p.arity): p.role for p in info.predicates}
        d = classify(str(err), known, policy.splitlines(), column=err.column or None)
        return info.model_copy(update={"ok": False, "diagnostics": [d]})

    def queries(self, policy: str) -> list[QuerySpec]:
        return self._ref.queries(policy)

    def ask(self, policy: str, pred: str, terms: list[dict]) -> AskResult:
        return self._ref.ask(policy, pred, terms)

    def explain(self, policy, actor, action, resource, context=None) -> WhyResult:
        """The proof is derived by the reference engine; it is shown only if C made the same decision."""
        why = self._ref.explain(policy, actor, action, resource, context)
        c = self.check(policy, actor, action, resource, context)
        if why.decision != c.decision:
            return why.model_copy(update={
                "decision": c.decision, "reason": c.reason, "error": True, "winner_line": None, "clauses": [],
                "verdict": (f"The engines disagree: C decided {c.decision}, the reference engine {why.decision}. "
                            "No explanation is shown because it would not describe the decision that was made.")})
        return why.model_copy(update={"reason": c.reason})
