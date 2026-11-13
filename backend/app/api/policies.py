import os
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, Field

from app.api.deps import get_adapter
from app.core import session
from app.engine.adapter import EngineAdapter, EngineError
from app.evaluate.evaluator import evaluate
from app.explain.explainer import Readback, explain
from app.policies.store import PolicyRecord, PolicyStore

router = APIRouter()


def get_store(request: Request) -> PolicyStore:
    """The visitor's OWN approved policies (see app/core/session.py): never another visitor's."""
    return PolicyStore(session.policies_dir(request))


def _max_policies() -> int:
    try:
        return int(os.getenv("MAX_POLICIES_PER_SESSION", "100"))
    except ValueError:
        return 100


class ExplainRequest(BaseModel):
    yog_source: str = Field(max_length=200_000)


class ExplainResponse(BaseModel):
    valid: bool
    errors: list[str]
    readback: Readback | None = None


@router.post("/explain", response_model=ExplainResponse)
def explain_policy(req: ExplainRequest, adapter: EngineAdapter = Depends(get_adapter)) -> ExplainResponse:
    """Validate + plain-English readback. Used for the Review screen and after every edit."""
    errors = adapter.validate(req.yog_source)
    if errors:
        return ExplainResponse(valid=False, errors=errors)
    return ExplainResponse(valid=True, errors=[], readback=explain(adapter, req.yog_source))


class ApproveRequest(BaseModel):
    # Every approval is written to disk twice (.yog and .json), so the sizes are capped like every other policy input
    # (200,000 characters, as /compile and the Studio tools): the count cap alone did not bound bytes.
    yog_source: str = Field(max_length=200_000)
    english_rules: list[Annotated[str, Field(max_length=2000)]] = Field(default_factory=list, max_length=50)
    retrieved_examples: list[Annotated[str, Field(max_length=200)]] = Field(default_factory=list, max_length=50)
    attempts: int = 0
    # A draft no stored example supported must be confirmed explicitly. This is a human-confirmation gate for the UI
    # (the review screen sends both), not an authentication boundary.
    grounded: bool = True
    ungrounded_confirmed: bool = False
    note: str = Field(default="", max_length=500)            # what changed (shown in Version History)


@router.post("/policies/approve", response_model=PolicyRecord)
def approve(req: ApproveRequest, adapter: EngineAdapter = Depends(get_adapter),
            store: PolicyStore = Depends(get_store)) -> PolicyRecord:
    """The human gate. The server re-validates -- the client's 'valid' flag is never trusted."""
    if not req.grounded and not req.ungrounded_confirmed:
        raise HTTPException(status_code=409, detail="this draft is not based on any stored example: confirm that you have read it line by line before approving")
    if len(store.list()) >= _max_policies():
        raise HTTPException(status_code=409, detail="you have reached the limit of approved policies for this session; they expire after a few days")
    errors = adapter.validate(req.yog_source)
    if errors:
        raise HTTPException(status_code=422, detail="cannot approve an invalid policy: " + "; ".join(errors))
    try:
        rb = explain(adapter, req.yog_source)
    except EngineError as e:
        raise HTTPException(status_code=422, detail=str(e))
    if not any(c.kind in ("allow", "deny") for c in rb.clauses):
        raise HTTPException(status_code=422, detail="cannot approve a policy with no allow/deny clause")
    # The server runs the (deterministic) evaluation itself on the exact text being approved; nothing the
    # client says about evaluation is trusted or stored.
    rep = evaluate(adapter, req.yog_source)
    evaluation = {"summary": rep.summary.model_dump(), "warnings": rep.warnings}
    previous = store.latest()
    return store.save(req.yog_source, english_rules=req.english_rules, retrieved_examples=req.retrieved_examples,
                      attempts=req.attempts, evaluation=evaluation, note=req.note,
                      parent_id=previous.id if previous else None,
                      readback=[f"line {c.line}: {c.text}" for c in rb.clauses])


class RejectRequest(BaseModel):
    reason: str = ""


@router.post("/policies/reject")
def reject(_: RejectRequest) -> dict:
    """Rejecting stores nothing: the draft simply never goes live."""
    return {"status": "rejected"}


@router.get("/policies", response_model=list[PolicyRecord])
def list_policies(store: PolicyStore = Depends(get_store)) -> list[PolicyRecord]:
    return store.list()


@router.get("/policies/{policy_id}", response_model=PolicyRecord)
def get_policy(policy_id: str, store: PolicyStore = Depends(get_store)) -> PolicyRecord:
    rec = store.get(policy_id)
    if rec is None:
        raise HTTPException(status_code=404, detail="no such approved policy")
    return rec
