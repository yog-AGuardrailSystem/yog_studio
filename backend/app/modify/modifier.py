"""Minimal-diff script modifier: adds `@yog_guard("<tool>")` above each tool function and one import line.

Never rewrites the file: output is the original text with whole lines INSERTED (verified: zero removed lines).
"""
import ast
import difflib

from pydantic import BaseModel

from app.core.models import DetectResult, Tool
from app.core.pyast import parse_source
from app.detect.detector import detect, scan_mcp, tool_decorator_base
from app.extract.ast_extractor import extract_tools

IMPORT_LINE = "from yog_runtime import yog_guard"


class ModifyResult(BaseModel):
    patched_source: str
    diff: str
    guarded: list[str]
    skipped: list[str]            # human-readable reasons
    already_guarded: list[str]
    added_lines: int
    removed_lines: int


class ModifyError(ValueError):
    pass


def _eol(source: str) -> str:
    return "\r\n" if "\r\n" in source else "\n"


def _already(fn: ast.AST) -> bool:
    for d in fn.decorator_list:
        t = d.func if isinstance(d, ast.Call) else d
        if (isinstance(t, ast.Name) and t.id == "yog_guard") or (isinstance(t, ast.Attribute) and t.attr == "yog_guard"):
            return True
    return False


def _import_insert_index(tree: ast.Module, lines: list[str]) -> int:
    """0-based line index at which to insert the import: after shebang/coding comments, the module docstring and
    any `from __future__` imports (inserting before a __future__ import is a SyntaxError)."""
    idx = 0
    while idx < len(lines) and idx < 2 and lines[idx].startswith("#") and (
            lines[idx].startswith("#!") or "coding" in lines[idx]):
        idx += 1
    for i, node in enumerate(tree.body):
        is_doc = i == 0 and isinstance(node, ast.Expr) and isinstance(getattr(node, "value", None), ast.Constant) \
            and isinstance(node.value.value, str)
        is_future = isinstance(node, ast.ImportFrom) and node.module == "__future__"
        if is_doc or is_future:
            idx = max(idx, node.end_lineno)
        else:
            break
    return idx


def modify(source: str, only: list[str] | None = None, filename: str = "agent.py") -> ModifyResult:
    tree = parse_source(source)
    detected: DetectResult = detect(tree, source)
    if detected.kind == "unknown":
        raise ModifyError("cannot modify: no MCP server or function-calling tools were detected")
    tools: list[Tool] = extract_tools(tree, detected)
    wanted = set(only) if only else None

    funcs = {id(n): n for n in ast.walk(tree) if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef))}
    targets: list[tuple[str, ast.AST]] = []       # (tool name, function node)
    skipped: list[str] = []
    if detected.kind == "mcp_server":
        info = scan_mcp(tree)
        for fn in sorted(funcs.values(), key=lambda f: f.lineno):
            for dec in fn.decorator_list:
                if tool_decorator_base(dec) is not None and dec.lineno in info.tool_decorator_lines:
                    name = next((t.name for t in tools if t.source_line == fn.lineno), fn.name)
                    targets.append((name, fn))
                    break
    else:
        by_name = {n.name: n for n in tree.body if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef))}
        for t in tools:
            if t.name in by_name:
                targets.append((t.name, by_name[t.name]))
            else:
                skipped.append(f"{t.name}: declared in the tools schema but no function with that name was found in this file")

    guarded, already = [], []
    inserts: list[tuple[int, str]] = []            # (0-based line index to insert before, text w/o eol)
    for name, fn in targets:
        if wanted is not None and name not in wanted:
            continue
        if _already(fn):
            already.append(name)
            continue
        indent = " " * fn.col_offset
        inserts.append((fn.lineno - 1, f'{indent}@yog_guard("{name}")'))
        guarded.append(name)

    if wanted:
        known = {n for n, _ in targets}
        skipped += [f"{n}: no such tool" for n in sorted(wanted - known)]
    if not guarded:
        return ModifyResult(patched_source=source, diff="", guarded=[], skipped=skipped,
                            already_guarded=already, added_lines=0, removed_lines=0)

    eol = _eol(source)
    lines = source.splitlines(keepends=True)
    imp_at = _import_insert_index(tree, [l.rstrip("\r\n") for l in lines])
    inserts.append((imp_at, IMPORT_LINE))
    # apply bottom-up so indices stay valid; the import goes before a decorator inserted at the same index
    for idx, text in sorted(inserts, key=lambda x: (x[0], x[1] != IMPORT_LINE), reverse=True):
        lines.insert(idx, text + eol)
    patched = "".join(lines)
    try:
        ast.parse(patched)
    except SyntaxError as e:                      # defensive: never hand back broken code
        raise ModifyError(f"internal error: patched file does not parse ({e.msg}, line {e.lineno})") from e

    diff = "".join(difflib.unified_diff(source.splitlines(keepends=True), patched.splitlines(keepends=True),
                                        fromfile=f"a/{filename}", tofile=f"b/{filename}"))
    added = sum(1 for l in diff.splitlines() if l.startswith("+") and not l.startswith("+++"))
    removed = sum(1 for l in diff.splitlines() if l.startswith("-") and not l.startswith("---"))
    return ModifyResult(patched_source=patched, diff=diff, guarded=guarded, skipped=skipped,
                        already_guarded=already, added_lines=added, removed_lines=removed)
