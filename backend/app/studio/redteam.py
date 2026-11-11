"""Red-Team: try to slip past a policy. Deterministic edge cases, judged against invariants the user states
("this must be DENY when the hour is 23 to 5"). Without invariants it can only list suspicious ALLOWs, and says so."""
import re
from typing import Literal

from pydantic import BaseModel, Field

from app.core import facts
from app.engine.adapter import EngineAdapter
from app.studio.common import Budget, BudgetExceeded, PolicyRef, Shape, boundary_values, safe_check

MAX_INVARIANTS = 20
MAX_ROWS = 300
HOUR_RE = re.compile(r"^hour\(now,\s*(-?\d+)\)$")
ARG_RE = re.compile(r"^arg\(([a-z0-9_]+),\s*([a-z0-9_]+),\s*(-?\d+)\)$")


class ArgCond(BaseModel):
    tool: str = Field(max_length=100)
    param: str = Field(max_length=100)
    min: int | None = None
    max: int | None = None


class Invariant(BaseModel):
    """`action` must always be `must` whenever every stated condition holds."""
    action: str = Field(max_length=200)
    must: Literal["ALLOW", "DENY"] = "DENY"
    hour_min: int | None = Field(default=None, ge=0, le=23)
    hour_max: int | None = Field(default=None, ge=0, le=23)     # min > max means the range wraps midnight
    arg: ArgCond | None = None

    def describe(self) -> str:
        parts = []
        if self.hour_min is not None and self.hour_max is not None:
            parts.append(f"the hour is {self.hour_min} to {self.hour_max}")
        if self.arg is not None:
            lo = f"at least {self.arg.min}" if self.arg.min is not None else ""
            hi = f"at most {self.arg.max}" if self.arg.max is not None else ""
            parts.append(f"{self.arg.tool}.{self.arg.param} is " + " and ".join(x for x in (lo, hi) if x))
        when = " and ".join(parts) if parts else "always"
        return f"{self.action} must be {self.must} when {when}"


class RedTeamRequest(PolicyRef):
    invariants: list[Invariant] = Field(default_factory=list, max_length=MAX_INVARIANTS)


class Attack(BaseModel):
    family: str
    note: str
    actor: str
    action: str
    resource: str
    context: list[str]
    decision: Literal["ALLOW", "DENY"]
    reason: str
    violates: int | None = None          # index of the invariant this breaks
    suspicious: bool = False             # ALLOW where DENY is the safe expectation, with no invariant to confirm it


class FamilyCount(BaseModel):
    family: str
    total: int
    allowed: int


class RedTeamReport(BaseModel):
    policy_label: str = ""
    checked: int
    counterexamples: int
    suspicious: int
    families: list[FamilyCount]
    attacks: list[Attack]
    invariants: list[str]
    note: str


def _in_hours(h: int, lo: int, hi: int) -> bool:
    if not 0 <= h <= 23:                 # 24 or 99 is not an hour of the day, so it cannot be "inside" a stated range
        return False
    return lo <= h <= hi if lo <= hi else (h >= lo or h <= hi)


def _violation(inv: Invariant, ctx: list[str], decision: str) -> bool:
    """True when the request surely falls inside the invariant's condition and the decision breaks it."""
    if decision == inv.must:
        return False
    hour = next((int(m.group(1)) for f in ctx if (m := HOUR_RE.match(f.replace(" ", "").replace(",", ", ", 1)))), None)
    if inv.hour_min is not None and inv.hour_max is not None:
        if hour is None or not _in_hours(hour, inv.hour_min, inv.hour_max):
            return False
    if inv.arg is not None:
        t, p = facts.ident(inv.arg.tool), facts.ident(inv.arg.param)
        val = None
        for f in ctx:
            m = ARG_RE.match(f.replace(" ", "").replace(",", ", "))
            if m and m.group(1) == t and m.group(2) == p:
                val = int(m.group(3))
        if val is None:
            return False
        if (inv.arg.min is not None and val < inv.arg.min) or (inv.arg.max is not None and val > inv.arg.max):
            return False
    return True


def candidates(sh: Shape) -> list[tuple[str, str, str, str, str, list[str]]]:
    """(family, note, actor, action, resource, context), built only from what the policy mentions."""
    a0, r0 = sh.actors[0], (sh.resources or ["item"])[0]
    acts = sh.actions[:10]
    vals = boundary_values(sh.constants)
    extra = (max(sh.constants) * 2 + 1) if sh.constants else 1000
    out: list[tuple[str, str, str, str, str, list[str]]] = []
    for a in acts:
        tool = a[4:] if a.startswith("can_") else a
        keys = [(t, p) for t, p in sh.arg_keys if t == tool]
        for t, p in keys:
            for v in vals + [extra]:
                out.append(("boundary", f"{p} = {v}", a0, a, r0, [f"arg({t}, {p}, {v})"]))
                if sh.uses_hour:
                    out.append(("boundary", f"{p} = {v} at noon", a0, a, r0, ["hour(now, 12)", f"arg({t}, {p}, {v})"]))
        if sh.uses_hour:
            for h in range(24):
                out.append(("time", f"hour = {h}", a0, a, r0, [f"hour(now, {h})"]))
        out.append(("dropped_context", "no context facts at all", a0, a, r0, []))
        if sh.uses_hour:
            out.append(("dropped_context", "arguments missing, hour given", a0, a, r0, ["hour(now, 12)"]))
        for t, p in keys:
            out.append(("dropped_context", "hour missing, argument given", a0, a, r0, [f"arg({t}, {p}, {vals[len(vals) // 2]})"]))
        for who in ("stranger", "admin", "root", "guest"):
            out.append(("unknown_actor", f"actor '{who}'", who, a, r0, ["hour(now, 12)"] if sh.uses_hour else []))
        for res in ("unknown_res", "all_resources"):
            out.append(("unknown_resource", f"resource '{res}'", a0, a, res, ["hour(now, 12)"] if sh.uses_hour else []))
        for who in (a0.capitalize(), a0.upper(), a0 + " "):
            out.append(("normalisation", f"actor spelled {who!r}", who, a, r0, ["hour(now, 12)"] if sh.uses_hour else []))
        for t, p in keys:
            for txt in ("none", "unknown"):
                out.append(("type_confusion", f"{p} given as the word '{txt}'", a0, a, r0, [f"arg({t}, {p}, {txt})"]))
            for v in (0, 99999, 2147483648):
                out.append(("extreme", f"{p} = {v}", a0, a, r0, [f"arg({t}, {p}, {v})"]))
        if sh.uses_hour:
            for h in (24, 99):
                out.append(("extreme", f"hour = {h} (not a real hour)", a0, a, r0, [f"hour(now, {h})"]))
    return out


SUSPICIOUS = {"dropped_context", "unknown_actor", "unknown_resource", "normalisation", "type_confusion", "extreme"}


def augment(sh: Shape, invariants: list[Invariant]) -> Shape:
    """A promise can be about something the policy never mentions (that is exactly the bug to catch: a policy that
    ignores the hour). So hours, arguments and numbers named by the promises are attacked too."""
    actions = list(sh.actions)
    keys = list(sh.arg_keys)
    nums = set(sh.constants)
    uses_hour = sh.uses_hour
    for inv in invariants:
        if inv.action and inv.action not in actions:
            actions.append(inv.action)
        if inv.hour_min is not None and inv.hour_max is not None:
            uses_hour = True
            nums.update((inv.hour_min, inv.hour_max))
        if inv.arg is not None:
            k = (facts.ident(inv.arg.tool), facts.ident(inv.arg.param))
            if k not in keys:
                keys.append(k)
            nums.update(x for x in (inv.arg.min, inv.arg.max) if x is not None)
    return sh.model_copy(update={"actions": actions, "arg_keys": keys, "constants": sorted(nums), "uses_hour": uses_hour})


def run(adapter: EngineAdapter, source: str, sh: Shape, invariants: list[Invariant], budget: Budget) -> RedTeamReport:
    sh = augment(sh, invariants)
    rows: list[Attack] = []
    counts: dict[str, list[int]] = {}
    checked = 0
    try:
        for family, note, actor, action, resource, ctx in candidates(sh):
            budget.spend()
            r = safe_check(adapter, source, actor, action, resource, ctx)
            checked += 1
            c = counts.setdefault(family, [0, 0])
            c[0] += 1
            c[1] += r.decision == "ALLOW"
            bad = next((i for i, inv in enumerate(invariants) if inv.action == action and _violation(inv, ctx, r.decision)), None)
            sus = bad is None and r.decision == "ALLOW" and family in SUSPICIOUS
            if bad is not None or sus or r.decision == "ALLOW":
                rows.append(Attack(family=family, note=note, actor=actor, action=action, resource=resource, context=ctx,
                                   decision=r.decision, reason=r.reason, violates=bad, suspicious=sus))
    except BudgetExceeded:
        pass
    rows.sort(key=lambda a: (a.violates is None, not a.suspicious, a.family))
    cx = sum(1 for a in rows if a.violates is not None)
    sus_n = sum(1 for a in rows if a.suspicious)
    note = ("Counterexamples are requests that break an invariant you stated. " if invariants else
            "No invariants were given, so nothing can be called a violation: the rows below are only ALLOWs that look "
            "unexpected, and you decide whether each is fine. ") + "Not finding a counterexample does not prove the policy safe."
    return RedTeamReport(checked=checked, counterexamples=cx, suspicious=sus_n,
                         families=[FamilyCount(family=k, total=v[0], allowed=v[1]) for k, v in counts.items()],
                         attacks=rows[:MAX_ROWS], invariants=[i.describe() for i in invariants], note=note)

