"""English rules -> YOG draft. LLM drafts, the engine verifies (max 3 attempts), a human approves later."""
import re
from collections.abc import Callable

from app.core.models import AttemptLog, PolicyDraft, RetrievedExample, ScenarioSummary, Tool
from app.engine.adapter import EngineAdapter, EngineError
from app.llm.provider import LLMError, LLMProvider, generate_text, load_prompt
from app.rag.retriever import Retrieved, Retriever

MAX_ATTEMPTS = 3
RERANK_POOL = 8           # candidates handed to the optional LLM reranker
FENCE = re.compile(r"```[ \t]*(?:yog)?[ \t]*\n(.*?)```", re.S | re.I)


CITE = re.compile(r"^[ \t]*USED_EXAMPLES[ \t]*:[ \t]*(.*)$", re.M | re.I)


def extract_yog(text: str) -> str:
    """Pull the policy out of the model reply: first fenced block, else the whole reply (minus the citation line)."""
    m = FENCE.search(text)
    body = m.group(1) if m else CITE.sub("", text)
    return body.strip("\n") + "\n" if body.strip() else ""


def parse_citations(reply: str, allowed: set[str]) -> tuple[list[str], list[str], bool]:
    """(valid ids, problems, said_none). An id the model cites that was never in the prompt is a problem, not a source."""
    m = CITE.search(reply)
    if not m:
        return [], (["the model did not say which examples it used"] if allowed else []), False
    raw = [x.strip(" `'\"[]()") for x in re.split(r"[,\s]+", m.group(1))]
    ids = [x for x in raw if x and x.lower() not in ("none", "n/a", "-", "null")]
    valid = list(dict.fromkeys(i for i in ids if i in allowed))
    problems = [f"cited '{i}', which was not among the retrieved examples" for i in dict.fromkeys(ids) if i not in allowed]
    return valid, problems, not ids


def decision_name(tool_name: str) -> str:
    return "can_" + re.sub(r"\W+", "_", tool_name).strip("_").lower()


def format_tools(tools: list[Tool]) -> str:
    if not tools:
        return "(no tools given: name decision predicates can_<action>)"
    lines = []
    for t in tools:
        params = ", ".join(p.name + (f": {p.type_hint}" if p.type_hint else "") for p in t.params)
        hints = f"  # side effects: {', '.join(t.side_effect_hints)}" if t.side_effect_hints else ""
        doc = f"  # {t.docstring.splitlines()[0]}" if t.docstring else ""
        lines.append(f"- {t.name}({params}) [{decision_name(t.name)}]{hints}{doc}")
    return "\n".join(lines)


def format_examples(examples: list[Retrieved]) -> str:
    if not examples:
        return ("(none: no stored example is close enough to these rules to learn from. Write the policy from the rules, "
                "the tools and the language reference alone, and finish with USED_EXAMPLES: none)")
    return "\n\n".join(f"Example [{e.id}]\nRule: {e.english}\n```yog\n{e.gold_yog.rstrip()}\n```" for e in examples)


def format_rules(rules: list[str]) -> str:
    return "\n".join(f"{i}. {r}" for i, r in enumerate(rules, 1))


def render(template: str, **values: str) -> str:
    for k, v in values.items():
        template = template.replace("{{" + k + "}}", v)
    return template


def lint(adapter: EngineAdapter, policy: str, tools: list[Tool]) -> list[str]:
    """Compiler errors plus Studio-specific checks the engine itself does not make."""
    if not policy.strip():
        return ["the reply contained no YOG policy"]
    errors = adapter.validate(policy)
    if errors:
        return errors
    try:
        info = adapter.program_info(policy)
    except EngineError as e:
        return [str(e)]
    decisions = [c for c in info["clauses"] if c["kind"] in ("allow", "deny")]
    if not decisions:
        return ["the policy has no allow or deny clause, so it decides nothing"]
    allowed = {decision_name(t.name) for t in tools}
    for c in decisions:
        head = c["head"]
        if len(head["args"]) != 2:
            errors.append(f"line {c['line']}: decision {head['pred']} must take exactly 2 arguments (Actor, Resource)")
        elif allowed and head["pred"] not in allowed:
            errors.append(f"line {c['line']}: {head['pred']} does not match any tool; use one of: {', '.join(sorted(allowed))}")
    return sorted(set(errors))


class TranslateCancelled(Exception):
    """The caller asked to stop; raised between steps (an LLM call already in flight finishes first)."""


MAX_FEEDBACK = 8          # at most this many independent-check disagreements are fed back to the model


def check_against_scenarios(adapter: EngineAdapter, policy: str, scenarios) -> tuple[int, int, list[str]]:
    """Run the independent scenarios. Returns (counted, passed, plain-English disagreements).

    A scenario that cannot even run (bad context syntax from the oracle model) is noise in the oracle, not a
    fault in the policy, so it is skipped rather than counted against the draft."""
    from app.evaluate.evaluator import run_scenario            # lazy: evaluate imports this module
    counted = passed = 0
    failures: list[str] = []
    for s in scenarios:
        r = run_scenario(adapter, policy, s)
        if r.error:
            continue
        counted += 1
        if r.passed:
            passed += 1
            continue
        ctx = f" with {', '.join(s.context)}" if s.context else ""
        note = f" ({s.note})" if s.note else ""
        failures.append(f"{s.action}({s.actor}, {s.resource}){ctx}: expected {s.expected} but the policy gives {r.actual}{note}")
    return counted, passed, failures


def translate(rules: list[str], tools: list[Tool], provider: LLMProvider, retriever: Retriever,
              adapter: EngineAdapter, max_attempts: int = MAX_ATTEMPTS, *, verify: bool = False,
              rerank: bool = False,
              on_event: Callable[[dict], None] | None = None,
              should_cancel: Callable[[], bool] | None = None) -> PolicyDraft:
    """Draft a policy. `verify=True` adds the semantic check: independent scenarios (written from the English only)
    are run against each compiling draft and any disagreement is fed back for a repair attempt. The draft is still
    only a draft: a human approves it later, and `verified` is shown, never used to approve anything."""
    def emit(**event) -> None:
        if on_event:
            on_event(event)

    def stop_if_cancelled() -> None:
        if should_cancel and should_cancel():
            raise TranslateCancelled()

    rules = [r.strip() for r in rules if r.strip()]
    if not rules:
        return PolicyDraft(english_rules=[], yog_source="", retrieved_examples=[], attempts=0, valid=False,
                           errors=["no rules given"])

    names = [t.name for t in tools]
    seen: dict[str, Retrieved] = {}
    emit(phase="retrieving")
    stop_if_cancelled()
    use_rerank = rerank and provider.name != "fake"         # the offline provider cannot judge relevance
    try:
        for r in rules:
            for e in retriever.search(r, names, RERANK_POOL if use_rerank else 3):
                if e.id not in seen or e.fused > seen[e.id].fused or (e.fused == seen[e.id].fused and e.score > seen[e.id].score):
                    seen[e.id] = e
    except LLMError as e:
        emit(phase="done", valid=False, error=f"retrieval failed: {e}")
        return PolicyDraft(english_rules=rules, yog_source="", retrieved_examples=[], attempts=0, valid=False,
                           errors=[f"retrieval failed: {e}"])
    candidates = sorted(seen.values(), key=lambda e: (-e.fused, -e.score))
    reranked = False
    if use_rerank:
        stop_if_cancelled()
        emit(phase="reranking", candidates=len(candidates))
        from app.rag.rerank import rerank as llm_rerank          # lazy: keeps the offline path import-light
        candidates, problem = llm_rerank(provider, rules, candidates, top=5)
        reranked = problem is None
        emit(phase="reranked", ok=reranked, problem=problem)
    examples = candidates[:5]
    floor_info = retriever.floor_info() if hasattr(retriever, "floor_info") else {}
    relevant = [e for e in examples if e.relevant]
    grounded = bool(relevant)                               # strict: weak matches are shown, never fed to the model
    example_ids = [e.id for e in examples]
    shown = [RetrievedExample(id=e.id, english=e.english, score=e.score, source=e.source, relevant=e.relevant,
                              lexical=e.lexical, rerank=e.rerank) for e in examples]
    emit(phase="retrieved", examples=[x.model_dump() for x in shown], grounded=grounded,
         floor=floor_info.get("floor"), calibrated=floor_info.get("calibrated"), reranked=reranked)

    scenarios: list = []
    scenario_note: list[str] = []
    if verify:
        stop_if_cancelled()
        emit(phase="scenarios", state="generating")
        from app.evaluate.scenarios import generate_independent   # lazy: evaluate imports this module
        scenarios, scenario_note = generate_independent(rules, tools, provider)
        emit(phase="scenarios", state="ready", count=len(scenarios), problems=scenario_note)

    cites: dict[int, tuple[list[str], list[str]]] = {}      # attempt -> (cited ids, citation problems)

    def draft(**kw) -> PolicyDraft:
        base = dict(english_rules=rules, retrieved_examples=example_ids, retrieved=shown, attempt_log=log,
                    grounded=grounded, floor=floor_info.get("floor"), floor_calibrated=floor_info.get("calibrated"),
                    reranked=reranked)
        n = kw.get("attempts", 0)
        if n in cites:
            base["cited_examples"], base["citation_problems"] = cites[n]
        return PolicyDraft(**{**base, **kw})

    tools_txt, rules_txt = format_tools(tools), format_rules(rules)
    prompt = render(load_prompt("translate"), tools=tools_txt, examples=format_examples(relevant), rules=rules_txt)
    log: list[AttemptLog] = []
    best: tuple[int, str, int, int] | None = None          # (disagreements, policy, attempt, checked_total) among compiling drafts
    policy, errors, attempts = "", [], 0
    for attempts in range(1, max_attempts + 1):
        stop_if_cancelled()
        emit(phase="attempt", n=attempts, state="generating")
        try:
            reply = generate_text(provider, prompt)
        except LLMError as e:
            msg = f"LLM call failed: {e}"
            log.append(AttemptLog(n=attempts, compiled=False, errors=[msg], yog_source=policy))
            emit(phase="attempt", n=attempts, state="checked", compiled=False, errors=[msg], scenario_failures=[])
            emit(phase="done", valid=False, error=msg)
            return draft(yog_source=policy, attempts=attempts, valid=False, errors=[msg])
        policy = extract_yog(reply)
        cited, problems, _ = parse_citations(reply, {e.id for e in relevant})
        if attempts > 1 and not cited and not problems:     # a repair round does not see the examples: keep what attempt 1 cited
            cited, problems = cites.get(attempts - 1, ([], []))
        cites[attempts] = (cited, problems)
        errors = lint(adapter, policy, tools)
        failures: list[str] = []
        counted = passed = 0
        if not errors and scenarios:
            counted, passed, failures = check_against_scenarios(adapter, policy, scenarios)
        log.append(AttemptLog(n=attempts, compiled=not errors, errors=errors, scenario_failures=failures,
                              yog_source=policy))
        emit(phase="attempt", n=attempts, state="checked", compiled=not errors, errors=errors,
             scenario_failures=failures)
        if not errors:
            if best is None or len(failures) < best[0]:
                best = (len(failures), policy, attempts, counted)
            if not failures:
                # verified only means something if at least one independent check really ran
                verified = True if counted else None
                summary = ScenarioSummary(total=counted, passed=passed) if counted else None
                emit(phase="done", valid=True, verified=verified)
                return draft(yog_source=policy, attempts=attempts, valid=True, errors=[], verified=verified,
                             scenario_summary=summary)
            feedback = [f"check: {f}" for f in failures[:MAX_FEEDBACK]]
        else:
            feedback = errors
        prompt = render(load_prompt("repair"), rules=rules_txt, tools=tools_txt, previous=policy.rstrip(),
                        errors="\n".join(f"- {e}" for e in feedback))

    if best is not None:                                   # compiled at least once, but the independent check disagrees
        n_fail, best_policy, best_attempt, counted = best
        _, _, best_failures = check_against_scenarios(adapter, best_policy, scenarios)
        summary = ScenarioSummary(total=counted, passed=counted - n_fail, failures=best_failures)
        emit(phase="done", valid=True, verified=False)
        return draft(yog_source=best_policy, attempts=attempts, valid=True, errors=[], verified=False,
                     scenario_summary=summary)
    emit(phase="done", valid=False, error="; ".join(errors))
    return draft(yog_source=policy, attempts=attempts, valid=False, errors=errors)
