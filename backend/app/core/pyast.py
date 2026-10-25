"""Small static-analysis helpers. Uploaded code is only ever parsed, never imported or executed."""
import ast
from typing import Any

MAX_SOURCE_BYTES = 1_000_000


class SourceError(ValueError):
    """The uploaded text is not analysable Python source."""


def parse_source(source: str) -> ast.Module:
    if len(source.encode("utf-8", errors="ignore")) > MAX_SOURCE_BYTES:
        raise SourceError("file too large (limit 1 MB)")
    try:
        return ast.parse(source)
    except SyntaxError as e:
        raise SourceError(f"not valid Python: {e.msg} (line {e.lineno})") from e
    except (ValueError, RecursionError, MemoryError) as e:
        raise SourceError(f"could not parse file: {type(e).__name__}") from e


def dotted(node: ast.AST) -> str | None:
    """`os.path.join` -> 'os.path.join'; None for anything that isn't a plain dotted name."""
    if isinstance(node, ast.Name):
        return node.id
    if isinstance(node, ast.Attribute):
        base = dotted(node.value)
        return f"{base}.{node.attr}" if base else None
    return None


def const_value(node: ast.AST) -> Any:
    """Literal-only evaluation of dict/list/str/num nodes. Returns _NOPE for anything dynamic."""
    if isinstance(node, ast.Constant):
        return node.value
    if isinstance(node, ast.Dict):
        out = {}
        for k, v in zip(node.keys, node.values):
            if k is None:                       # **spread
                continue
            key = const_value(k)
            if key is NOPE:
                continue
            out[key] = const_value(v)
        return out
    if isinstance(node, (ast.List, ast.Tuple)):
        return [const_value(e) for e in node.elts]
    return NOPE


class _Nope:
    def __repr__(self) -> str:
        return "<dynamic>"


NOPE = _Nope()


def line_text(lines: list[str], lineno: int) -> str:
    return lines[lineno - 1].strip() if 0 < lineno <= len(lines) else ""


def evidence(lines: list[str], lineno: int) -> str:
    return f"line {lineno}: {line_text(lines, lineno)}"
