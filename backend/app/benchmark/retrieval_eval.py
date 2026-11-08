"""Does retrieval find the right example from a REWORDED query? (recall@k and MRR on benchmark/paraphrases.yaml)

Every example has a held-out paraphrase. We search with the paraphrase (plus the example's tool names, as in real use)
and check where the source example lands. This is what distinguishes a real embedding model from keyword overlap, and
it tells us whether RAG can help translation at all.

    cd backend && uv run python -m app.benchmark.retrieval_eval              # the configured provider
    cd backend && LLM_PROVIDER=fake uv run python -m app.benchmark.retrieval_eval
"""
import argparse
import json
import sys
import tempfile
from datetime import datetime, timezone
from pathlib import Path

import yaml

from app.benchmark.stats import fmt, proportion
from app.core.config import REPO_ROOT
from app.llm.provider import LLMProvider
from app.rag.examples import PolicyExample, load_retrieval_examples
from app.rag.retriever import Retriever

PARAPHRASES = REPO_ROOT / "benchmark" / "paraphrases.yaml"
RESULTS_DIR = REPO_ROOT / "benchmark" / "results"
KS = (1, 3, 5)


def load_paraphrases(path: Path = PARAPHRASES) -> list[dict]:
    return yaml.safe_load(path.read_text(encoding="utf-8")) or []


def evaluate_retrieval(provider: LLMProvider, examples: list[PolicyExample] | None = None,
                       paraphrases: list[dict] | None = None, ks: tuple[int, ...] = KS) -> dict:
    examples = examples if examples is not None else load_retrieval_examples()
    paraphrases = paraphrases if paraphrases is not None else load_paraphrases()
    by_id = {e.id: e for e in examples}
    missing = [p["id"] for p in paraphrases if p["id"] not in by_id]
    if missing:
        raise ValueError(f"paraphrases reference unknown examples: {missing}")
    with tempfile.TemporaryDirectory() as tmp:
        retriever = Retriever(provider, examples, Path(tmp) / "index.npz")
        rows = []
        for p in paraphrases:
            ex = by_id[p["id"]]
            tools = [t.split("(")[0] for t in ex.tools_context]
            hits = retriever.search(p["paraphrase"], tools, max(ks))
            ids = [h.id for h in hits]
            rank = ids.index(p["id"]) + 1 if p["id"] in ids else None
            rows.append({"id": p["id"], "source": ex.source, "tier": p.get("tier", "easy"), "rank": rank, "top1": ids[0] if ids else None,
                         "top1_score": hits[0].score if hits else None, "paraphrase": p["paraphrase"]})

    def metrics(subset: list[dict]) -> dict:
        n = len(subset)
        out = {f"recall@{k}": proportion(sum(1 for r in subset if r["rank"] and r["rank"] <= k), n) for k in ks}
        out["mrr"] = round(sum(1 / r["rank"] for r in subset if r["rank"]) / n, 3) if n else None
        out["n"] = n
        return out

    sources = sorted({r["source"] for r in rows})
    tiers = sorted({r["tier"] for r in rows})
    return {
        "provider": provider.name, "model": provider.model, "embed_model": provider.embed_model,
        "when": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "overall": metrics(rows),
        "by_source": {s: metrics([r for r in rows if r["source"] == s]) for s in sources},
        "by_tier": {t: metrics([r for r in rows if r["tier"] == t]) for t in tiers},
        "misses": [r for r in rows if not r["rank"] or r["rank"] > 1],
        "rows": rows,
    }


def to_markdown(res: dict) -> str:
    o = res["overall"]
    lines = [f"# Retrieval evaluation ({res['provider']}, embed model {res['embed_model'] or 'n/a'}, n={o['n']})", "",
             "Each example has a held-out paraphrase; the query is the paraphrase and the target is its source example.", "",
             "| metric | result |", "|---|---|"]
    lines += [f"| recall@{k} | {fmt(o[f'recall@{k}'])} |" for k in KS]
    lines += [f"| MRR | {o['mrr']} |", ""]
    for t, m in res["by_tier"].items():
        lines.append(f"- {t} paraphrases: recall@1 {fmt(m['recall@1'])}, recall@3 {fmt(m['recall@3'])}, MRR {m['mrr']} (n={m['n']})")
    for s, m in res["by_source"].items():
        lines.append(f"- {s}: recall@1 {fmt(m['recall@1'])}, recall@5 {fmt(m['recall@5'])} (n={m['n']})")
    lines += ["", f"Not found at rank 1: {len(res['misses'])} of {o['n']}."]
    return "\n".join(lines) + "\n"


def main() -> int:
    from app.llm.factory import get_provider
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", type=Path, default=RESULTS_DIR)
    args = ap.parse_args()
    provider = get_provider()
    res = evaluate_retrieval(provider)
    fake = provider.name == "fake"
    out = args.out / "fake" if fake else args.out        # offline-fake numbers never sit beside real ones
    out.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    (out / f"retrieval-{provider.name}-{stamp}.json").write_text(json.dumps(res, indent=2), encoding="utf-8")
    md = to_markdown(res)
    (out / f"retrieval-{provider.name}-{stamp}.md").write_text(md, encoding="utf-8")
    print(md)
    if fake:
        print("NOTE: offline fake provider (hashed bag-of-words). Compare with a real embedding model before quoting.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
