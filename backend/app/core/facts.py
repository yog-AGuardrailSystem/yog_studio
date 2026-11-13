"""Turn a real tool call into YOG context facts. THE one normalisation used by the runtime, the device
simulator and the evaluator (docs/conventions.md).

The engine lexer has no decimals/booleans, treats an Uppercase-initial word as a variable, and facts may not
contain variables -- so raw values must be normalised or the engine raises / mis-parses.
"""
import re
from typing import Any

DAYS = ["mon", "tue", "wed", "thu", "fri", "sat", "sun"]


def ident(value: Any) -> str:
    """lowercase snake_case constant that the engine lexer accepts as an IDENT."""
    s = re.sub(r"[^a-z0-9]+", "_", str(value).strip().lower()).strip("_")
    if not s:
        return "empty"
    return f"v_{s}" if s[0].isdigit() else s


class FactError(ValueError):
    """An argument the engine cannot represent faithfully. The call must be DENIED (never rounded or merged)."""


def pathlike(s: str) -> bool:
    """Text that names a place: ident() would merge ../notes.txt, /notes.txt and NOTES.TXT into one constant."""
    return "/" in s or "\\" in s or ".." in s


def value(v: Any) -> int | str | None:
    """bool -> 1/0, int -> int, whole float -> int, str -> ident, None -> skipped.
    Raises FactError for a decimal (the lexer has no decimals, and rounding let 28.4 pass a limit of 28) and for a
    path-like string (ident() is not one-to-one on those, so a path allowlist would match other paths)."""
    if v is None:
        return None
    if isinstance(v, bool):
        return 1 if v else 0
    if isinstance(v, int):
        return v
    if isinstance(v, float):
        if v != v or v in (float("inf"), float("-inf")) or v != int(v):
            raise FactError(f"{v!r} is not a whole number and cannot be compared exactly; pass a whole number")
        return int(v)
    if isinstance(v, (list, tuple, dict, set)):
        return len(v)                   # collections are reduced to their size (e.g. recipient_count)
    if isinstance(v, str) and pathlike(v):
        raise FactError("a path-like value cannot be matched exactly (different paths would normalise to the same name)")
    return ident(v)


def fact(pred: str, *args: Any) -> str:
    return f"{pred}({', '.join(str(a) for a in args)})"


def facts_from_call(tool: str, args: dict[str, Any], hour: int, day: str) -> list[str]:
    """Context facts for one call. hour (0-23) and day (mon..sun) are always included."""
    out = [fact("hour", "now", int(hour) % 24), fact("day", "now", ident(day))]
    t = ident(tool)
    for name, raw in args.items():
        try:
            v = value(raw)
        except FactError as e:
            raise FactError(f"argument {name!r}: {e}") from e
        if v is not None:
            out.append(fact("arg", t, ident(name), v))
    return out
