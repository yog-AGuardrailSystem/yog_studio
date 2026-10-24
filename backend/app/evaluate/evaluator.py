"""Runs scenarios through the engine and builds the red/green report."""
from pydantic import BaseModel

from app.core.models import Tool
from app.engine.adapter import EngineAdapter, EngineError
from app.evaluate.scenarios import Scenario, ScenarioResult, characterization, generate_independent
from app.llm.provider import LLMProvider
from app.translate.translator import decision_name


class Summary(BaseModel):
    independent_total: int
    independent_passed: int
    pass_pct: float | None          # None when there is nothing independent to grade against
    unconfirmed: int                # characterization rows: shown, but never counted as passes
    errors: int
    all_green: bool


class Report(BaseModel):
    results: list[ScenarioResult]
    summary: Summary
    warnings: list[str]


def run_scenario(adapter: EngineAdapter, policy: str, s: Scenario) -> ScenarioResult:
    base = s.model_dump()
    try:
        r = adapter.check(policy, s.actor, s.action, s.resource, s.context)
    except EngineError as e:                                  # bad context in ONE row must not sink the run
        return ScenarioResult(**base, actual=None, reason="", passed=False, error=str(e))
    passed = True if s.unconfirmed else r.decision == s.expected
    return ScenarioResult(**base, actual=r.decision, reason=r.reason, trace=r.trace, passed=passed)


def summarise(results: list[ScenarioResult]) -> Summary:
    indep = [r for r in results if not r.unconfirmed]
    ok = sum(1 for r in indep if r.passed)
    errors = sum(1 for r in results if r.error)
    return Summary(independent_total=len(indep), independent_passed=ok,
                   pass_pct=round(100 * ok / len(indep), 1) if indep else None,
                   unconfirmed=sum(1 for r in results if r.unconfirmed), errors=errors,
                   all_green=bool(indep) and ok == len(indep) and errors == 0)


def evaluate(adapter: EngineAdapter, policy: str, *, rules: list[str] | None = None, tools: list[Tool] | None = None,
             user_scenarios: list[Scenario] | None = None, provider: LLMProvider | None = None) -> Report:
    """Raises EngineError if the policy does not compile."""
    warnings: list[str] = []
    scenarios: list[Scenario] = [s.model_copy(update={"source": "user", "unconfirmed": False})
                                 for s in (user_scenarios or [])]
    if provider is not None and rules:
        gen, problems = generate_independent([r for r in rules if r.strip()], tools or [], provider)
        scenarios += gen
        warnings += problems
    chars, cw = characterization(adapter, policy)
    scenarios += chars
    warnings += cw

    info = adapter.program_info(policy)
    covered = {c["head"]["pred"] for c in info["clauses"] if c["kind"] in ("allow", "deny")}
    for t in tools or []:
        if decision_name(t.name) not in covered:
            warnings.append(f"tool '{t.name}' is not covered by any rule: every call to it is denied by default.")

    results = [run_scenario(adapter, policy, s) for s in scenarios]
    summary = summarise(results)
    if summary.independent_total == 0:
        warnings.append("No independent scenarios: nothing here checks the policy against what you meant. "
                        "Add your own scenarios or enable an LLM provider.")
    return Report(results=results, summary=summary, warnings=warnings)
