"""Team review pack: turn Claude-drafted examples into human-reviewed ones, safely.

    make a pack:   uv run python -m app.benchmark.review pack --reviewers Varun,Viz,Priya --out review/
    apply answers: uv run python -m app.benchmark.review apply review/Varun.md review/Viz.md

Each sheet lists items (English, YOG, plain-English readback, scenarios). A reviewer writes under every item:
    VERDICT: ok | reject            (anything else is left untouched)
    REVISED_YOG:                    (optional) a fenced block with the corrected policy
Applying re-validates (compiles, and passes the item's own scenarios) BEFORE flipping `source` to
`reviewed-by:<name>`; a revision that fails is refused and the item stays claude-draft.
"""
import argparse
import re
import sys
from pathlib import Path

import yaml

from app.benchmark.runner import BENCH_FILE
from app.core.config import REPO_ROOT
from app.engine.adapter import EngineAdapter, EngineError
from app.explain.explainer import explain
from app.rag.examples import POLICIES_DIR, PolicyExample


def _yaml_files() -> list[Path]:
    return [BENCH_FILE, *sorted(POLICIES_DIR.glob("*.yaml"))]


def drafted_items(files: list[Path] | None = None) -> list[tuple[Path, PolicyExample]]:
    out = []
    for f in files or _yaml_files():
        for x in yaml.safe_load(f.read_text(encoding="utf-8")) or []:
            ex = PolicyExample(**x)
            if ex.source == "claude-draft":
                out.append((f, ex))
    return out


def assign(items: list, reviewers: list[str]) -> dict[str, list]:
    """Round-robin; every item gets exactly one reviewer."""
    out = {r: [] for r in reviewers}
    for i, it in enumerate(items):
        out[reviewers[i % len(reviewers)]].append(it)
    return out


def render_sheet(adapter: EngineAdapter, reviewer: str, items: list[tuple[Path, PolicyExample]]) -> str:
    lines = [f"# YOG review sheet for {reviewer}", "",
             "For each item: read the English, the YOG and the readback. Is the YOG what the English means?",
             "Write `VERDICT: ok` or `VERDICT: reject` under the item. To fix it, add a `REVISED_YOG:` fenced block.", ""]
    for f, ex in items:
        try:
            readback = "\n".join(f"- {c.text}" for c in explain(adapter, ex.gold_yog).clauses)
        except EngineError as e:
            readback = f"(readback unavailable: {e})"
        scen = "\n".join(f"- {s.action}({s.actor}, {s.resource}) {s.context} -> {s.expected}" for s in ex.scenarios)
        lines += [f"## {ex.id}  ({f.name})", "", f"**English:** {ex.english}", "", "```yog", ex.gold_yog.rstrip(), "```", "",
                  "Readback:", readback, "", "Scenarios:", scen or "(none)", "", "VERDICT: ", "", "REVISED_YOG:", ""]
    return "\n".join(lines) + "\n"


def parse_sheet(text: str) -> dict[str, dict]:
    """{id: {verdict, revised}} for every item with a recognised verdict."""
    out = {}
    for block in re.split(r"^## ", text, flags=re.M)[1:]:
        iid = block.split()[0]
        v = re.search(r"^VERDICT:[ \t]*(ok|reject)\b", block, flags=re.M | re.I)
        if not v:
            continue
        rev = re.search(r"REVISED_YOG:\s*```[a-z]*\n(.*?)```", block, flags=re.S)
        out[iid] = {"verdict": v.group(1).lower(), "revised": rev.group(1) if rev else None}
    return out


def validate(adapter: EngineAdapter, ex: PolicyExample, yog: str) -> list[str]:
    problems = list(adapter.validate(yog))
    if problems:
        return problems
    for s in ex.scenarios:
        try:
            got = adapter.check(yog, s.actor, s.action, s.resource, s.context).decision
        except EngineError as e:
            return [f"scenario errors: {e}"]
        if got != s.expected:
            problems.append(f"{s.action}({s.actor}, {s.resource}) {s.context}: expected {s.expected}, got {got}")
    return problems


def _rewrite_item(text: str, iid: str, name: str, new_yog: str | None) -> str:
    """Edit the YAML as text so formatting and comments survive."""
    m = re.search(rf"^- id: {re.escape(iid)}[ \t]*$", text, flags=re.M)
    if not m:
        raise KeyError(iid)
    nxt = re.search(r"^- id: ", text[m.end():], flags=re.M)
    end = m.end() + nxt.start() if nxt else len(text)
    block = text[m.start():end]
    block = re.sub(r"^(\s*source:[ \t]*).*$", rf"\g<1>reviewed-by:{name}", block, count=1, flags=re.M)
    if new_yog is not None:
        def repl(mm):
            body = "\n".join(("    " + ln if ln.strip() else "") for ln in new_yog.rstrip().splitlines())
            return f"{mm.group(1)}\n{body}\n"
        block = re.sub(r"^(  gold_yog:[ \t]*\|)\n(?:    .*\n|[ \t]*\n)*", repl, block, count=1, flags=re.M)
    return text[:m.start()] + block + text[end:]


def apply(adapter: EngineAdapter, sheets: dict[str, str], files: list[Path] | None = None, dry: bool = False) -> dict:
    """sheets = {reviewer name: sheet text}. Returns what was accepted, refused and rejected."""
    report = {"accepted": [], "refused": [], "rejected": []}
    items = {ex.id: (f, ex) for f, ex in drafted_items(files)}
    for name, text in sheets.items():
        for iid, ans in parse_sheet(text).items():
            if iid not in items:
                continue
            f, ex = items[iid]
            if ans["verdict"] == "reject":
                report["rejected"].append(iid)
                continue
            yog = ans["revised"] or ex.gold_yog
            problems = validate(adapter, ex, yog)
            if problems:
                report["refused"].append({"id": iid, "problems": problems})
                continue
            if not dry:
                f.write_text(_rewrite_item(f.read_text(encoding="utf-8"), iid, name, ans["revised"]),
                             encoding="utf-8", newline="")
            report["accepted"].append(iid)
    return report


def main() -> int:
    from app.engine.python_prototype import PythonPrototypeAdapter
    adapter = PythonPrototypeAdapter()
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    p = sub.add_parser("pack")
    p.add_argument("--reviewers", required=True)
    p.add_argument("--out", type=Path, default=REPO_ROOT / "review")
    a = sub.add_parser("apply")
    a.add_argument("sheets", nargs="+", type=Path)
    a.add_argument("--dry", action="store_true")
    args = ap.parse_args()
    if args.cmd == "pack":
        names = [n.strip() for n in args.reviewers.split(",") if n.strip()]
        args.out.mkdir(parents=True, exist_ok=True)
        for n, its in assign(drafted_items(), names).items():
            (args.out / f"{n}.md").write_text(render_sheet(adapter, n, its), encoding="utf-8")
            print(f"{n}: {len(its)} items -> {args.out / (n + '.md')}")
        return 0
    rep = apply(adapter, {s.stem: s.read_text(encoding="utf-8") for s in args.sheets}, dry=args.dry)
    print(f"accepted {len(rep['accepted'])}, refused {len(rep['refused'])}, rejected {len(rep['rejected'])}")
    for r in rep["refused"]:
        print("REFUSED", r["id"], r["problems"])
    return 0


if __name__ == "__main__":
    sys.exit(main())
