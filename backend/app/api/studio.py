"""HTTP API of the Studio tools (/studio/*). Every route works on a policy the visitor chose (an approved one, the demo, or
pasted text), validates it first, and caps how many engine checks it may spend. No route calls an LLM."""
import json

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import Response
from pydantic import BaseModel, Field

from app.api.deps import get_adapter
from app.api.device import get_audit
from app.api.policies import _max_policies, get_store
from app.core.config import EXAMPLES_DIR
from app.core.facts import FactError
from app.core.pyast import SourceError
from app.engine.adapter import EngineAdapter, EngineError
from app.modify.modifier import ModifyError
from app.evaluate.evaluator import evaluate
from app.explain.explainer import explain
from app.policies.store import PolicyRecord, PolicyStore
from app.studio import gaps as gaps_mod
from app.studio import mutation, pack, redteam, replay, scorecard, templates, versions
from app.studio.audit import AuditLog, to_csv
from app.studio.common import (DEMO_ID, Budget, BudgetExceeded, PolicyRef, ResolvedPolicy, budget_error, call_request,
                               policy_sha256, require_valid, resolve_policy, safe_check, shape)
from app.studio.pmap import MapRequest, MapResult, MapSuggest, build_map, suggest
from app.studio.why import WhyRequest, WhyResponse, explain_checked

router = APIRouter(prefix="/studio")
RUNTIME_PATH = pack.RUNTIME_PATH
SAMPLE_TRACE = EXAMPLES_DIR / "traces" / "smart_home_day.jsonl"


def _use(ref: PolicyRef, store: PolicyStore, adapter: EngineAdapter) -> ResolvedPolicy:
    p = resolve_policy(ref, store)
    require_valid(adapter, p.source)
    return p


# ----------------------------------------------------------------- Why-Explainer
@router.post("/why", response_model=WhyResponse)
def why(req: WhyRequest, adapter: EngineAdapter = Depends(get_adapter), store: PolicyStore = Depends(get_store)) -> WhyResponse:
    p = _use(req, store, adapter)
    try:
        res, ok = explain_checked(adapter, p.source, req.actor, req.action, req.resource, req.context)
    except EngineError as e:
        raise HTTPException(status_code=422, detail=str(e))
    return WhyResponse(policy_label=p.label, source=p.source, result=res, consistent=ok)


# ----------------------------------------------------------------- Policy Map
@router.post("/map/suggest", response_model=MapSuggest)
def map_suggest(ref: PolicyRef, adapter: EngineAdapter = Depends(get_adapter), store: PolicyStore = Depends(get_store)) -> MapSuggest:
    p = _use(ref, store, adapter)
    s = suggest(shape(adapter.program_info(p.source)))
    s.policy_label = p.label
    return s


@router.post("/map", response_model=MapResult)
def policy_map(req: MapRequest, adapter: EngineAdapter = Depends(get_adapter), store: PolicyStore = Depends(get_store)) -> MapResult:
    p = _use(req, store, adapter)
    try:
        out = build_map(adapter, p.source, req, Budget())
    except BudgetExceeded as e:
        raise budget_error(e)
    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e))
    out.policy_label = p.label
    return out


# ----------------------------------------------------------------- Gap Analyzer
class GapsRequest(PolicyRef):
    tools: list[str] = Field(default_factory=list, max_length=100)
    scenarios: list[mutation.TestCase] = Field(default_factory=list, max_length=150)


@router.post("/gaps", response_model=gaps_mod.GapReport)
def gaps(req: GapsRequest, adapter: EngineAdapter = Depends(get_adapter), store: PolicyStore = Depends(get_store)) -> gaps_mod.GapReport:
    p = _use(req, store, adapter)
    scen = [gaps_mod.Scenario(actor=s.actor, action=s.action, resource=s.resource, context=s.context, expected=s.expected) for s in req.scenarios]
    try:
        rep = gaps_mod.analyze(adapter, p.source, tools=[t for t in req.tools if t.strip()], scenarios=scen, budget=Budget(6000))
    except BudgetExceeded as e:
        raise budget_error(e)
    rep.policy_label, rep.source = p.label, p.source
    return rep


# ----------------------------------------------------------------- Red-Team
@router.post("/redteam", response_model=redteam.RedTeamReport)
def red_team(req: redteam.RedTeamRequest, adapter: EngineAdapter = Depends(get_adapter),
             store: PolicyStore = Depends(get_store)) -> redteam.RedTeamReport:
    p = _use(req, store, adapter)
    rep = redteam.run(adapter, p.source, shape(adapter.program_info(p.source)), req.invariants, Budget())
    rep.policy_label = p.label
    return rep


# ----------------------------------------------------------------- Test Strength
@router.post("/mutation", response_model=mutation.MutationReport)
def test_strength(req: mutation.MutationRequest, adapter: EngineAdapter = Depends(get_adapter),
                  store: PolicyStore = Depends(get_store)) -> mutation.MutationReport:
    p = _use(req, store, adapter)
    rep = mutation.run(adapter, p.source, shape(adapter.program_info(p.source)), req.scenarios, req.max_mutants, Budget(8000))
    rep.policy_label = p.label
    return rep


# ----------------------------------------------------------------- Templates
@router.get("/templates", response_model=list[templates.Template])
def list_templates() -> list[templates.Template]:
    return templates.load()


class CombineRequest(BaseModel):
    ids: list[str] = Field(max_length=templates.MAX_COMBINE)


@router.post("/templates/combine", response_model=templates.CombineResult)
def combine_templates(req: CombineRequest, adapter: EngineAdapter = Depends(get_adapter)) -> templates.CombineResult:
    return templates.combine(adapter, req.ids)


# ----------------------------------------------------------------- Version history
@router.get("/versions", response_model=list[versions.VersionSummary])
def list_versions(store: PolicyStore = Depends(get_store)) -> list[versions.VersionSummary]:
    return versions.summaries(store)


class DiffRequest(BaseModel):
    a: str
    b: str


@router.post("/versions/diff", response_model=versions.DiffResult)
def diff_versions(req: DiffRequest, adapter: EngineAdapter = Depends(get_adapter), store: PolicyStore = Depends(get_store)) -> versions.DiffResult:
    a, b = store.get(req.a), store.get(req.b)
    if a is None or b is None:
        raise HTTPException(status_code=404, detail="no such approved policy")
    return versions.diff(adapter, a, b, Budget(6000))


@router.post("/versions/restore", response_model=PolicyRecord)
def restore_version(req: versions.RestoreRequest, adapter: EngineAdapter = Depends(get_adapter),
                    store: PolicyStore = Depends(get_store)) -> PolicyRecord:
    """Restoring saves the old text as a NEW approved record (nothing is overwritten). The server validates and
    re-evaluates it exactly as it does for a normal approval."""
    old = store.get(req.policy_id)
    if old is None:
        raise HTTPException(status_code=404, detail="no such approved policy")
    if len(store.list()) >= _max_policies():
        raise HTTPException(status_code=409, detail="you have reached the limit of approved policies for this session")
    errors = adapter.validate(old.yog_source)
    if errors:
        raise HTTPException(status_code=422, detail="that version no longer compiles: " + "; ".join(errors[:2]))
    rep = evaluate(adapter, old.yog_source)
    latest = store.latest()
    return store.save(old.yog_source, english_rules=old.english_rules, retrieved_examples=old.retrieved_examples,
                      attempts=old.attempts, readback=old.readback, note=req.note or f"restored {old.id}",
                      parent_id=latest.id if latest else None, restored_from=old.id,
                      evaluation={"summary": rep.summary.model_dump(), "warnings": rep.warnings})


# ----------------------------------------------------------------- Audit log
@router.get("/audit")
def audit_list(limit: int = Query(200, ge=1, le=1000), decision: str | None = Query(None, max_length=20),
               tool: str | None = Query(None, max_length=100), q: str | None = Query(None, max_length=100),
               audit: AuditLog = Depends(get_audit)) -> dict:
    return {"entries": audit.read(limit, decision, tool, q), "total": audit.count()}


@router.get("/audit/verify")
def audit_verify(audit: AuditLog = Depends(get_audit)) -> dict:
    return audit.verify()


@router.get("/audit/export.csv")
def audit_csv(audit: AuditLog = Depends(get_audit)) -> Response:
    return Response(to_csv(list(reversed(audit.read(1000)))), media_type="text/csv",
                    headers={"Content-Disposition": 'attachment; filename="yog_audit_log.csv"'})


# ----------------------------------------------------------------- Trace Replay
@router.get("/replay/sample")
def replay_sample() -> dict:
    return {"filename": SAMPLE_TRACE.name, "format": "jsonl", "text": SAMPLE_TRACE.read_text(encoding="utf-8")}


@router.post("/replay", response_model=replay.ReplayResult)
def trace_replay(req: replay.ReplayRequest, adapter: EngineAdapter = Depends(get_adapter), store: PolicyStore = Depends(get_store),
                 audit: AuditLog = Depends(get_audit)) -> replay.ReplayResult:
    p = _use(req.policy, store, adapter)
    other = _use(req.compare, store, adapter) if req.compare is not None else None
    if req.format == "audit":
        text = "\n".join(json.dumps({"tool": e.get("tool"), "args": e.get("args", {}), "sim_hour": e.get("sim_hour", 12),
                                     "sim_day": e.get("sim_day", "mon")}) for e in reversed(audit.read(replay.MAX_ROWS)))
        rows, problems = replay.parse_rows(text, "jsonl")
    else:
        rows, problems = replay.parse_rows(req.text, req.format)
    if not rows:
        raise HTTPException(status_code=422, detail="; ".join(problems) or "there are no calls to replay")
    try:
        out, summary = replay.replay(adapter, p.source, other.source if other else None, rows, Budget(2 * replay.MAX_ROWS + 10))
    except BudgetExceeded as e:
        raise budget_error(e)
    return replay.ReplayResult(policy_label=p.label, other_label=other.label if other else None, rows=out, summary=summary,
                               problems=problems)


# ----------------------------------------------------------------- Runtime Guard
@router.get("/sdk/runtime")
def sdk_runtime() -> dict:
    src = RUNTIME_PATH.read_text(encoding="utf-8")
    return {"filename": "yog_runtime.py", "source": src, "lines": src.count("\n") + 1}


class TryCall(PolicyRef):
    tool: str = Field(max_length=100)
    args: dict = Field(default_factory=dict)
    hour: int = Field(default=12, ge=0, le=23)
    day: str = "mon"


class TryResult(BaseModel):
    policy_label: str
    decision: str
    reason: str
    action: str
    resource: str
    context: list[str]
    policy_sha256: str


@router.post("/sdk/try", response_model=TryResult)
def sdk_try(req: TryCall, adapter: EngineAdapter = Depends(get_adapter), store: PolicyStore = Depends(get_store)) -> TryResult:
    """What the runtime guard would answer for one call, using the same facts path the guard itself uses."""
    p = _use(req, store, adapter)
    if req.day.lower() not in ("mon", "tue", "wed", "thu", "fri", "sat", "sun"):
        raise HTTPException(status_code=422, detail="day must be mon..sun")
    try:
        actor, action, resource, ctx = call_request(req.tool, req.args, req.hour, req.day.lower())
    except FactError as e:                        # what the real guard does for a decimal or a path-like value
        return TryResult(policy_label=p.label, decision="DENY", reason=f"refused, failing closed: {e}", action="can_" + req.tool,
                         resource="", context=[], policy_sha256=policy_sha256(p.source))
    r = safe_check(adapter, p.source, actor, action, resource, ctx)
    return TryResult(policy_label=p.label, decision=r.decision, reason=r.reason, action=action, resource=resource, context=ctx,
                     policy_sha256=policy_sha256(p.source))


# ----------------------------------------------------------------- Export Pack
class ExportRequest(BaseModel):
    policy_id: str
    filename: str = Field(default="agent.py", max_length=100)
    source: str | None = Field(default=None, max_length=1_000_000)       # the agent, optional
    tools: list[str] = Field(default_factory=list, max_length=100)


@router.post("/export")
def export_pack(req: ExportRequest, adapter: EngineAdapter = Depends(get_adapter), store: PolicyStore = Depends(get_store)) -> Response:
    if req.policy_id == DEMO_ID:
        raise HTTPException(status_code=409, detail="the demo policy was not approved by you: approve a policy first")
    rec = store.get(req.policy_id)
    if rec is None:
        raise HTTPException(status_code=404, detail="no such approved policy: approve a policy first")
    try:
        data, manifest = pack.build(adapter, rec, agent_source=req.source, filename=req.filename, tools=req.tools)
    except (SourceError, ModifyError) as e:                  # the agent file is not usable (both are ValueErrors: catch them first)
        raise HTTPException(status_code=422, detail=str(e))
    except ValueError as e:                                  # the policy must not be exported (offline placeholder)
        raise HTTPException(status_code=409, detail=str(e))
    return Response(data, media_type="application/zip", headers={
        "Content-Disposition": f'attachment; filename="yog_export_{rec.id}.zip"', "X-Pack-Files": str(len(manifest["files"]))})


@router.post("/export/preview")
def export_preview(req: ExportRequest, store: PolicyStore = Depends(get_store)) -> dict:
    """What would be in the pack, and whether it can be built, without building it."""
    if req.policy_id == DEMO_ID:
        return {"ok": False, "reason": "the demo policy was not approved by you", "files": []}
    rec = store.get(req.policy_id)
    if rec is None:
        return {"ok": False, "reason": "no such approved policy", "files": []}
    if pack.PLACEHOLDER_MARKER in rec.yog_source:
        return {"ok": False, "reason": "this policy is still the offline placeholder", "files": []}
    files = ["policy.yog", "REPORT.html", "scenarios.json", "manifest.json"]
    if req.source:
        files += [req.filename, "yog_runtime.py", "yog.py", "README.txt"]
    return {"ok": True, "reason": "", "files": files, "policy_id": rec.id}


# ----------------------------------------------------------------- Scorecard
class ScorecardRequest(PolicyRef):
    tools: list[str] = Field(default_factory=list, max_length=100)
    include_strength: bool = True


@router.post("/scorecard", response_model=scorecard.Scorecard)
def get_scorecard(req: ScorecardRequest, adapter: EngineAdapter = Depends(get_adapter),
                  store: PolicyStore = Depends(get_store)) -> scorecard.Scorecard:
    p = _use(req, store, adapter)
    try:
        sc = scorecard.compute(adapter, p.source, [t for t in req.tools if t.strip()], req.include_strength)
    except BudgetExceeded as e:
        raise budget_error(e)
    sc.policy_label = p.label
    return sc


@router.get("/readback")
def readback(policy_id: str | None = Query(None, max_length=60), adapter: EngineAdapter = Depends(get_adapter),
             store: PolicyStore = Depends(get_store)) -> dict:
    p = _use(PolicyRef(policy_id=policy_id), store, adapter)
    return {"policy_label": p.label, "readback": explain(adapter, p.source).model_dump()}

