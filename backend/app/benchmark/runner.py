"""Benchmark: English rule -> generated YOG -> compared with the gold policy (CLAUDE.md section 11).

Semantic correctness = same ALLOW/DENY as the gold policy on EVERY scenario (not string equality).
Run:  cd backend && uv run python -m app.benchmark.runner [--limit N]
"""
import argparse
import json
import re
import sys
import tempfile
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import yaml

from app.core.config import REPO_ROOT
from app.core.models import Param, Tool
from app.engine.adapter import EngineAdapter, EngineError
from app.llm.fake import FakeProvider
from app.llm.provider import LLMProvider
from app.rag.examples import PolicyExample, load_examples
from app.rag.retriever import Retriever, example_text
from app.translate.translator import lint, translate

BENCH_FILE = REPO_ROOT / "benchmark" / "rules.yaml"
RESULTS_DIR = REPO_ROOT / "benchmark" / "results"
LEAK_THRESHOLD = 0.9


def load_benchmark(path: Path = BENCH_FILE) -> list[PolicyExample]:
    return [PolicyExample(**x) for x in yaml.safe_load(path.read_text(encoding="utf-8"))]


def tools_from_context(ctx: list[str]) -> list[Tool]:
    out = []
    for t in ctx:
        m = re.match(r"\s*(\w+)\s*\((.*)\)\s*$", t)
        name, params = (m.group(1), [p.strip() for p in m.group(2).split(",") if p.strip()]) if m else (t.strip(), [])
        out.append(Tool(name=name, params=[Param(name=p) for p in params], source_line=1))
    return out


def leakage(provider: LLMProvider, bench: list[PolicyExample], examples: list[PolicyExample]) -> list[tuple[str, str, float]]:
    """(benchmark id, nearest retrieval example id, cosine) for every benchmark rule."""
    b = np.array(provider.embed([e.english for e in bench]), dtype=np.float32)
    r = np.array(provider.embed([example_text(e) for e in examples]), dtype=np.float32)
    b /= np.maximum(np.linalg.norm(b, axis=1, keepdims=True), 1e-9)
    r /= np.maximum(np.linalg.norm(r, axis=1, keepdims=True), 1e-9)
    sims = b @ r.T
    return [(bench[i].id, examples[int(sims[i].argmax())].id, float(sims[i].max())) for i in range(len(bench))]


def categorize(adapter: EngineAdapter, policy: str, tools: list[Tool], errors: list[str], semantic: bool) -> str | None:
    if semantic:
        return None
    if any("LLM call failed" in e or "retrieval failed" in e for e in errors):
        return "llm_error"
    if any("no YOG policy" in e for e in errors):
        return "no_output"
    if adapter.validate(policy):
        e = adapter.validate(policy)[0]
        return "undefined_predicate" if "not defined" in e else "unbound_variable" if "unbound" in e or "never bound" in e else "syntax"
    if lint(adapter, policy, tools):
        return "wrong_tool_name"
    return "wrong_decision"


def semantic_match(adapter: EngineAdapter, gold: PolicyExample, policy: str) -> bool:
    for s in gold.scenarios:
        want = adapter.check(gold.gold_yog, s.actor, s.action, s.resource, s.context).decision
        try:
            got = adapter.check(policy, s.actor, s.action, s.resource, s.context).decision
        except EngineError:
            return False
        if got != want:
            return False
    return True


def run_config(adapter, provider, retriever, bench, max_attempts: int) -> dict:
    rows, cats = [], {}
    for ex in bench:
        tools = tools_from_context(ex.tools_context)
        d = translate([ex.english], tools, provider, retriever, adapter, max_attempts=max_attempts)
        syntax_ok = bool(d.yog_source.strip()) and not adapter.validate(d.yog_source)
        sem = syntax_ok and not lint(adapter, d.yog_source, tools) and semantic_match(adapter, ex, d.yog_source)
        cat = categorize(adapter, d.yog_source, tools, d.errors, sem)
        if cat:
            cats[cat] = cats.get(cat, 0) + 1
        rows.append({"id": ex.id, "attempts": d.attempts, "syntax_valid": syntax_ok, "semantic_correct": sem, "failure": cat})
    n = len(rows) or 1
    return {"max_attempts": max_attempts, "n": len(rows),
            "syntax_valid_pct": round(100 * sum(r["syntax_valid"] for r in rows) / n, 1),
            "semantic_correct_pct": round(100 * sum(r["semantic_correct"] for r in rows) / n, 1),
            "avg_attempts": round(sum(r["attempts"] for r in rows) / n, 2), "failure_categories": cats, "rows": rows}


def run(adapter: EngineAdapter, provider: LLMProvider, limit: int | None = None) -> dict:
    bench = load_benchmark()[: limit or None]
    examples = load_examples()
    leaks = leakage(provider, bench, examples)
    with tempfile.TemporaryDirectory() as tmp:
        retriever = Retriever(provider, examples, Path(tmp) / "index.npz")
        with_retry = run_config(adapter, provider, retriever, bench, 3)
        without = run_config(adapter, provider, retriever, bench, 1)
    fake = isinstance(provider, FakeProvider)
    return {
        "provider": provider.name, "when": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "interpretation": ("OFFLINE FAKE PROVIDER: this measures retrieval echo (copying the nearest example), NOT translation "
                           "quality. Do not quote these numbers as evidence.") if fake else "live LLM run",
        "rule_source": "claude-draft: replace with team-written rules for the final numbers (CLAUDE.md section 11)",
        "leakage": {"threshold": LEAK_THRESHOLD, "max_similarity": round(max(s for *_, s in leaks), 3),
                    "over_threshold": [(a, b, round(s, 3)) for a, b, s in leaks if s > LEAK_THRESHOLD]},
        "with_retry": with_retry, "without_retry": without,
    }


def to_markdown(res: dict) -> str:
    w, o = res["with_retry"], res["without_retry"]
    lines = [f"# Benchmark ({res['provider']}, {w['n']} rules, {res['when']})", "", f"> {res['interpretation']}", "",
             "| metric | without retry (1 attempt) | with retry loop (max 3) |", "|---|---|---|",
             f"| syntax-valid % | {o['syntax_valid_pct']} | {w['syntax_valid_pct']} |",
             f"| semantically correct % | {o['semantic_correct_pct']} | {w['semantic_correct_pct']} |",
             f"| avg attempts | {o['avg_attempts']} | {w['avg_attempts']} |", "",
             f"Failure categories without retry: {o['failure_categories'] or 'none'}",
             f"Failure categories with retry: {w['failure_categories'] or 'none'}", "",
             f"Leakage: max cosine similarity benchmark-vs-retrieval = {res['leakage']['max_similarity']} "
             f"(threshold {res['leakage']['threshold']}); over threshold: {res['leakage']['over_threshold'] or 'none'}", "",
             f"Rule source: {res['rule_source']}"]
    return "\n".join(lines) + "\n"


def main() -> int:
    from app.engine.python_prototype import PythonPrototypeAdapter
    from app.llm.factory import get_provider
    ap = argparse.ArgumentParser()
    ap.add_argument("--limit", type=int)
    args = ap.parse_args()
    provider = get_provider()
    res = run(PythonPrototypeAdapter(), provider, args.limit)
    RESULTS_DIR.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    (RESULTS_DIR / f"{provider.name}-{stamp}.json").write_text(json.dumps(res, indent=2), encoding="utf-8")
    md = to_markdown(res)
    (RESULTS_DIR / f"{provider.name}-{stamp}.md").write_text(md, encoding="utf-8")
    print(md)
    return 0


if __name__ == "__main__":
    sys.exit(main())
