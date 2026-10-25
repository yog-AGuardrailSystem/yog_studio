"""English rules -> YOG draft. LLM drafts, the engine verifies (max 3 attempts), a human approves later."""
import re

from app.core.models import PolicyDraft, Tool
from app.engine.adapter import EngineAdapter, EngineError
from app.llm.provider import LLMError, LLMProvider, load_prompt
from app.rag.retriever import Retrieved, Retriever

MAX_ATTEMPTS = 3
FENCE = re.compile(r"```[ \t]*(?:yog)?[ \t]*\n(.*?)```", re.S | re.I)


def extract_yog(text: str) -> str:
    """Pull the policy out of the model reply: first fenced block, else the whole reply."""
    m = FENCE.search(text)
    body = m.group(1) if m else text
    return body.strip("\n") + "\n" if body.strip() else ""


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
        return "(none)"
    return "\n\n".join(f"Rule: {e.english}\n```yog\n{e.gold_yog.rstrip()}\n```" for e in examples)


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


def translate(rules: list[str], tools: list[Tool], provider: LLMProvider, retriever: Retriever,
              adapter: EngineAdapter, max_attempts: int = MAX_ATTEMPTS) -> PolicyDraft:
    rules = [r.strip() for r in rules if r.strip()]
    if not rules:
        return PolicyDraft(english_rules=[], yog_source="", retrieved_examples=[], attempts=0, valid=False,
                           errors=["no rules given"])

    names = [t.name for t in tools]
    seen: dict[str, Retrieved] = {}
    try:
        for r in rules:
            for e in retriever.search(r, names, 3):
                if e.id not in seen or e.score > seen[e.id].score:
                    seen[e.id] = e
    except LLMError as e:
        return PolicyDraft(english_rules=rules, yog_source="", retrieved_examples=[], attempts=0, valid=False,
                           errors=[f"retrieval failed: {e}"])
    examples = sorted(seen.values(), key=lambda e: -e.score)[:5]
    example_ids = [e.id for e in examples]

    tools_txt, rules_txt = format_tools(tools), format_rules(rules)
    prompt = render(load_prompt("translate"), tools=tools_txt, examples=format_examples(examples), rules=rules_txt)
    policy, errors = "", []
    attempts = 0
    for attempts in range(1, max_attempts + 1):
        try:
            reply = provider.generate(prompt)
        except LLMError as e:
            return PolicyDraft(english_rules=rules, yog_source=policy, retrieved_examples=example_ids,
                               attempts=attempts, valid=False, errors=[f"LLM call failed: {e}"])
        policy = extract_yog(reply)
        errors = lint(adapter, policy, tools)
        if not errors:
            return PolicyDraft(english_rules=rules, yog_source=policy, retrieved_examples=example_ids,
                               attempts=attempts, valid=True, errors=[])
        prompt = render(load_prompt("repair"), rules=rules_txt, tools=tools_txt, previous=policy.rstrip(),
                        errors="\n".join(f"- {e}" for e in errors))
    return PolicyDraft(english_rules=rules, yog_source=policy, retrieved_examples=example_ids,
                       attempts=attempts, valid=False, errors=errors)
