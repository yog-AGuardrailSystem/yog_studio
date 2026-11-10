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
from app.llm.provider import LLMProvider, embed_texts
from app.rag.examples import PolicyExample, load_retrieval_examples
from app.rag.retriever import Retriever

PARAPHRASES = REPO_ROOT / "benchmark" / "paraphrases.yaml"
RESULTS_DIR = REPO_ROOT / "benchmark" / "results"
KS = (1, 3, 5)


def load_paraphrases(path: Path = PARAPHRASES) -> list[dict]:
    return yaml.safe_load(path.read_text(encoding="utf-8")) or []


def evaluate_retrieval(provider: LLMProvider, examples: list[PolicyExample] | None = None,
                       paraphrases: list[dict] | None = None, ks: tuple[int, ...] = KS, hybrid: bool = True, lex_weight: float | None = None,
                       oracle_tools: bool = False) -> dict:
    examples = examples if examples is not None else load_retrieval_examples()
    paraphrases = paraphrases if paraphrases is not None else load_paraphrases()
    by_id = {e.id: e for e in examples}
    missing = [p["id"] for p in paraphrases if p["id"] not in by_id]
    if missing:
        raise ValueError(f"paraphrases reference unknown examples: {missing}")
    with tempfile.TemporaryDirectory() as tmp:
        retriever = Retriever(provider, examples, Path(tmp) / "index.npz", hybrid=hybrid, lex_weight=lex_weight)
        embed_texts(provider, [p["paraphrase"] for p in paraphrases], task="query")   # one batched call fills the cache
        rows = []
        for p in paraphrases:
            ex = by_id[p["id"]]
            # tools are NOT given by default: handing each example its own tool names would flatter the result
            tools = [t.split("(")[0] for t in ex.tools_context] if oracle_tools else []
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
        "provider": provider.name, "oracle_tools": oracle_tools, "hybrid": hybrid, "lex_weight": retriever.lex_weight, "model": provider.model, "embed_model": provider.embed_model,
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


NEGATIVES = REPO_ROOT / "benchmark" / "retrieval_negatives.yaml"


def load_negatives(path: Path = NEGATIVES) -> list[dict]:
    return yaml.safe_load(path.read_text(encoding="utf-8")) or []


def calibrate_floor(provider: LLMProvider, examples: list[PolicyExample] | None = None,
                    paraphrases: list[dict] | None = None, negatives: list[dict] | None = None) -> dict:
    """Pick the dense-cosine floor for this provider from data, not by feel.

    positives = cosine between each held-out paraphrase and the example it paraphrases (it should count as relevant)
    negatives = best cosine any example reaches for an off-topic query (it must NOT count as relevant)
    Separable -> floor halfway between the worst-case negative and the 10th-percentile positive.
    Overlapping -> floor just above the best negative (strict: no off-topic query passes) and report how many
    positives that costs, so the trade-off is visible instead of hidden."""
    import numpy as np
    examples = examples if examples is not None else load_retrieval_examples()
    paraphrases = paraphrases if paraphrases is not None else load_paraphrases()
    negatives = negatives if negatives is not None else load_negatives()
    by_id = {e.id: e for e in examples}
    with tempfile.TemporaryDirectory() as tmp:
        retriever = Retriever(provider, examples, Path(tmp) / "index.npz")
        embed_texts(provider, [p["paraphrase"] for p in paraphrases] + [n["query"] for n in negatives], task="query")
        pos = []
        for p in paraphrases:
            tools = [t.split("(")[0] for t in by_id[p["id"]].tools_context]
            hits = {h.id: h.score for h in retriever.search(p["paraphrase"], tools, len(examples))}
            pos.append(hits[p["id"]])
        neg = [retriever.search(n["query"], [], 1)[0].score for n in negatives]
    pos_a, neg_a = np.array(pos), np.array(neg)
    neg_max, pos_p10 = float(neg_a.max()), float(np.percentile(pos_a, 10))
    separable = neg_max < pos_p10
    floor = (neg_max + pos_p10) / 2 if separable else neg_max + 0.005
    return {"floor": round(floor, 3), "separable": separable, "n_positive": len(pos), "n_negative": len(neg),
            "negative_max": round(neg_max, 3), "positive_p10": round(pos_p10, 3),
            "positive_median": round(float(np.median(pos_a)), 3),
            "positives_kept": round(float((pos_a >= floor).mean()), 3),
            "negatives_rejected": round(float((neg_a < floor).mean()), 3),
            "when": datetime.now(timezone.utc).isoformat(timespec="seconds")}


def main() -> int:
    from app.llm.factory import get_provider
    from app.rag.retriever import FLOORS_PATH, floor_key, load_floors
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", type=Path, default=RESULTS_DIR)
    ap.add_argument("--calibrate", action="store_true", help="measure and save the relevance floor for the configured provider")
    args = ap.parse_args()
    provider = get_provider()
    if args.calibrate:
        cal = calibrate_floor(provider)
        floors = load_floors()
        floors[floor_key(provider)] = cal
        FLOORS_PATH.write_text(json.dumps(floors, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        print(json.dumps({floor_key(provider): cal}, indent=2))
        return 0
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
