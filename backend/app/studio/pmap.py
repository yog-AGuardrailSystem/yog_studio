"""Policy Map: the decision for every combination of two inputs (hour, day, or a tool argument), as a grid."""
from typing import Literal

from pydantic import BaseModel, Field

from app.core import facts
from app.engine.adapter import EngineAdapter
from app.studio.common import Budget, PolicyRef, Shape, boundary_values, safe_check_many

MAX_AXIS_VALUES = 60


class Axis(BaseModel):
    kind: Literal["hour", "day", "arg"]
    tool: str | None = Field(default=None, max_length=100)        # arg only
    param: str | None = Field(default=None, max_length=100)       # arg only
    values: list[int] | None = Field(default=None, max_length=MAX_AXIS_VALUES)   # arg only


class MapRequest(PolicyRef):
    actor: str = Field(default="agent", max_length=200)
    action: str = Field(max_length=200)
    resource: str = Field(default="item", max_length=200)
    context: list[str] = Field(default_factory=list, max_length=40)   # fixed facts held while the axes vary
    x: Axis
    y: Axis | None = None


class MapResult(BaseModel):
    policy_label: str = ""
    x_title: str
    y_title: str
    x_labels: list[str]
    y_labels: list[str]
    cells: list[list[Literal["A", "D"]]]          # cells[row][col]
    reasons: list[list[str]]
    allow: int
    deny: int


def _expand(axis: Axis) -> tuple[str, list[str], list[str]]:
    """(title, labels, one fact per label)."""
    if axis.kind == "hour":
        return "hour of day", [f"{h:02d}" for h in range(24)], [f"hour(now, {h})" for h in range(24)]
    if axis.kind == "day":
        return "day of week", list(facts.DAYS), [f"day(now, {d})" for d in facts.DAYS]
    if not axis.tool or not axis.param or not axis.values:
        raise ValueError("an argument axis needs a tool, a parameter and at least one value")
    t, p = facts.ident(axis.tool), facts.ident(axis.param)
    vals = sorted({int(v) for v in axis.values})
    return f"{t}.{p}", [str(v) for v in vals], [f"arg({t}, {p}, {v})" for v in vals]


def _drop(base: list[str], axis: Axis | None) -> list[str]:
    """The fixed facts, minus any fact the axis is about to supply."""
    if axis is None:
        return list(base)
    prefix = {"hour": "hour(now", "day": "day(now"}.get(axis.kind) or f"arg({facts.ident(axis.tool or '')},{facts.ident(axis.param or '')},"
    return [f for f in base if not f.replace(" ", "").startswith(prefix.replace(" ", ""))]


def build_map(adapter: EngineAdapter, source: str, req: MapRequest, budget: Budget) -> MapResult:
    if req.y is not None and req.y.kind == req.x.kind and req.y.kind != "arg":
        raise ValueError("the two axes must be different inputs")
    xt, xl, xf = _expand(req.x)
    if req.y is None:
        yt, yl, yf = "", [""], [""]
    else:
        yt, yl, yf = _expand(req.y)
    base = _drop(_drop(req.context, req.x), req.y)
    cells: list[list[str]] = []
    reasons: list[list[str]] = []
    allow = deny = 0
    budget.spend(len(xf) * len(yf))
    grid = [base + [fx] + ([fy] if fy else []) for fy in yf for fx in xf]
    results = iter(safe_check_many(adapter, source, [(req.actor, req.action, req.resource, ctx) for ctx in grid]))
    for fy in yf:
        row, rrow = [], []
        for fx in xf:
            r = next(results)
            row.append("A" if r.decision == "ALLOW" else "D")
            rrow.append(r.reason)
            allow += r.decision == "ALLOW"
            deny += r.decision != "ALLOW"
        cells.append(row)
        reasons.append(rrow)
    return MapResult(x_title=xt, y_title=yt, x_labels=xl, y_labels=yl, cells=cells, reasons=reasons,  # type: ignore[arg-type]
                     allow=allow, deny=deny)


class ArgKey(BaseModel):
    tool: str
    param: str
    values: list[int]


class MapSuggest(BaseModel):
    policy_label: str = ""
    actions: list[str]
    actors: list[str]
    resources: list[str]
    uses_hour: bool
    uses_day: bool
    arg_keys: list[ArgKey]


def suggest(sh: Shape) -> MapSuggest:
    vals = boundary_values(sh.constants)
    return MapSuggest(actions=sh.actions, actors=sh.actors, resources=sh.resources or ["item"],
                      uses_hour=sh.uses_hour, uses_day=sh.uses_day,
                      arg_keys=[ArgKey(tool=t, param=p, values=vals) for t, p in sh.arg_keys])
