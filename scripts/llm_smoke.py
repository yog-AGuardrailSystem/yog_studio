#!/usr/bin/env python3
"""Run this ONCE after putting your keys in backend/.env. It makes a handful of tiny real API calls and prints
PASS/FAIL for each capability Studio relies on, so you know the real providers work before running a benchmark.

    cd backend
    uv run python ../scripts/llm_smoke.py            # whatever LLM_PROVIDER / EMBED_PROVIDER select
    uv run python ../scripts/llm_smoke.py gemini     # force one provider
    uv run python ../scripts/llm_smoke.py claude

Cost: a few cents at most. It never prints a key.
"""
import json
import os
import sys
import time

sys.path.insert(0, os.getcwd())

from app.llm.factory import get_provider  # noqa: E402
from app.llm.provider import LLMError  # noqa: E402

results: list[tuple[str, bool, str]] = []


def step(name: str, fn) -> None:
    t0 = time.time()
    try:
        detail = fn()
        results.append((name, True, f"{detail}  ({time.time() - t0:.1f}s)"))
    except Exception as e:                                           # noqa: BLE001 - report every failure, never crash
        results.append((name, False, f"{type(e).__name__}: {e}"))


def main() -> int:
    if len(sys.argv) > 1:
        os.environ["LLM_PROVIDER"] = sys.argv[1]
    p = get_provider()
    print(f"provider={p.name} model={p.model} embed_model={p.embed_model}\n")

    def plain():
        out = p.generate("Reply with exactly the single word: pong")
        assert out.strip(), "empty reply"
        return f"replied {out.strip()[:40]!r}"

    def schema():
        s = {"type": "object", "properties": {"scenarios": {"type": "array", "items": {
            "type": "object", "properties": {"n": {"type": "integer"}}, "required": ["n"]}}}, "required": ["scenarios"]}
        out = p.generate('Return {"scenarios": [{"n": 1}, {"n": 2}]}', json_schema=s) if p.supports_json_schema \
            else p.generate('Return JSON only: {"scenarios": [{"n": 1}, {"n": 2}]}')
        data = json.loads(out[out.find("{"):out.rfind("}") + 1])
        assert len(data["scenarios"]) == 2, data
        return "valid JSON object with 2 scenarios"

    def embed_doc_query():
        d = p.embed(["Only admins may delete from a database."], task="document") if p.supports_embed_task \
            else p.embed(["Only admins may delete from a database."])
        q = p.embed(["who can remove rows"], task="query") if p.supports_embed_task else p.embed(["who can remove rows"])
        assert len(d[0]) == len(q[0]) > 100, (len(d[0]), len(q[0]))
        return f"{len(d[0])}-dimensional vectors"

    def translate_one():
        from app.api.deps import get_adapter
        from app.api.retrieve import get_retriever
        from app.core.models import Tool
        from app.translate.translator import translate
        d = translate(["The agent may never unlock the door between 11pm and 6am."],
                      [Tool(name="unlock_door", source_line=1)], p, get_retriever(), get_adapter(), verify=True)
        assert d.valid, d.errors
        return f"valid={d.valid} verified={d.verified} attempts={d.attempts} retrieved={[r.id for r in d.retrieved]}"

    step("plain generation", plain)
    step("structured JSON output", schema)
    step("embeddings (document + query)", embed_doc_query)
    step("end to end: English -> checked YOG", translate_one)

    width = max(len(n) for n, _, _ in results)
    for name, ok, detail in results:
        print(f"{'PASS' if ok else 'FAIL'}  {name:<{width}}  {detail}")
    print("\nusage:", json.dumps(p.usage.snapshot()))
    return 0 if all(ok for _, ok, _ in results) else 1


if __name__ == "__main__":
    try:
        sys.exit(main())
    except LLMError as e:
        print(f"FAIL  could not even build the provider: {e}")
        sys.exit(1)
