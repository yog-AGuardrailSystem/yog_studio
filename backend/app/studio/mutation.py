"""Test Strength (mutation testing): make small breaking edits to the policy and see whether the tests notice.
A mutant that no test catches is a weak spot in the tests. Some survivors are harmless equivalents; the page says so."""
import re
from typing import Literal

from pydantic import BaseModel, Field

from app.engine.adapter import EngineAdapter
from app.studio.common import Budget, BudgetExceeded, PolicyRef, Shape, safe_check
from app.studio.gaps import targeted_probes

MAX_MUTANTS = 40
MAX_SCENARIOS = 150
MAX_SITES = 2000           # edit sites listed before the evenly spread max_mutants selection
CMP = re.compile(r"^(\s+)(\S+)\s+(>=|<=|==|!=|>|<)\s+(\S+)\s*(#.*)?$")
HEAD = re.compile(r"^(allow|deny|rule)\s")
FLIP = {">=": ">", ">": ">=", "<=": "<", "<": "<=", "==": "!=", "!=": "=="}


class TestCase(BaseModel):
    __test__ = False                    # not a pytest class
    actor: str = Field(max_length=200)
    action: str = Field(max_length=200)
    resource: str = Field(max_length=200)
    context: list[str] = Field(default_factory=list, max_length=40)
    expected: Literal["ALLOW", "DENY"]


class MutationRequest(PolicyRef):
    scenarios: list[TestCase] = Field(default_factory=list, max_length=MAX_SCENARIOS)
    max_mutants: int = Field(default=MAX_MUTANTS, ge=1, le=MAX_MUTANTS)


class Mutant(BaseModel):
    id: int
    line: int
    kind: str
    description: str
    before: str
    after: str
    status: Literal["killed", "survived", "invalid"]
    caught_by: str | None = None


class MutationReport(BaseModel):
    policy_label: str = ""
    tests_used: int
    tests_source: Literal["yours", "baseline"]
    tests_excluded: int                  # scenarios the unmodified policy already fails: they cannot judge anything
    valid: int
    killed: int
    survived: int
    invalid: int
    score: float | None                  # killed / valid, in percent
    mutants: list[Mutant]
    note: str


def _clause_end(lines: list[str], start: int) -> int:
    i = start + 1
    while i < len(lines) and (lines[i].startswith((" ", "\t")) or not lines[i].strip()):
        i += 1
    return i


def generate(source: str) -> list[tuple]:
    """(line, kind, description, before, after, build), deterministic and in source order.

    `build` is a zero-argument function that makes the mutated source text; it has a `.key` identifying the edit. The
    text is NOT built here: a policy near the size limit has thousands of edit sites and a full copy of the source for
    each one is quadratic memory, while only max_mutants of them are ever used. At most MAX_SITES sites are listed."""
    lines = source.split("\n")
    out: list[tuple] = []

    def add(i: int, kind: str, desc: str, before: str, after_lines: list[str], span: tuple[int, int]):
        if len(out) >= MAX_SITES or list(after_lines) == lines[span[0]:span[1]]:
            return

        def build(span=span, after=tuple(after_lines)) -> str:
            return "\n".join(lines[:span[0]] + list(after) + lines[span[1]:])

        build.key = (span, tuple(after_lines))          # type: ignore[attr-defined]
        out.append((i + 1, kind, desc, before.strip(), " / ".join(a.strip() for a in after_lines) or "(removed)", build))

    body_count: dict[int, int] = {}
    start = -1
    for i, ln in enumerate(lines):
        if HEAD.match(ln):
            start = i
            body_count[i] = 0
        elif ln.startswith((" ", "\t")) and ln.strip() and start >= 0:
            body_count[start] += 1
    start = -1
    for i, ln in enumerate(lines):
        if HEAD.match(ln):
            start = i
            if ln.startswith(("allow", "deny")):
                kind = "drop deny rule" if ln.startswith("deny") else "drop allow rule"
                add(i, kind, f"Remove the whole {ln.split()[0]} rule", ln, [], (i, _clause_end(lines, i)))
            continue
        if not ln.startswith((" ", "\t")) or not ln.strip():
            continue
        m = CMP.match(ln)
        if m:
            ind, lhs, op, rhs, cm = m.groups()
            tail = f" {cm}" if cm else ""
            add(i, "flip comparison", f"Change '{op}' to '{FLIP[op]}'", ln, [f"{ind}{lhs} {FLIP[op]} {rhs}{tail}"], (i, i + 1))
            for side, other in ((rhs, "r"), (lhs, "l")):
                if re.fullmatch(r"\d+", side):
                    for d in (1, -1):
                        n = int(side) + d
                        if n < 0:
                            continue
                        new = f"{ind}{lhs} {op} {n}{tail}" if other == "r" else f"{ind}{n} {op} {rhs}{tail}"
                        add(i, "shift number", f"Change {side} to {n}", ln, [new], (i, i + 1))
        elif ln.strip().startswith("not "):
            add(i, "remove not", "Remove the 'not'", ln, [ln.replace("not ", "", 1)], (i, i + 1))
        if start >= 0 and body_count.get(start, 0) > 1:
            add(i, "drop condition", "Remove this condition", ln, [], (i, i + 1))
    return out


def run(adapter: EngineAdapter, source: str, sh: Shape, tests: list[TestCase], max_mutants: int, budget: Budget) -> MutationReport:
    baseline = False
    if not tests:
        baseline = True
        probes = targeted_probes(sh)[:MAX_SCENARIOS]
        tests = [TestCase(actor=a, action=act, resource=r, context=c,
                          expected=safe_check(adapter, source, a, act, r, c).decision) for a, act, r, c in probes]
    # tests the original policy already fails cannot tell us anything about a change
    usable: list[TestCase] = []
    for t in tests:
        budget.spend()
        if safe_check(adapter, source, t.actor, t.action, t.resource, t.context).decision == t.expected:
            usable.append(t)
    excluded = len(tests) - len(usable)

    seen: set = set()
    cand = []
    for item in generate(source):
        if item[5].key not in seen:
            seen.add(item[5].key)
            cand.append(item)
    if len(cand) > max_mutants:                      # spread the cap evenly over the file instead of taking the first few
        step = len(cand) / max_mutants
        cand = [cand[int(k * step)] for k in range(max_mutants)]

    mutants: list[Mutant] = []
    try:
        for n, (line, kind, desc, before, after, build) in enumerate(cand, 1):
            msrc = build()                           # only the chosen edits are ever turned into text
            if adapter.validate(msrc):
                mutants.append(Mutant(id=n, line=line, kind=kind, description=desc, before=before, after=after, status="invalid"))
                continue
            caught = None
            for t in usable:
                budget.spend()
                if safe_check(adapter, msrc, t.actor, t.action, t.resource, t.context).decision != t.expected:
                    caught = f"{t.action}({t.actor}, {t.resource}) {' '.join(t.context)}".strip()
                    break
            mutants.append(Mutant(id=n, line=line, kind=kind, description=desc, before=before, after=after,
                                  status="killed" if caught else "survived", caught_by=caught))
    except BudgetExceeded:
        pass
    killed = sum(1 for m in mutants if m.status == "killed")
    survived = sum(1 for m in mutants if m.status == "survived")
    valid = killed + survived
    note = ("The tests here are probes generated from the policy itself, so this measures how sensitive those probes are. "
            "Bring your own scenarios for a score about your intent. " if baseline else
            "The score says how many small breaking changes your scenarios notice. ") + \
        "A surviving change is a place no test looks, though some survivors change nothing in practice."
    return MutationReport(tests_used=len(usable), tests_source="baseline" if baseline else "yours", tests_excluded=excluded,
                          valid=valid, killed=killed, survived=survived, invalid=len(mutants) - valid,
                          score=round(100 * killed / valid, 1) if valid else None, mutants=mutants, note=note)
