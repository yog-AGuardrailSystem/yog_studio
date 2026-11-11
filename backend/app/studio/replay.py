"""Trace Replay: take a recorded list of tool calls (data only, nothing is executed) and ask a policy what it would
have said to each. With a second policy it shows which calls change. Reads JSONL or CSV, at most MAX_ROWS rows."""
import csv
import io
import json
from typing import Literal

from pydantic import BaseModel, Field

from app.core import facts
from app.engine.adapter import EngineAdapter
from app.studio.common import Budget, PolicyRef, call_request, safe_check

MAX_ROWS = 500
MAX_TEXT = 200_000


class CallRow(BaseModel):
    tool: str
    args: dict = Field(default_factory=dict)
    hour: int = 12
    day: str = "mon"
    actor: str = "agent"


class ReplayRequest(BaseModel):
    policy: PolicyRef = Field(default_factory=PolicyRef)
    compare: PolicyRef | None = None
    text: str = Field(default="", max_length=MAX_TEXT)
    format: Literal["jsonl", "csv", "audit"] = "jsonl"      # "audit": ignore text, replay this visitor's audit log


class ReplayRow(BaseModel):
    n: int
    tool: str
    args: dict
    hour: int
    day: str
    decision: Literal["ALLOW", "DENY"]
    reason: str
    other: Literal["ALLOW", "DENY"] | None = None
    other_reason: str = ""
    changed: bool = False


class ReplaySummary(BaseModel):
    total: int
    allowed: int
    denied: int
    other_allowed: int | None = None
    changed: int = 0


class ReplayResult(BaseModel):
    policy_label: str = ""
    other_label: str | None = None
    rows: list[ReplayRow]
    summary: ReplaySummary
    problems: list[str]


def _row(d: dict, n: int) -> tuple[CallRow | None, str | None]:
    try:
        tool = d.get("tool")
        if not isinstance(tool, str) or not tool.strip() or len(tool) > 100:
            return None, f"row {n}: 'tool' must be a name"
        args = d.get("args") or {}
        if isinstance(args, str):
            args = json.loads(args) if args.strip() else {}
        if not isinstance(args, dict):
            return None, f"row {n}: 'args' must be an object"
        hour = int(d.get("hour", d.get("sim_hour", 12)))
        day = str(d.get("day", d.get("sim_day", "mon"))).strip().lower()
        if not 0 <= hour <= 23:
            return None, f"row {n}: hour must be 0-23"
        if day not in facts.DAYS:
            return None, f"row {n}: day must be one of {', '.join(facts.DAYS)}"
        return CallRow(tool=tool.strip(), args=args, hour=hour, day=day, actor=str(d.get("actor") or "agent")[:100]), None
    except (ValueError, TypeError) as e:
        return None, f"row {n}: {type(e).__name__}"


def parse_rows(text: str, fmt: str) -> tuple[list[CallRow], list[str]]:
    rows: list[CallRow] = []
    problems: list[str] = []
    items: list[dict] = []
    if fmt == "csv":
        try:
            for rec in csv.DictReader(io.StringIO(text)):
                d = {k.strip(): v for k, v in rec.items() if k}
                extra = {k[4:]: _num(v) for k, v in d.items() if k.startswith("arg_") and v not in (None, "")}
                if extra:
                    base = d.get("args")
                    d["args"] = {**(json.loads(base) if isinstance(base, str) and base.strip() else {}), **extra}
                items.append(d)
        except (csv.Error, ValueError) as e:
            problems.append(f"the CSV could not be read ({type(e).__name__})")
    else:
        for i, ln in enumerate(text.split("\n"), 1):
            if not ln.strip():
                continue
            try:
                d = json.loads(ln)
                if not isinstance(d, dict):
                    raise ValueError("not an object")
                items.append(d)
            except ValueError:
                problems.append(f"line {i}: not a JSON object")
    for i, d in enumerate(items[:MAX_ROWS], 1):
        row, why = _row(d, i)
        if row:
            rows.append(row)
        elif why:
            problems.append(why)
    if len(items) > MAX_ROWS:
        problems.append(f"only the first {MAX_ROWS} rows were used")
    return rows, problems[:30]


def _num(v: str):
    try:
        return int(v)
    except (TypeError, ValueError):
        return v


def replay(adapter: EngineAdapter, source: str, other: str | None, rows: list[CallRow], budget: Budget) -> tuple[list[ReplayRow], ReplaySummary]:
    out: list[ReplayRow] = []
    for n, r in enumerate(rows, 1):
        actor, action, resource, ctx = call_request(r.tool, r.args, r.hour, r.day, r.actor)
        budget.spend(2 if other else 1)
        a = safe_check(adapter, source, actor, action, resource, ctx)
        b = safe_check(adapter, other, actor, action, resource, ctx) if other else None
        out.append(ReplayRow(n=n, tool=r.tool, args=r.args, hour=r.hour, day=r.day, decision=a.decision, reason=a.reason,
                             other=b.decision if b else None, other_reason=b.reason if b else "",
                             changed=bool(b and b.decision != a.decision)))
    allowed = sum(1 for r in out if r.decision == "ALLOW")
    return out, ReplaySummary(total=len(out), allowed=allowed, denied=len(out) - allowed,
                              other_allowed=sum(1 for r in out if r.other == "ALLOW") if other else None,
                              changed=sum(1 for r in out if r.changed))
