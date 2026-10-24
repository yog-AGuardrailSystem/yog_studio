"""Scenario generation.

Two kinds, deliberately kept apart so a policy is never graded against itself:
  * independent    expectation comes from the English rules (LLM, which never sees the YOG) or from the user.
  * characterization  deterministic probes (boundaries, no-context). `expected` is just what the engine did,
                     shown as UNCONFIRMED until a human confirms/flips it. Excluded from the pass percentage.
"""
import json
import re
from typing import Literal

from pydantic import BaseModel, Field

from app.core.models import Tool
from app.engine.adapter import EngineAdapter, EngineError
from app.llm.provider import LLMError, LLMProvider, load_prompt
from app.translate.translator import decision_name, format_tools, render

CONTEXT_PREDS = ("hour", "day", "arg")
HOURS = [0, 3, 12, 23]
MAX_PER_ACTION = 14


class Scenario(BaseModel):
    actor: str
    action: str
    resource: str
    context: list[str] = Field(default_factory=list)
    expected: Literal["ALLOW", "DENY"]
    source: Literal["generated", "user"] = "generated"
    unconfirmed: bool = False          # characterization row: expected == engine output, not independent
    note: str = ""


class ScenarioResult(Scenario):
    actual: Literal["ALLOW", "DENY"] | None = None
    reason: str = ""
    trace: list[str] = Field(default_factory=list)
    passed: bool = False
    error: str | None = None


# ----------------------------------------------------------------- deterministic probes

def _constants(info: dict, pred: str) -> list[int]:
    """Integer constants compared against variables, used to pick boundary values."""
    nums: set[int] = set()
    for c in info["clauses"]:
        for g in c["body"]:
            if g["type"] == "cmp":
                for side in (g["lhs"], g["rhs"]):
                    if "const" in side and isinstance(side["const"], int):
                        nums.add(side["const"])
    return sorted(nums)


def _actors(info: dict) -> list[str]:
    actors = []
    for f in info["facts"]:
        if f["pred"] == "role" and f["args"] and "const" in f["args"][0]:
            a = str(f["args"][0]["const"])
            if a != "placeholder" and a not in actors:
                actors.append(a)
    return (actors[:2] or []) + ["stranger"]


def _resources(info: dict) -> list[str]:
    res = []
    for c in info["clauses"]:
        for g in c["body"]:
            if g["type"] == "cmp":
                for side in (g["lhs"], g["rhs"]):
                    if "const" in side and isinstance(side["const"], str) and side["const"] not in res:
                        res.append(side["const"])
    return (res[:2]) + ["item"]


def _arg_keys(info: dict) -> list[tuple[str, str]]:
    keys = []
    for c in info["clauses"]:
        for g in c["body"]:
            if g["type"] == "atom" and g["pred"] == "arg" and len(g["args"]) == 3:
                a, b = g["args"][0], g["args"][1]
                if "const" in a and "const" in b and (str(a["const"]), str(b["const"])) not in keys:
                    keys.append((str(a["const"]), str(b["const"])))
    return keys


def characterization(adapter: EngineAdapter, policy: str) -> tuple[list[Scenario], list[str]]:
    """Probe every decision predicate. Returns (scenarios, warnings)."""
    info = adapter.program_info(policy)
    preds = sorted({c["head"]["pred"] for c in info["clauses"] if c["kind"] in ("allow", "deny")})
    nums = _constants(info, "")
    used = {g["pred"] for c in info["clauses"] for g in c["body"] if g["type"] == "atom"}
    warnings: list[str] = []
    out: list[Scenario] = []
    actors, resources = _actors(info), _resources(info)
    arg_keys = _arg_keys(info)
    uses_hour = "hour" in used

    def add(actor, action, resource, ctx, note):
        try:
            r = adapter.check(policy, actor, action, resource, ctx)
        except EngineError:
            return None
        out.append(Scenario(actor=actor, action=action, resource=resource, context=ctx, expected=r.decision,
                            source="generated", unconfirmed=True, note=note))
        return r

    for p in preds:
        for a in actors:
            for res in resources[:2]:
                r = add(a, p, res, [], "no context supplied")
                if r and r.decision == "ALLOW" and (uses_hour or arg_keys) and a != "stranger":
                    warnings.append(f"{p}: ALLOWED for '{a}' with no time/argument information. "
                                    f"Deny rules that need hour/arg do not fire without it.")
        if uses_hour:
            hours = sorted({h for h in HOURS} | {h for n in nums for h in (n - 1, n, n + 1) if 0 <= h <= 23})
            for h in hours:
                add(actors[0], p, resources[0], [f"hour(now, {h})"], f"hour = {h}")
        for tool, param in arg_keys:
            for n in sorted({0} | {x for c in nums for x in (c - 1, c, c + 1) if x >= 0}):
                add(actors[0], p, resources[0], [f"arg({tool}, {param}, {n})"], f"{param} = {n}")
    # drop exact duplicates
    seen, uniq = set(), []
    for s in out:
        k = (s.actor, s.action, s.resource, tuple(s.context))
        if k not in seen:
            seen.add(k)
            uniq.append(s)
    # keep the table readable: at most MAX_PER_ACTION probes per decision predicate (no-context rows come first)
    kept, count = [], {}
    for sc in uniq:
        count[sc.action] = count.get(sc.action, 0) + 1
        if count[sc.action] <= MAX_PER_ACTION:
            kept.append(sc)
    return kept, sorted(set(warnings))


# ----------------------------------------------------------------- LLM (independent)

JSON_RE = re.compile(r"\[.*\]", re.S)


def generate_independent(rules: list[str], tools: list[Tool], provider: LLMProvider) -> tuple[list[Scenario], list[str]]:
    """The model sees ONLY the English rules and the tools -- never the YOG -- so expectations are independent."""
    problems: list[str] = []
    prompt = render(load_prompt("scenarios"), tools=format_tools(tools),
                    rules="\n".join(f"{i}. {r}" for i, r in enumerate(rules, 1)))
    try:
        reply = provider.generate(prompt)
    except LLMError as e:
        return [], [f"scenario generation failed: {e}"]
    m = JSON_RE.search(reply)
    if not m:
        return [], ["scenario generator returned no JSON list"]
    try:
        raw = json.loads(m.group(0))
    except json.JSONDecodeError:
        return [], ["scenario generator returned invalid JSON"]
    names = {decision_name(t.name) for t in tools}
    out = []
    for i, row in enumerate(raw if isinstance(raw, list) else []):
        try:
            ctx = [str(c) for c in row.get("context", [])]
            exp = str(row["expected"]).upper()
            if exp not in ("ALLOW", "DENY"):
                raise ValueError("expected must be ALLOW or DENY")
            action = str(row["action"])
            if names and action not in names:
                raise ValueError(f"unknown action {action}")
            out.append(Scenario(actor=str(row["actor"]), action=action, resource=str(row["resource"]),
                                context=ctx, expected=exp, source="generated", note=str(row.get("note", ""))))
        except (KeyError, ValueError, AttributeError, TypeError) as e:
            problems.append(f"scenario {i + 1} skipped: {e}")      # one bad row never fails the run
    return out, problems
