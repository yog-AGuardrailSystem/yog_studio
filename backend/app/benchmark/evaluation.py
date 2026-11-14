"""The evaluation harness: English rule -> generated YOG -> compared with the gold policy, across a grid of
ablations, on a frozen dev/test split, with full provenance and confidence intervals.

Semantic correctness = the generated policy gives the same ALLOW/DENY as the gold policy on EVERY scenario
(never string equality). The grid answers "does each part earn its place?":

    full         RAG on,     up to 3 attempts, independent-scenario gate on
    no-gate      RAG on,     up to 3 attempts, no gate
    no-retry     RAG on,     1 attempt,        no gate
    no-rag       no examples,up to 3 attempts, no gate
    random-rag   RANDOM examples (same count) up to 3 attempts, no gate   <- separates "relevant" from "any examples"

Integrity rules: prompts are tuned on the DEV split only. The TEST split (benchmark/split.json, frozen) is for the
final report; every run on it is appended to benchmark/results/test_runs.log with the prompt hash, so peeking is
visible. Offline-fake results are written to results/fake/ and labelled; they never sit beside real ones.

    cd backend && uv run python -m app.benchmark.evaluation --split dev --limit 5
    cd backend && uv run python -m app.benchmark.evaluation --split test --configs full,no-rag
"""
import argparse
import hashlib
import json
import os
import random
import subprocess
import sys
import tempfile
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

from app.benchmark.runner import BENCH_FILE, categorize, load_benchmark, semantic_match, tools_from_context
from app.benchmark.stats import fmt, percentile, proportion
from app.core.config import REPO_ROOT
from app.engine.adapter import EngineAdapter, EngineError
from app.evaluate.evaluator import run_scenario
from app.evaluate.scenarios import generate_independent
from app.llm.provider import PROMPTS_DIR, LLMProvider
from app.rag.examples import POLICIES_DIR, PolicyExample, load_retrieval_examples
from app.rag.retriever import Retrieved, Retriever
from app.translate.translator import lint, translate

RESULTS_DIR = REPO_ROOT / "benchmark" / "results"
SPLIT_FILE = REPO_ROOT / "benchmark" / "split.json"
ENGINE_VERSION_FILE = REPO_ROOT / "engine" / "VERSION"
PROMPT_FILES = ("translate.md", "repair.md", "scenarios.md")


@dataclass(frozen=True)
class Config:
    name: str
    rag: str            # on | random | off
    max_attempts: int
    gate: bool


CONFIGS: dict[str, Config] = {c.name: c for c in (
    Config("full", "on", 3, True),
    Config("no-gate", "on", 3, False),
    Config("no-retry", "on", 1, False),
    Config("no-rag", "off", 3, False),
    Config("random-rag", "random", 3, False),
)}


# ------------------------------------------------------------------ the frozen dev/test split
def assign_test(rule_id: str) -> bool:
    """Deterministic: about a third of the rules go to the frozen test set, chosen by hash, not by anyone's taste."""
    return int(hashlib.sha256(rule_id.encode()).hexdigest(), 16) % 3 == 0


def get_split(bench: list[PolicyExample], path: Path | None = None) -> dict:
    """Load benchmark/split.json, creating it on first use. A rule added later is DEV unless the file says otherwise,
    so growing the benchmark can never silently move a rule into (or out of) the frozen test set."""
    path = path or SPLIT_FILE
    if path.exists():
        data = json.loads(path.read_text(encoding="utf-8"))
    else:
        data = {"rule": "sha256(id) % 3 == 0 -> test; frozen on creation, new rules default to dev",
                "created": datetime.now(timezone.utc).date().isoformat(),
                "test": sorted(e.id for e in bench if assign_test(e.id))}
        path.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")
    test = set(data["test"])
    return {"test": sorted(test & {e.id for e in bench}),
            "dev": sorted({e.id for e in bench} - test), "rule": data["rule"], "created": data["created"]}


def select(bench: list[PolicyExample], split: dict, which: str) -> list[PolicyExample]:
    if which == "all":
        return bench
    ids = set(split[which])
    return [e for e in bench if e.id in ids]


# ------------------------------------------------------------------ retrievers for the ablations
class NullRetriever:
    def search(self, english: str, tools: list[str] | None = None, k: int = 3) -> list[Retrieved]:
        return []


class RandomRetriever:
    """Returns k random examples (seeded per query text): the control for 'is it the RELEVANT examples that help?'"""

    def __init__(self, examples: list[PolicyExample], seed: int = 20261108) -> None:
        self.examples, self.seed = examples, seed

    def search(self, english: str, tools: list[str] | None = None, k: int = 3) -> list[Retrieved]:
        rng = random.Random(f"{self.seed}:{english}")
        picks = rng.sample(self.examples, min(k, len(self.examples)))
        return [Retrieved(id=e.id, english=e.english, tools_context=e.tools_context, gold_yog=e.gold_yog,
                          score=0.0, source=e.source) for e in picks]


def make_retriever(mode: str, provider: LLMProvider, examples: list[PolicyExample], tmp: Path):
    if mode == "off":
        return NullRetriever()
    if mode == "random":
        return RandomRetriever(examples)
    return Retriever(provider, examples, tmp / "index.npz")


# ------------------------------------------------------------------ one rule, one configuration
def differing_scenarios(adapter: EngineAdapter, gold: PolicyExample, policy: str, limit: int = 5) -> list[str]:
    out = []
    for s in gold.scenarios:
        want = adapter.check(gold.gold_yog, s.actor, s.action, s.resource, s.context).decision
        try:
            got = adapter.check(policy, s.actor, s.action, s.resource, s.context).decision
        except EngineError as e:
            out.append(f"{s.action}({s.actor}, {s.resource}) {s.context}: policy does not run ({e})")
            continue
        if got != want:
            out.append(f"{s.action}({s.actor}, {s.resource}) {s.context}: gold {want}, generated {got}")
    return out[:limit]


def run_rule(adapter: EngineAdapter, provider: LLMProvider, retriever, ex: PolicyExample, cfg: Config) -> dict:
    tools = tools_from_context(ex.tools_context)
    t0 = time.perf_counter()
    try:
        d = translate([ex.english], tools, provider, retriever, adapter, max_attempts=cfg.max_attempts, verify=cfg.gate)
    except Exception as e:                                           # noqa: BLE001 - one rule never sinks the run
        return {"id": ex.id, "english": ex.english, "yog_source": "", "attempts": 0, "syntax_valid": False,
                "semantic_correct": False, "verified": None, "failure": "exception", "differing": [],
                "errors": [f"{type(e).__name__}: {e}"], "latency_s": round(time.perf_counter() - t0, 2)}
    latency = round(time.perf_counter() - t0, 2)
    syntax_ok = bool(d.yog_source.strip()) and not adapter.validate(d.yog_source)
    sem = bool(syntax_ok and not lint(adapter, d.yog_source, tools) and semantic_match(adapter, ex, d.yog_source))
    cat = categorize(adapter, d.yog_source, tools, d.errors, sem)
    return {"id": ex.id, "english": ex.english, "yog_source": d.yog_source, "attempts": d.attempts,
            "syntax_valid": syntax_ok, "semantic_correct": sem, "verified": d.verified, "failure": cat,
            "differing": [] if sem or not syntax_ok else differing_scenarios(adapter, ex, d.yog_source),
            "errors": d.errors, "latency_s": latency}


# ------------------------------------------------------------------ aggregate
def summarize(rows: list[dict]) -> dict:
    n = len(rows)
    sem = [r for r in rows if r["semantic_correct"]]
    cats: dict[str, list[dict]] = {}
    for r in rows:
        if r["failure"]:
            cats.setdefault(r["failure"], []).append(r)
    ver_t = [r for r in rows if r["verified"] is True]
    ver_f = [r for r in rows if r["verified"] is False]
    lat = [r["latency_s"] for r in rows]
    return {
        "n": n,
        "syntax_valid": proportion(sum(r["syntax_valid"] for r in rows), n),
        "semantic_correct": proportion(len(sem), n),
        "avg_attempts": round(sum(r["attempts"] for r in rows) / n, 2) if n else None,
        "latency_p50_s": percentile(lat, 50), "latency_p95_s": percentile(lat, 95),
        "verified": {"true": len(ver_t), "false": len(ver_f), "unknown": n - len(ver_t) - len(ver_f),
                     "semantic_given_verified_true": proportion(sum(r["semantic_correct"] for r in ver_t), len(ver_t)),
                     "semantic_given_verified_false": proportion(sum(r["semantic_correct"] for r in ver_f), len(ver_f))},
        "failure_categories": {c: len(v) for c, v in cats.items()},
        "failure_examples": {c: [{"id": r["id"], "english": r["english"], "differing": r["differing"][:2],
                                  "errors": r["errors"][:2]} for r in v[:3]] for c, v in cats.items()},
    }


def oracle_agreement(adapter: EngineAdapter, provider: LLMProvider, bench: list[PolicyExample]) -> dict:
    """How often do scenarios written by the LLM from the English alone agree with the GOLD policy? A low number means
    the independent check is unreliable (or the gold is wrong), so `verified=False` should not be trusted."""
    counted = agreed = skipped_rules = 0
    for ex in bench:
        scenarios, problems = generate_independent([ex.english], tools_from_context(ex.tools_context), provider)
        if not scenarios:
            skipped_rules += 1
            continue
        for s in scenarios:
            r = run_scenario(adapter, ex.gold_yog, s)
            if r.error:
                continue
            counted += 1
            agreed += bool(r.passed)
    return {"agreement": proportion(agreed, counted), "rules_without_scenarios": skipped_rules}


# ------------------------------------------------------------------ robustness (prompt injection via docstrings)
ROBUSTNESS_FILE = REPO_ROOT / "benchmark" / "robustness.yaml"


def load_robustness(path: Path = ROBUSTNESS_FILE) -> list[dict]:
    import yaml
    return yaml.safe_load(path.read_text(encoding="utf-8")) or []


def run_robustness(adapter: EngineAdapter, provider: LLMProvider, retriever, cases: list[dict] | None = None) -> dict:
    """Tool docstrings are untrusted. A case passes only if the generated policy still gives every required decision."""
    from app.core.models import Param, Tool
    cases = cases if cases is not None else load_robustness()
    rows = []
    for c in cases:
        tools = [Tool(name=t["name"], params=[Param(name=p) for p in t.get("params", [])],
                      docstring=t.get("docstring"), source_line=1) for t in c["tools"]]
        try:
            d = translate([c["english"]], tools, provider, retriever, adapter, verify=False)
        except Exception as e:                                       # noqa: BLE001
            rows.append({"id": c["id"], "passed": False, "failed": [f"exception: {e}"], "yog_source": ""})
            continue
        failed = []
        for s in c["scenarios"]:
            try:
                got = adapter.check(d.yog_source, s["actor"], s["action"], s["resource"], s.get("context", [])).decision
            except EngineError as e:
                got = f"error: {e}"
            if got != s["expected"]:
                failed.append(f"{s['action']}({s['actor']}, {s['resource']}) {s.get('context', [])}: wanted {s['expected']}, got {got}")
        rows.append({"id": c["id"], "passed": not failed, "failed": failed, "yog_source": d.yog_source})
    return {"passed": proportion(sum(r["passed"] for r in rows), len(rows)), "rows": rows}


# ------------------------------------------------------------------ provenance
def _sha(*chunks: bytes) -> str:
    h = hashlib.sha256()
    for c in chunks:
        h.update(c)
    return h.hexdigest()[:16]


def prompt_hash(prompts_dir: Path = PROMPTS_DIR) -> str:
    return _sha(*[(prompts_dir / f).read_bytes() for f in PROMPT_FILES])


def dataset_hash() -> str:
    files = [BENCH_FILE, *sorted(POLICIES_DIR.glob("*.yaml"))]
    return _sha(*[f.read_bytes() for f in files])


def _git_commit() -> str:
    try:
        return subprocess.run(["git", "rev-parse", "HEAD"], cwd=REPO_ROOT, capture_output=True, text=True,
                              timeout=10, check=True).stdout.strip()
    except (OSError, subprocess.SubprocessError):
        return os.environ.get("GIT_COMMIT", "unknown")


def provenance(provider: LLMProvider, bench: list[PolicyExample], split_name: str, split: dict) -> dict:
    sources: dict[str, int] = {}
    for e in bench:
        sources[e.source] = sources.get(e.source, 0) + 1
    engine = ENGINE_VERSION_FILE.read_text(encoding="utf-8").strip() if ENGINE_VERSION_FILE.exists() else "unknown"
    return {
        "provider": provider.name, "model": provider.model, "embed_model": provider.embed_model,
        "when": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "git_commit": _git_commit(), "engine_version": engine,
        "prompt_hash": prompt_hash(), "dataset_hash": dataset_hash(),
        "split": split_name, "n_rules": len(bench), "split_rule": split["rule"], "split_created": split["created"],
        "rule_sources": sources,
    }


def interpretation(provider: LLMProvider, sources: dict[str, int]) -> list[str]:
    notes = []
    if provider.name == "fake":
        notes.append("OFFLINE FAKE PROVIDER: this measures retrieval echo (copying the nearest example), NOT translation "
                     "quality. Do not quote these numbers as evidence.")
    drafted = sources.get("claude-draft", 0)
    if drafted:
        notes.append(f"{drafted} of {sum(sources.values())} rules and their scenarios were drafted by Claude and are not "
                     "yet reviewed by the team: a prototype result, not a final benchmark.")
    return notes


# ------------------------------------------------------------------ the grid
def run_grid(adapter: EngineAdapter, provider: LLMProvider, bench: list[PolicyExample], configs: list[Config], *,
             examples: list[PolicyExample] | None = None, partial: Path | None = None,
             progress=lambda msg: None) -> dict:
    examples = examples if examples is not None else load_retrieval_examples()
    done: dict[tuple[str, str], dict] = {}
    if partial and partial.exists():
        for line in partial.read_text(encoding="utf-8").splitlines():
            if line.strip():
                rec = json.loads(line)
                done[(rec["config"], rec["id"])] = rec["row"]
    out: dict[str, dict] = {}
    with tempfile.TemporaryDirectory() as tmp:
        for cfg in configs:
            retriever = make_retriever(cfg.rag, provider, examples, Path(tmp) / cfg.name)
            usage0 = provider.usage.snapshot()
            rows = []
            for i, ex in enumerate(bench, 1):
                key = (cfg.name, ex.id)
                if key in done:
                    rows.append(done[key])
                    continue
                row = run_rule(adapter, provider, retriever, ex, cfg)
                rows.append(row)
                if partial:
                    with partial.open("a", encoding="utf-8") as fh:
                        fh.write(json.dumps({"config": cfg.name, "id": ex.id, "row": row}) + "\n")
                progress(f"[{cfg.name}] {i}/{len(bench)} {ex.id}: {'OK' if row['semantic_correct'] else row['failure']}")
            usage1 = provider.usage.snapshot()
            out[cfg.name] = {"config": {"rag": cfg.rag, "max_attempts": cfg.max_attempts, "gate": cfg.gate},
                             "summary": summarize(rows),
                             "usage": {k: round(usage1[k] - usage0[k], 2) for k in usage1}, "rows": rows}
    return out


def run(adapter: EngineAdapter, provider: LLMProvider, *, split_name: str = "dev", config_names: list[str] | None = None,
        limit: int | None = None, partial: Path | None = None, with_oracle: bool = True,
        with_robustness: bool = False,
        split_path: Path | None = None, progress=lambda msg: None) -> dict:
    bench_all = load_benchmark()
    split = get_split(bench_all, split_path)
    bench = select(bench_all, split, split_name)[: limit or None]
    configs = [CONFIGS[n] for n in (config_names or list(CONFIGS))]
    res = provenance(provider, bench, split_name, split)
    res["interpretation"] = interpretation(provider, res["rule_sources"])
    res["results"] = run_grid(adapter, provider, bench, configs, partial=partial, progress=progress)
    if with_robustness:
        with tempfile.TemporaryDirectory() as tmp:
            res["robustness"] = run_robustness(adapter, provider, make_retriever("on", provider, load_retrieval_examples(), Path(tmp)))
    if with_oracle and provider.name != "fake":
        res["oracle"] = oracle_agreement(adapter, provider, bench)
    res["usage_total"] = provider.usage.snapshot()
    return res


# ------------------------------------------------------------------ reporting
def to_markdown(res: dict) -> str:
    lines = [f"# Evaluation: {res['provider']} {res['model'] or ''} on the {res['split']} split ({res['n_rules']} rules)", ""]
    lines += [f"> {n}" for n in res["interpretation"]] + [""] if res["interpretation"] else []
    lines += ["| configuration | syntax-valid | semantically correct | avg attempts | p50 / p95 latency |", "|---|---|---|---|---|"]
    for name, r in res["results"].items():
        s = r["summary"]
        lines.append(f"| {name} | {fmt(s['syntax_valid'])} | {fmt(s['semantic_correct'])} | {s['avg_attempts']} | "
                     f"{s['latency_p50_s']}s / {s['latency_p95_s']}s |")
    lines += ["", "With a few dozen rules, differences under about 15 points are not statistically meaningful: read the "
              "confidence intervals, not just the percentages.", ""]
    res_cfg = res["results"]
    if "full" in res_cfg:
        v = res_cfg["full"]["summary"]["verified"]
        lines += ["**Does the independent check help?** In the `full` configuration "
                  f"{v['true']} drafts were verified, {v['false']} were flagged, {v['unknown']} had no check. "
                  f"Correct when verified: {fmt(v['semantic_given_verified_true'])}. "
                  f"Correct when flagged: {fmt(v['semantic_given_verified_false'])}.", ""]
    if "robustness" in res:
        rb = res["robustness"]
        lines += [f"**Prompt-injection robustness** (hostile tool docstrings): {fmt(rb['passed'])}. "
                  f"Failed: {[r['id'] for r in rb['rows'] if not r['passed']] or 'none'}.", ""]
    if "oracle" in res:
        lines += [f"**Is the independent check itself reliable?** Scenarios written from the English agreed with the gold "
                  f"policy {fmt(res['oracle']['agreement'])}.", ""]
    for name, r in res_cfg.items():
        cats = r["summary"]["failure_categories"]
        lines.append(f"- {name} failures: {cats or 'none'}")
    lines += ["", "## Provenance", "",
              f"provider `{res['provider']}`, model `{res['model']}`, embeddings `{res['embed_model']}`; engine `{res['engine_version']}`; "
              f"git `{res['git_commit'][:10]}`; prompts `{res['prompt_hash']}`; dataset `{res['dataset_hash']}`; "
              f"rule sources {res['rule_sources']}; split rule: {res['split_rule']}.",
              f"tokens: {res['usage_total']['prompt_tokens']} in / {res['usage_total']['output_tokens']} out, "
              f"{res['usage_total']['calls']} calls, {res['usage_total']['retries']} retries."]
    return "\n".join(lines) + "\n"


def output_dir(provider: LLMProvider, base: Path = RESULTS_DIR) -> Path:
    return base / "fake" if provider.name == "fake" else base


def log_test_run(res: dict, base: Path = RESULTS_DIR) -> None:
    """An audit trail of every look at the frozen test set."""
    base.mkdir(parents=True, exist_ok=True)
    entry = {"when": res["when"], "provider": res["provider"], "model": res["model"], "prompt_hash": res["prompt_hash"],
             "configs": list(res["results"]), "git_commit": res["git_commit"][:10]}
    with (base / "test_runs.log").open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(entry) + "\n")


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--split", choices=["dev", "test", "all"], default="dev")
    ap.add_argument("--configs", help=f"comma list from: {', '.join(CONFIGS)} (default: all)")
    ap.add_argument("--limit", type=int)
    ap.add_argument("--resume", type=Path, help="a partial .jsonl from an interrupted run")
    ap.add_argument("--robustness", action="store_true", help="also run the prompt-injection set")
    ap.add_argument("--no-cache", action="store_true", help="do not reuse cached LLM answers")
    ap.add_argument("--out", type=Path, default=RESULTS_DIR)
    ap.add_argument("--engine", choices=["python", "c"], default=os.environ.get("YOG_ENGINE", "python"),
                    help="which YOG engine decides (default: $YOG_ENGINE or python)")
    args = ap.parse_args()
    if not args.no_cache:
        os.environ.setdefault("LLM_CACHE_GENERATE", "1")         # identical prompts are free and reproducible
    from app.llm.factory import get_provider
    provider = get_provider()
    names = args.configs.split(",") if args.configs else None
    if names and (bad := [n for n in names if n not in CONFIGS]):
        print(f"unknown configuration(s): {bad}. Choose from {list(CONFIGS)}")
        return 2
    if args.split in ("test", "all"):
        print("NOTE: the TEST split is for the final report. Do not tune prompts after looking at it.")
    out = output_dir(provider, args.out)
    out.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    partial = args.resume or out / f".partial-{args.split}-{provider.name}-{stamp}.jsonl"
    from app.api.deps import make_adapter
    res = run(make_adapter(args.engine), provider, split_name=args.split, config_names=names, limit=args.limit,
              partial=partial, with_robustness=args.robustness, progress=print)
    res["engine"] = args.engine
    if args.split in ("test", "all"):
        log_test_run(res, args.out)
    base = f"eval-{args.split}-{provider.name}-{stamp}"
    (out / f"{base}.json").write_text(json.dumps(res, indent=2), encoding="utf-8")
    md = to_markdown(res)
    (out / f"{base}.md").write_text(md, encoding="utf-8")
    print(md)
    return 0


if __name__ == "__main__":
    sys.exit(main())
