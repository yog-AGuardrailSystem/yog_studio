"""Templates: the example policies, grouped into packs, as starting points. Combining templates is checked by the
engine before it is offered. Drafted examples are labelled as needing team review."""
import yaml
from pydantic import BaseModel, Field

from app.core.config import EXAMPLES_DIR
from app.engine.adapter import EngineAdapter

POLICIES_DIR = EXAMPLES_DIR / "policies"
MAX_COMBINE = 6

PACK_TITLES = {
    "database": "Database administration", "files": "File access", "finance": "Payments and money",
    "generic": "General rules", "network": "Network and email", "smart_home": "Smart home",
}


class Template(BaseModel):
    id: str
    pack: str
    pack_title: str
    english: str
    tools_context: list[str] = Field(default_factory=list)
    source_label: str                    # team | claude-draft | ...
    reviewed: bool                       # False = a draft nobody on the team has reviewed yet
    yog: str
    scenarios: int


def load() -> list[Template]:
    out: list[Template] = []
    for path in sorted(POLICIES_DIR.glob("*.yaml")):
        data = yaml.safe_load(path.read_text(encoding="utf-8")) or []
        pack = path.stem
        for item in data:
            src = str(item.get("source", "unknown"))
            out.append(Template(id=item["id"], pack=pack, pack_title=PACK_TITLES.get(pack, pack.replace("_", " ").title()),
                                english=item["english"], tools_context=list(item.get("tools_context", [])),
                                source_label=src, reviewed=not src.startswith("claude-draft") and src != "unknown",
                                yog=item["gold_yog"], scenarios=len(item.get("scenarios", []))))
    return out


class CombineResult(BaseModel):
    ok: bool
    source: str
    errors: list[str]
    used: list[str]


def combine(adapter: EngineAdapter, ids: list[str]) -> CombineResult:
    """Merge the chosen templates into one program: repeated `fact` lines are kept once, the rest is concatenated.
    The result is only `ok` if the engine compiles it."""
    by_id = {t.id: t for t in load()}
    missing = [i for i in ids if i not in by_id]
    if missing:
        return CombineResult(ok=False, source="", errors=[f"unknown template: {m}" for m in missing[:3]], used=[])
    if not 1 <= len(ids) <= MAX_COMBINE:
        return CombineResult(ok=False, source="", errors=[f"choose between 1 and {MAX_COMBINE} templates"], used=[])
    seen_facts: set[str] = set()
    parts: list[str] = []
    for i in ids:
        lines = []
        for ln in by_id[i].yog.rstrip().split("\n"):
            if ln.startswith("fact "):
                key = " ".join(ln.split())
                if key in seen_facts:
                    continue
                seen_facts.add(key)
            lines.append(ln)
        parts.append(f"# from template {i}\n" + "\n".join(lines))
    source = "\n\n".join(parts) + "\n"
    errors = adapter.validate(source)
    return CombineResult(ok=not errors, source=source, errors=errors, used=list(ids))
