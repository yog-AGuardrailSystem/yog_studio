"""Version History: every approval is already saved and never edited. This adds the list, the diff, and the *behaviour*
difference: both versions are run on the same requests and the ones whose answer changed are listed."""
import difflib

from pydantic import BaseModel, Field

from app.engine.adapter import EngineAdapter
from app.policies.store import PolicyRecord, PolicyStore
from app.studio.common import Budget, BudgetExceeded, safe_check_many, shape
from app.studio.gaps import targeted_probes

MAX_FLIPS = 200


class VersionSummary(BaseModel):
    id: str
    approved_at: str
    note: str
    parent_id: str | None
    restored_from: str | None
    clauses: int
    rules: int                           # english rules the human wrote for it
    pass_pct: float | None
    latest: bool


class Flip(BaseModel):
    actor: str
    action: str
    resource: str
    context: list[str]
    before: str
    after: str


class DiffResult(BaseModel):
    a: str
    b: str
    text_diff: str
    added: int
    removed: int
    probes: int
    flips: list[Flip]
    flips_total: int
    changed_actions: list[str]
    summary: str


def _clauses(rec: PolicyRecord) -> int:
    return sum(1 for ln in rec.yog_source.split("\n") if ln.startswith(("allow ", "deny ", "rule ")))


def summaries(store: PolicyStore) -> list[VersionSummary]:
    recs = store.list()
    out = []
    for i, r in enumerate(recs):
        ev = (r.evaluation or {}).get("summary", {}) if isinstance(r.evaluation, dict) else {}
        out.append(VersionSummary(id=r.id, approved_at=r.approved_at, note=r.note, parent_id=r.parent_id,
                                  restored_from=r.restored_from, clauses=_clauses(r), rules=len(r.english_rules),
                                  pass_pct=ev.get("pass_pct"), latest=i == 0))
    return out


def diff(adapter: EngineAdapter, a: PolicyRecord, b: PolicyRecord, budget: Budget) -> DiffResult:
    text = "".join(difflib.unified_diff(a.yog_source.splitlines(keepends=True), b.yog_source.splitlines(keepends=True),
                                        fromfile=a.id, tofile=b.id))
    added = sum(1 for ln in text.splitlines() if ln.startswith("+") and not ln.startswith("+++"))
    removed = sum(1 for ln in text.splitlines() if ln.startswith("-") and not ln.startswith("---"))
    probes = targeted_probes(shape(adapter.program_info(a.yog_source))) + targeted_probes(shape(adapter.program_info(b.yog_source)))
    seen: set = set()
    uniq = []
    for p in probes:
        k = (p[0], p[1], p[2], tuple(p[3]))
        if k not in seen:
            seen.add(k)
            uniq.append(p)
    flips: list[Flip] = []
    total = 0
    n = min(len(uniq), budget.room() // 2)                # the probes the budget allows (2 checks each)
    budget.spend(2 * n)
    ra = safe_check_many(adapter, a.yog_source, uniq[:n])
    rb = safe_check_many(adapter, b.yog_source, uniq[:n])
    try:
        for (actor, action, resource, ctx), x, y in zip(uniq[:n], ra, rb):
            da, db = x.decision, y.decision
            if da != db:
                total += 1
                if len(flips) < MAX_FLIPS:
                    flips.append(Flip(actor=actor, action=action, resource=resource, context=ctx, before=da, after=db))
    except BudgetExceeded:
        pass
    changed = sorted({f.action for f in flips})
    if not removed and not added:
        summary = "The two versions have the same text."
    elif total == 0:
        summary = f"The text changed ({added} lines added, {removed} removed) but none of the {len(uniq)} probe requests got a different answer."
    else:
        summary = f"{total} of {len(uniq)} probe requests get a different answer, in {', '.join(changed[:4])}."
    return DiffResult(a=a.id, b=b.id, text_diff=text, added=added, removed=removed, probes=len(uniq), flips=flips,
                      flips_total=total, changed_actions=changed, summary=summary)


class RestoreRequest(BaseModel):
    policy_id: str
    note: str = Field(default="", max_length=500)
