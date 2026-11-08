"""The engine team's real C lexer, run as a subprocess, for side-by-side comparison with the Python reference.

Vendored at engine/c_front/ (pinned commit, see engine/c_front/VERSION). We never edit those sources. The binary is
`lexdump`, built from lexer.c + tools/lexdump.c, which prints one token per line as `LINE:COL TYPE [text]`.

Where the binary comes from, in order: $YOG_LEXDUMP, then a build we make ourselves with the system C compiler into
backend/data/ (first use). If neither exists (no compiler on this machine) the result is `available=False` with a
reason; the UI shows that honestly instead of pretending.

The C lexer deliberately differs from the Python reference in a few documented ways (engine/c_front docs:
lexer_week4.md). Those are listed in KNOWN_DIFFERENCES and are not reported as mismatches.
"""
import os
import re
import shutil
import subprocess
import tempfile
from pathlib import Path

from pydantic import BaseModel, Field

from app.core.config import DATA_DIR, REPO_ROOT

C_FRONT = REPO_ROOT / "engine" / "c_front"
MAX_SOURCE_BYTES = 64 * 1024
RUN_TIMEOUT_S = 5
BUILD_TIMEOUT_S = 60

# C token type -> the reference interpreter's token kind
KIND_MAP = {
    "EOF": "EOF", "NEWLINE": "NEWLINE", "INDENT": "INDENT", "DEDENT": "DEDENT",
    "IDENT": "IDENT", "VAR": "VAR", "WILDCARD": "WILD", "STRING": "STR", "INT": "INT",
    "FACT": "KW", "RULE": "KW", "ALLOW": "KW", "DENY": "KW", "QUERY": "KW", "NOT": "KW",
    "LPAREN": "(", "RPAREN": ")", "COMMA": ",", "COLON": ":",
    "EQ": "OP", "NEQ": "OP", "LT": "OP", "LTE": "OP", "GT": "OP", "GTE": "OP",
}
OP_TEXT = {"EQ": "==", "NEQ": "!=", "LT": "<", "LTE": "<=", "GT": ">", "GTE": ">="}
KW_TEXT = {"FACT": "fact", "RULE": "rule", "ALLOW": "allow", "DENY": "deny", "QUERY": "query", "NOT": "not"}

# Documented, intentional differences (so a mismatch list only ever contains surprises).
KNOWN_DIFFERENCES = [
    "Integers outside 64 bits are an error in C (unbounded in the reference).",
    "Indentation deeper than 63 levels is an error in C.",
    "Identifiers are ASCII-only in C.",
    "Tabs are rejected by C (the reference counts only spaces).",
    "C columns are tracked for errors; the reference reports lines only.",
]

_LINE = re.compile(r"^(\d+):(\d+) (\S+)(?: (.*))?$")


class CToken(BaseModel):
    kind: str                       # reference-style kind, e.g. KW, IDENT, OP
    c_type: str                     # the C lexer's own name, e.g. FACT, LTE
    value: str | int | None = None
    line: int
    column: int


class Mismatch(BaseModel):
    index: int
    python: str
    c: str


class CLexerResult(BaseModel):
    available: bool
    reason: str | None = None       # why unavailable, or the C lexer's lexical error message
    ok: bool = False                # C lexer accepted the whole input
    tokens: list[CToken] = Field(default_factory=list)
    compared: int = 0               # tokens compared against the reference
    mismatches: list[Mismatch] = Field(default_factory=list)
    known_differences: list[str] = Field(default_factory=list)
    binary: str | None = None


# ---------------------------------------------------------------- locating / building the binary
def _exe_name() -> str:
    return "lexdump.exe" if os.name == "nt" else "lexdump"


def _compiler() -> str | None:
    for name in (os.environ.get("CC"), "cc", "gcc", "clang"):
        if name and shutil.which(name):
            return shutil.which(name)
    return None


def find_binary(build: bool = True) -> Path | None:
    env = os.environ.get("YOG_LEXDUMP")
    if env:
        return Path(env) if Path(env).is_file() else None
    out = DATA_DIR / "c_front" / _exe_name()
    if out.is_file():
        return out
    if not build:
        return None
    cc = _compiler()
    if not cc:
        return None
    out.parent.mkdir(parents=True, exist_ok=True)
    cmd = [cc, "-std=c11", "-O2", "-I", str(C_FRONT / "src"),
           str(C_FRONT / "src" / "lexer" / "lexer.c"), str(C_FRONT / "tools" / "lexdump.c"), "-o", str(out)]
    try:
        subprocess.run(cmd, check=True, capture_output=True, timeout=BUILD_TIMEOUT_S)
    except (subprocess.SubprocessError, OSError):
        return None
    return out if out.is_file() else None


# ---------------------------------------------------------------- parsing lexdump output
def parse_dump(text: str) -> list[CToken]:
    toks: list[CToken] = []
    for raw in text.splitlines():
        m = _LINE.match(raw)
        if not m:
            continue
        line, col, ctype, rest = int(m.group(1)), int(m.group(2)), m.group(3), m.group(4)
        kind = KIND_MAP.get(ctype, ctype)
        if ctype in OP_TEXT:
            value: str | int | None = OP_TEXT[ctype]
        elif ctype in KW_TEXT:
            value = KW_TEXT[ctype]
        elif ctype == "INT":
            value = int(rest) if rest is not None else None
        elif ctype in ("IDENT", "VAR", "STRING"):
            value = rest if rest is not None else ""
        elif ctype in ("LPAREN", "RPAREN", "COMMA", "COLON"):
            value = {"LPAREN": "(", "RPAREN": ")", "COMMA": ",", "COLON": ":"}[ctype]
        else:
            value = None
        toks.append(CToken(kind=kind, c_type=ctype, value=value, line=line, column=col))
    return toks


def _norm(kind: str, value) -> str:
    return f"{kind}:{'' if value is None else value}"


def compare(c_tokens: list[CToken], py_tokens: list[tuple[str, object, int]]) -> tuple[int, list[Mismatch]]:
    """Compare kind+value (not lines/columns) token by token. Returns (compared, mismatches)."""
    mism: list[Mismatch] = []
    n = max(len(c_tokens), len(py_tokens))
    for i in range(n):
        c = _norm(c_tokens[i].kind, c_tokens[i].value) if i < len(c_tokens) else "<missing>"
        p = _norm(py_tokens[i][0], py_tokens[i][1]) if i < len(py_tokens) else "<missing>"
        if c != p:
            mism.append(Mismatch(index=i, python=p, c=c))
    return n, mism


# ---------------------------------------------------------------- public entry point
def run_c_lexer(source: str, py_tokens: list[tuple[str, object, int]] | None = None) -> CLexerResult:
    base = CLexerResult(available=False, known_differences=KNOWN_DIFFERENCES)
    if len(source.encode("utf-8")) > MAX_SOURCE_BYTES:
        base.reason = f"source is larger than {MAX_SOURCE_BYTES // 1024} KB"
        return base
    binary = find_binary()
    if binary is None:
        base.reason = ("the C lexer is not built on this server (no C compiler found and YOG_LEXDUMP is not set)")
        return base
    base.available = True
    base.binary = binary.name
    with tempfile.TemporaryDirectory() as tmp:
        path = Path(tmp) / "input.yog"
        path.write_text(source, encoding="utf-8", newline="")
        try:
            proc = subprocess.run([str(binary), str(path)], capture_output=True, text=True,
                                  timeout=RUN_TIMEOUT_S, cwd=tmp)
        except subprocess.TimeoutExpired:
            base.reason = f"the C lexer did not finish within {RUN_TIMEOUT_S}s"
            return base
        except OSError as e:
            base.available = False
            base.reason = f"could not run the C lexer: {e}"
            return base
    base.tokens = parse_dump(proc.stdout)
    if proc.returncode == 0:
        base.ok = True
    elif proc.returncode == 1:
        # lexical error: stderr is `<file>:<line>:<col>: lexical error: <message>`
        msg = (proc.stderr or "").strip().splitlines()[-1] if proc.stderr else "lexical error"
        base.reason = re.sub(r"^.*?input\.yog:", "", msg)
    else:
        base.reason = (proc.stderr or "the C lexer failed").strip()[:200]
    if py_tokens is not None and base.ok:
        base.compared, base.mismatches = compare(base.tokens, py_tokens)
    return base
