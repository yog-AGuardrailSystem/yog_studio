"""Gap Analyzer: static checks on a policy. Each finding says whether it is *proved* (follows from the text alone) or
a *heuristic* (a probe or a rule of thumb). Nothing here runs an agent or calls an LLM."""
from typing import Literal

from pydantic import BaseModel, Field

from app.engine.adapter import EngineAdapter, EngineError
from app.evaluate.scenarios import Scenario
from app.studio.common import Budget, Shape, boundary_values, safe_check, shape
from app.translate.translator import decision_name

CONTEXT_PREDS = ("hour", "day", "arg")
MAX_PROBES = 400
PROBES_PER_ACTION = 60


class Finding(BaseModel):
    id: str
    severity: Literal["warning", "info"]
    certainty: Literal["proved", "heuristic"]
    title: str
    detail: str
    lines: list[int] = Field(default_factory=list)
    action: str | None = None


class ClauseCoverage(BaseModel):
    line: int
    kind: Literal["allow", "deny"]
    head: str
    matched: int           # probes where this clause fired
    tried: int             # probes where its head applied at all


class GapReport(BaseModel):
    policy_label: str = ""
    source: str = ""       # the policy text, so the page can highlight the lines a finding names
    findings: list[Finding]
    governed: int          # actions (or tools) with at least one allow/deny clause
    total: int             # actions plus tools that have no rule
    coverage_pct: float | None
    clauses: list[ClauseCoverage]
    clause_coverage_pct: float | None
    probes: int


# ----------------------------------------------------------------- term helpers (program_info JSON)
def _t(term: dict) -> tuple:
    return ("v", term["var"]) if "var" in term else ("c", term.get("const"))


def _goal_key(g: dict) -> tuple:
    if g["type"] == "cmp":
        return ("cmp", g["op"], _t(g["lhs"]), _t(g["rhs"]))
    atom = g if g["type"] == "atom" else g["atom"]
    return (g["type"], atom["pred"], tuple(_t(a) for a in atom["args"]))


def _canonical(c: dict) -> tuple:
    """The clause with variables renamed by first appearance, so equal clauses compare equal."""
    names: dict[str, str] = {}

    def ren(t: tuple) -> tuple:
        if t[0] == "v":
            return ("v", names.setdefault(t[1], f"V{len(names)}"))
        return t

    def goal(g: dict) -> tuple:
        k = _goal_key(g)
        if k[0] == "cmp":
            return ("cmp", k[1], ren(k[2]), ren(k[3]))
        return (k[0], k[1], tuple(ren(a) for a in k[2]))

    head = (c["head"]["pred"], tuple(ren(_t(a)) for a in c["head"]["args"]))
    return (c["kind"], head, tuple(goal(g) for g in c["body"]))


# ----------------------------------------------------------------- 1. contradictory bounds
_FLIP = {"<": ">", ">": "<", "<=": ">=", ">=": "<=", "==": "==", "!=": "!="}


def contradiction(c: dict) -> str | None:
    """Plain-English reason why the clause body can never hold, or None. Integer bounds and equalities only."""
    lo: dict[str, int] = {}
    hi: dict[str, int] = {}
    ne: dict[str, set] = {}
    eq: dict[str, set] = {}
    for g in c["body"]:
        if g["type"] != "cmp":
            continue
        a, b, op = g["lhs"], g["rhs"], g["op"]
        if "var" in a and "const" in b:
            v, k = a["var"], b["const"]
        elif "const" in a and "var" in b:
            v, k, op = b["var"], a["const"], _FLIP[op]
        else:
            continue
        if op == "==":
            eq.setdefault(v, set()).add(k)
        elif op == "!=":
            ne.setdefault(v, set()).add(k)
        elif isinstance(k, int) and not isinstance(k, bool):
            if op == ">":
                lo[v] = max(lo.get(v, k + 1), k + 1)
            elif op == ">=":
                lo[v] = max(lo.get(v, k), k)
            elif op == "<":
                hi[v] = min(hi.get(v, k - 1), k - 1)
            elif op == "<=":
                hi[v] = min(hi.get(v, k), k)
    for v, vals in eq.items():
        if len(vals) > 1:
            return f"{v} would have to equal {' and '.join(str(x) for x in sorted(vals, key=str))} at once"
        only = next(iter(vals))
        if only in ne.get(v, set()):
            return f"{v} would have to both equal and differ from {only}"
        if isinstance(only, int):
            if v in lo and only < lo[v]:
                return f"{v} would have to equal {only} and also be at least {lo[v]}"
            if v in hi and only > hi[v]:
                return f"{v} would have to equal {only} and also be at most {hi[v]}"
    for v in set(lo) & set(hi):
        if lo[v] > hi[v]:
            return f"{v} would have to be at least {lo[v]} and at most {hi[v]} at the same time"
        if lo[v] == hi[v] and lo[v] in ne.get(v, set()):
            return f"{v} would have to be exactly {lo[v]} and also not {lo[v]}"
    return None


# ----------------------------------------------------------------- 2. shadowed allow
def _match_term(td: tuple, ta: tuple, m: dict) -> dict | None:
    if td[0] == "c":
        return m if ta == td else None
    if td[1] in m:
        return m if m[td[1]] == ta else None
    return {**m, td[1]: ta}


def _match_goal(gd: dict, ga: dict, m: dict) -> dict | None:
    if gd["type"] != ga["type"]:
        return None
    if gd["type"] == "cmp":
        if gd["op"] != ga["op"]:
            return None
        m2 = _match_term(_t(gd["lhs"]), _t(ga["lhs"]), m)
        return None if m2 is None else _match_term(_t(gd["rhs"]), _t(ga["rhs"]), m2)
    ad = gd if gd["type"] == "atom" else gd["atom"]
    aa = ga if ga["type"] == "atom" else ga["atom"]
    if ad["pred"] != aa["pred"] or len(ad["args"]) != len(aa["args"]):
        return None
    for x, y in zip(ad["args"], aa["args"]):
        m = _match_term(_t(x), _t(y), m)
        if m is None:
            return None
    return m


def shadows(deny: dict, allow: dict) -> bool:
    """True when every request the allow clause accepts is also matched by the deny clause: the deny's head can be
    mapped onto the allow's head and each of the deny's conditions appears in the allow's body."""
    if deny["head"]["pred"] != allow["head"]["pred"] or len(deny["head"]["args"]) != len(allow["head"]["args"]):
        return False
    m: dict | None = {}
    for x, y in zip(deny["head"]["args"], allow["head"]["args"]):
        m = _match_term(_t(x), _t(y), m)
        if m is None:
            return False

    def rec(i: int, mm: dict) -> bool:
        if i == len(deny["body"]):
            return True
        for ga in allow["body"]:
            m2 = _match_goal(deny["body"][i], ga, mm)
            if m2 is not None and rec(i + 1, m2):
                return True
        return False

    return rec(0, m)


# ----------------------------------------------------------------- probes that aim at every clause
def targeted_probes(sh: Shape) -> list[tuple[str, str, str, list[str]]]:
    """Requests chosen from what the policy mentions: every action, a known actor and a stranger, the hours and
    argument values around each number it compares against."""
    resource = (sh.resources or ["item"])[0]
    hours = sorted({12, 3, 0, 23} | {h for n in sh.constants for h in (n - 1, n, n + 1) if 0 <= h <= 23}) if sh.uses_hour else []
    vals = boundary_values(sh.constants)
    out: list[tuple[str, str, str, list[str]]] = []
    for a in sh.actions:
        tool = a[4:] if a.startswith("can_") else a
        ctxs: list[list[str]] = [[]] + [[f"hour(now, {h})"] for h in hours]
        for t, p in sh.arg_keys:
            if t == tool:
                for v in vals:
                    ctxs.append([f"arg({t}, {p}, {v})"])
                    if sh.uses_hour:
                        ctxs.append([f"hour(now, 12)", f"arg({t}, {p}, {v})"])
        rows = [(sh.actors[0], a, resource, ctx) for ctx in ctxs] + [("stranger", a, resource, ctx) for ctx in ctxs[:3]]
        out.extend(rows[:PROBES_PER_ACTION])
    return out


# ----------------------------------------------------------------- the report
def _uses_context(c: dict) -> bool:
    for g in c["body"]:
        atom = g if g["type"] == "atom" else g.get("atom")
        if atom and atom["pred"] in CONTEXT_PREDS:
            return True
    return False


def analyze(adapter: EngineAdapter, source: str, *, tools: list[str] | None = None,
            scenarios: list[Scenario] | None = None, budget: Budget | None = None) -> GapReport:
    budget = budget or Budget()
    info = adapter.program_info(source)
    sh: Shape = shape(info)
    clauses = info["clauses"]
    decisions = [c for c in clauses if c["kind"] in ("allow", "deny")]
    findings: list[Finding] = []

    # tools with no rule
    covered_actions = {c["head"]["pred"] for c in decisions}
    for t in tools or []:
        if decision_name(t) not in covered_actions:
            findings.append(Finding(id="uncovered_tool", severity="warning", certainty="proved",
                                    title=f"No rule for the tool '{t}'",
                                    detail=f"Nothing mentions {decision_name(t)}, so every call to '{t}' is denied by default.",
                                    action=decision_name(t)))
    # an action that can never be allowed
    for a in sh.actions:
        kinds = {c["kind"] for c in decisions if c["head"]["pred"] == a}
        if kinds == {"deny"}:
            findings.append(Finding(id="never_allowed", severity="warning", certainty="proved",
                                    title=f"{a} can never be allowed",
                                    detail="It has deny rules but no allow rule, so it is always denied. The deny rules do nothing.",
                                    lines=[c["line"] for c in decisions if c["head"]["pred"] == a], action=a))
    # dead clauses
    for c in decisions:
        why = contradiction(c)
        if why:
            findings.append(Finding(id="dead_clause", severity="warning", certainty="proved",
                                    title=f"The {c['kind']} rule at line {c['line']} can never match",
                                    detail=f"{why}.", lines=[c["line"]], action=c["head"]["pred"]))
    # allow rules a deny always overrides
    denies = [c for c in decisions if c["kind"] == "deny"]
    for a in (c for c in decisions if c["kind"] == "allow"):
        for d in denies:
            if shadows(d, a):
                findings.append(Finding(id="shadowed_allow", severity="warning", certainty="proved",
                                        title=f"The allow rule at line {a['line']} is always overridden",
                                        detail=f"Whenever it applies, the deny rule at line {d['line']} applies too, and DENY beats ALLOW. "
                                               "The allow rule never has any effect.",
                                        lines=[a["line"], d["line"]], action=a["head"]["pred"]))
                break
    # duplicates
    seen: dict[tuple, int] = {}
    for c in clauses:
        k = _canonical(c)
        if k in seen:
            findings.append(Finding(id="duplicate_clause", severity="info", certainty="proved",
                                    title=f"Line {c['line']} repeats the rule at line {seen[k]}",
                                    detail="The two clauses mean exactly the same thing. One can be removed.",
                                    lines=[seen[k], c["line"]], action=c["head"]["pred"] if c["kind"] != "rule" else None))
        else:
            seen[k] = c["line"]
    # defined but never used
    used = {(g if g["type"] == "atom" else g["atom"])["pred"] for c in clauses for g in c["body"] if g["type"] != "cmp"}
    fact_lines: dict[str, int] = {}
    for f in info["facts"]:
        fact_lines.setdefault(f["pred"], f["line"])
    for pred, line in fact_lines.items():
        if pred not in used and pred not in CONTEXT_PREDS:
            findings.append(Finding(id="unused_fact", severity="info", certainty="heuristic",
                                    title=f"The fact '{pred}' is never used", lines=[line],
                                    detail="No rule reads it. It may be left over, or a rule that should use it is missing."))
    for c in clauses:
        if c["kind"] == "rule" and c["head"]["pred"] not in used:
            findings.append(Finding(id="unused_rule", severity="info", certainty="heuristic",
                                    title=f"The rule '{c['head']['pred']}' is never used", lines=[c["line"]],
                                    detail="No other rule or decision refers to it."))
    # a deny that needs a fact the caller might not send
    resource = (sh.resources or ["item"])[0]
    for a in sh.actions:
        needy = [c for c in decisions if c["head"]["pred"] == a and c["kind"] == "deny" and _uses_context(c)]
        if not needy:
            continue
        for actor in sh.actors[:1]:
            budget.spend()
            if safe_check(adapter, source, actor, a, resource, []).decision == "ALLOW":
                findings.append(Finding(id="fails_open", severity="warning", certainty="heuristic",
                                        title=f"{a} is allowed when the time or arguments are not supplied",
                                        detail=f"A deny rule (line {needy[0]['line']}) needs hour, day or argument facts. If the caller "
                                               "leaves them out the deny cannot fire, and the allow rule wins.",
                                        lines=[c["line"] for c in needy], action=a))

    # clause coverage from probes
    if scenarios:
        probes = [(s.actor, s.action, s.resource, s.context) for s in scenarios][:MAX_PROBES]
    else:
        probes = targeted_probes(sh)[:MAX_PROBES]
    cov: dict[int, ClauseCoverage] = {}
    for c in decisions:
        cov[c["line"]] = ClauseCoverage(line=c["line"], kind=c["kind"], head=c["head"]["pred"], matched=0, tried=0)
    for actor, action, resource, context in probes:
        budget.spend()
        try:
            w = adapter.explain(source, actor, action, resource, context)
        except EngineError:
            continue
        for cl in w.clauses:
            row = cov.get(cl.line)
            if row is None:
                continue
            if cl.status != "head_mismatch":
                row.tried += 1
            if cl.status == "matched":
                row.matched += 1
    rows = sorted(cov.values(), key=lambda r: r.line)
    for r in rows:
        if r.matched == 0:
            findings.append(Finding(id="untested_clause", severity="info", certainty="heuristic",
                                    title=f"No test makes the {r.kind} rule at line {r.line} fire",
                                    detail="None of the probes in this run matched it. Add a scenario that does, so a change to it would be noticed.",
                                    lines=[r.line], action=r.head))
    if tools:
        wanted = {decision_name(t) for t in tools}
        total, governed = len(wanted), len(wanted & covered_actions)
    else:                               # without the agent's tool list the share of tools covered is unknown, not 100%
        total = governed = len(covered_actions)
    order = {"warning": 0, "info": 1}
    findings.sort(key=lambda f: (order[f.severity], f.lines[0] if f.lines else 0))
    return GapReport(findings=findings, governed=governed, total=total,
                     coverage_pct=round(100 * governed / total, 1) if (tools and total) else None,
                     clauses=rows,
                     clause_coverage_pct=round(100 * sum(1 for r in rows if r.matched) / len(rows), 1) if rows else None,
                     probes=len(probes))
