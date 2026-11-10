"""Optional LLM reranker: reads the top candidates and scores how useful each is for the new rule.

Only used with a real LLM (the offline provider cannot judge anything) and only when the user switches it on.
Any failure (call error, unparseable reply) leaves the original order untouched: reranking can only ever help."""
import json
import re

from app.llm.provider import LLMError, LLMProvider, generate_text, load_prompt
from app.rag.retriever import Retrieved

RELEVANT_AT = 5.0          # a reranker score at or above this counts as relevant
SCHEMA = {"type": "array", "items": {"type": "object", "properties": {
    "id": {"type": "string"}, "score": {"type": "number"}}, "required": ["id", "score"]}}


def _render(template: str, **values: str) -> str:
    for k, v in values.items():
        template = template.replace("{{" + k + "}}", v)
    return template


def parse_scores(text: str, ids: set[str]) -> dict[str, float]:
    """Pull {id: score} out of the reply, ignoring unknown ids and clamping to 0..10. Empty dict if unusable."""
    m = re.search(r"\[.*\]", text, re.S)
    if not m:
        return {}
    try:
        data = json.loads(m.group(0))
    except ValueError:
        return {}
    out: dict[str, float] = {}
    for item in data if isinstance(data, list) else []:
        if isinstance(item, dict) and item.get("id") in ids and isinstance(item.get("score"), (int, float)) \
                and not isinstance(item.get("score"), bool):
            out[item["id"]] = max(0.0, min(10.0, float(item["score"])))
    return out


def rerank(provider: LLMProvider, rules: list[str], candidates: list[Retrieved], top: int = 3) -> tuple[list[Retrieved], str | None]:
    """Returns (best `top` candidates ordered by usefulness, problem). `problem` is None on success; on failure the
    candidates come back unchanged (in their original order, cut to `top`) with a short reason."""
    if len(candidates) < 2:
        return candidates[:top], None
    listing = "\n".join(f"- id: {c.id}\n  rule: {c.english}\n  tools: {', '.join(t.split('(')[0] for t in c.tools_context) or '(none)'}"
                        for c in candidates)
    prompt = _render(load_prompt("rerank"), rules="\n".join(f"{i}. {r}" for i, r in enumerate(rules, 1)), candidates=listing)
    try:
        reply = generate_text(provider, prompt, json_schema=SCHEMA)
    except LLMError as e:
        return candidates[:top], f"reranker call failed: {e}"
    scores = parse_scores(reply, {c.id for c in candidates})
    if len(scores) < len(candidates) // 2 + 1:                     # too little to trust: keep the retrieval order
        return candidates[:top], "reranker reply could not be used"
    ranked = []
    for c in candidates:
        s = scores.get(c.id)
        ranked.append(c.model_copy(update={"rerank": s, "relevant": c.relevant if s is None else s >= RELEVANT_AT}))
    ranked.sort(key=lambda c: (-(c.rerank if c.rerank is not None else -1.0), -c.fused))
    return ranked[:top], None
