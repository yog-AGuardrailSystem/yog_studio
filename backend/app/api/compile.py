"""The compiler explorer API: tokens, AST, diagnostics (/compile), running a program's queries (/run), and the
real C lexer side by side with the reference (/compile/c-lexer)."""
import re
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from app.api.deps import get_adapter
from app.engine.adapter import CheckResult, CompileInfo, Diagnostic, EngineAdapter, EngineError
from app.engine.c_lexer import CLexerResult, run_c_lexer

router = APIRouter()

MAX_SOURCE_CHARS = 200_000
MAX_QUERIES = 200
MAX_TRACE_LINES = 120


class SourceRequest(BaseModel):
    source: str = Field(max_length=MAX_SOURCE_CHARS)


@router.post("/compile", response_model=CompileInfo)
def compile_source(req: SourceRequest, adapter: EngineAdapter = Depends(get_adapter)) -> CompileInfo:
    try:
        return adapter.compile_info(req.source)
    except EngineError as e:
        raise HTTPException(status_code=501, detail=str(e))


# ---------------------------------------------------------------- the real C lexer, side by side
class CLexerResponse(CLexerResult):
    python_ok: bool = True
    python_error: str | None = None


@router.post("/compile/c-lexer", response_model=CLexerResponse)
def compare_c_lexer(req: SourceRequest, adapter: EngineAdapter = Depends(get_adapter)) -> CLexerResponse:
    try:
        info = adapter.compile_info(req.source)
    except EngineError as e:
        raise HTTPException(status_code=501, detail=str(e))
    # The reference tokenizes before it parses; if tokens exist the tokenizer accepted the input.
    tokenized = bool(info.tokens)
    py_tokens = [(t.kind, t.value, t.line) for t in info.tokens] if tokenized else None
    res = run_c_lexer(req.source, py_tokens)
    out = CLexerResponse(**res.model_dump())
    if not tokenized and info.diagnostics:
        out.python_ok = False
        out.python_error = info.diagnostics[0].message
    return out


# ---------------------------------------------------------------- running a program's queries
def _strip_comment(line: str) -> tuple[str, str]:
    """(code, comment) split at the first # that is not inside a quoted string."""
    in_str = False
    for i, ch in enumerate(line):
        if ch == '"':
            in_str = not in_str
        elif ch == "#" and not in_str:
            return line[:i], line[i + 1:]
    return line, ""


_WORDS = re.compile(r"\b(TRUE|ALLOW|FALSE|DENY)\b")


def parse_expectation(line: str) -> Literal["ALLOW", "DENY"] | None:
    """The team's convention: a trailing comment such as `# staging -> expect TRUE` or `# -> DENY`.
    TRUE/ALLOW = allowed, FALSE/DENY = denied. Mixed or absent = no expectation."""
    _, comment = _strip_comment(line)
    words = set(_WORDS.findall(comment))
    pos, neg = words & {"TRUE", "ALLOW"}, words & {"FALSE", "DENY"}
    if pos and not neg:
        return "ALLOW"
    if neg and not pos:
        return "DENY"
    return None


class AdHoc(BaseModel):
    actor: str
    action: str
    resource: str
    context: list[str] = Field(default_factory=list)


class RunRequest(SourceRequest):
    adhoc: AdHoc | None = None


class QueryResult(BaseModel):
    line: int
    text: str
    kind: Literal["decision", "fact-query", "unsupported"]
    decision: Literal["ALLOW", "DENY"] | None = None
    answer: bool | None = None
    reason: str = ""
    trace: list[str] = Field(default_factory=list)
    bindings: list[dict] = Field(default_factory=list)
    expected: Literal["ALLOW", "DENY"] | None = None
    passed: bool | None = None            # None = no expectation written


class RunResponse(BaseModel):
    ok: bool
    diagnostics: list[Diagnostic] = Field(default_factory=list)
    results: list[QueryResult] = Field(default_factory=list)
    passed: int = 0
    failed: int = 0
    untested: int = 0
    truncated: bool = False
    adhoc: CheckResult | None = None
    adhoc_error: str | None = None


@router.post("/run", response_model=RunResponse)
def run_program(req: RunRequest, adapter: EngineAdapter = Depends(get_adapter)) -> RunResponse:
    """Evaluate every `query` of the program, and optionally one ad-hoc request with per-request context facts.

    Decision predicates always go through check() (DENY beats ALLOW). Never through the engine's plain query, which
    ignores DENY clauses (docs/engine_issues.md)."""
    try:
        info = adapter.compile_info(req.source)
    except EngineError as e:
        raise HTTPException(status_code=501, detail=str(e))
    out = RunResponse(ok=info.ok, diagnostics=info.diagnostics)
    if not info.ok:
        return out
    roles = {(p.name, p.arity): p.role for p in info.predicates}
    src_lines = req.source.splitlines()
    specs = adapter.queries(req.source)
    if len(specs) > MAX_QUERIES:
        specs, out.truncated = specs[:MAX_QUERIES], True
    for q in specs:
        text_line = src_lines[q.line - 1] if 0 < q.line <= len(src_lines) else ""
        expected = parse_expectation(text_line)
        arity = len(q.terms)
        role = roles.get((q.pred, arity))
        res = QueryResult(line=q.line, text=q.text, kind="unsupported", expected=expected)
        ground = all("const" in t for t in q.terms)
        if role == "decision":
            if arity == 2 and ground:
                r = adapter.check(req.source, q.terms[0]["const"], q.pred, q.terms[1]["const"], [])
                res.kind, res.decision, res.reason, res.trace = "decision", r.decision, r.reason, r.trace[:MAX_TRACE_LINES]
            else:
                res.reason = "decision queries need exactly two constant arguments: the actor and the resource"
        elif role in ("fact", "rule"):
            a = adapter.ask(req.source, q.pred, q.terms)
            res.kind, res.answer, res.bindings, res.trace = "fact-query", a.answer, a.bindings, a.trace[:MAX_TRACE_LINES]
            res.reason = "holds" if a.answer else "does not hold"
        else:
            res.reason = f"{q.pred}/{arity} is not defined"
        if expected is not None and res.kind != "unsupported":
            got = res.decision if res.kind == "decision" else ("ALLOW" if res.answer else "DENY")
            res.passed = got == expected
        out.results.append(res)
    out.passed = sum(1 for r in out.results if r.passed is True)
    out.failed = sum(1 for r in out.results if r.passed is False)
    out.untested = sum(1 for r in out.results if r.passed is None)
    if req.adhoc is not None:
        try:
            out.adhoc = adapter.check(req.source, req.adhoc.actor, req.adhoc.action, req.adhoc.resource,
                                      req.adhoc.context)
        except EngineError as e:
            out.adhoc_error = str(e)
    return out
