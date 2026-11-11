"""Safety Scorecard: a handful of numbers about one policy, each from a tool in this package. A number that has not been
measured says "not measured" and never a made-up value."""
from typing import Literal

from pydantic import BaseModel

from app.engine.adapter import EngineAdapter
from app.evaluate.evaluator import evaluate
from app.studio import gaps as gaps_mod
from app.studio import mutation, redteam
from app.studio.common import Budget, shape


class Metric(BaseModel):
    id: str
    label: str
    value: str | None
    detail: str
    status: Literal["good", "warn", "bad", "todo"]
    link: str


class Scorecard(BaseModel):
    policy_label: str = ""
    headline: str
    metrics: list[Metric]


def compute(adapter: EngineAdapter, source: str, tools: list[str] | None = None, include_strength: bool = True) -> Scorecard:
    sh = shape(adapter.program_info(source))
    g = gaps_mod.analyze(adapter, source, tools=tools or None, budget=Budget(6000))
    m: list[Metric] = []

    if g.coverage_pct is None:
        m.append(Metric(id="tools", label="Tools covered", value=None, status="todo", link="/studio/gaps",
                        detail="Upload an agent so Studio knows which tools exist, then each is checked for a rule."))
    else:
        m.append(Metric(id="tools", label="Tools covered", value=f"{g.governed} of {g.total}", link="/studio/gaps",
                        status="good" if g.governed == g.total else "bad",
                        detail="Every tool has a rule." if g.governed == g.total else "Tools without a rule are denied by default."))

    ev = evaluate(adapter, source)
    s = ev.summary
    if s.independent_total == 0:
        m.append(Metric(id="scenarios", label="Scenario tests", value=None, status="todo", link="/review",
                        detail=f"{s.unconfirmed} generated probes ran, but none is a scenario written from your intent yet."))
    else:
        m.append(Metric(id="scenarios", label="Scenario tests", value=f"{s.independent_passed} of {s.independent_total} pass",
                        status="good" if s.all_green else "bad", link="/review", detail="Scenarios written from the English rules."))

    if g.clause_coverage_pct is None:
        m.append(Metric(id="clauses", label="Rules exercised", value=None, status="todo", link="/studio/gaps", detail="No allow or deny rules."))
    else:
        m.append(Metric(id="clauses", label="Rules exercised", value=f"{g.clause_coverage_pct:g}%", link="/studio/gaps",
                        status="good" if g.clause_coverage_pct == 100 else "warn",
                        detail="Share of allow/deny rules that at least one probe makes fire."))

    proved = [f for f in g.findings if f.certainty == "proved" and f.severity == "warning" and f.id != "uncovered_tool"]
    m.append(Metric(id="gaps", label="Proved problems", value=str(len(proved)), link="/studio/gaps",
                    status="good" if not proved else "bad",
                    detail="Dead rules, shadowed allows and actions that can never be allowed." if proved else "None found by the static checks."))

    rt = redteam.run(adapter, source, sh, [], Budget())
    m.append(Metric(id="redteam", label="Suspicious ALLOWs", value=str(rt.suspicious), link="/studio/red-team",
                    status="good" if rt.suspicious == 0 else "warn",
                    detail="Edge cases that were allowed and look unexpected. State invariants on the Red-Team page to confirm or clear them."))

    if include_strength:
        mt = mutation.run(adapter, source, sh, [], 30, Budget(6000))
        if mt.score is None:
            m.append(Metric(id="strength", label="Test strength", value=None, status="todo", link="/studio/strength", detail="No valid changes could be made."))
        else:
            m.append(Metric(id="strength", label="Test strength", value=f"{mt.score:g}%", link="/studio/strength",
                            status="good" if mt.score >= 90 else "warn" if mt.score >= 60 else "bad",
                            detail=f"{mt.killed} of {mt.valid} small breaking changes were noticed."))
    else:
        m.append(Metric(id="strength", label="Test strength", value=None, status="todo", link="/studio/strength", detail="Not measured."))

    good = sum(1 for x in m if x.status == "good")
    measured = sum(1 for x in m if x.status != "todo")
    return Scorecard(headline=f"{good} of {measured} measured checks look good" + (f"; {len(m) - measured} not measured yet" if measured < len(m) else ""),
                     metrics=m)
