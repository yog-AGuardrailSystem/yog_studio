from functools import lru_cache

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from app.api.deps import get_adapter
from app.engine.adapter import EngineAdapter, EngineError
from app.explain.explainer import Readback, explain
from app.policies.store import PolicyRecord, PolicyStore

router = APIRouter()


@lru_cache(maxsize=1)
def get_store() -> PolicyStore:
    return PolicyStore()


class ExplainRequest(BaseModel):
    yog_source: str


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
    yog_source: str
    english_rules: list[str] = Field(default_factory=list)
    retrieved_examples: list[str] = Field(default_factory=list)
    attempts: int = 0
    evaluation: dict | None = None


@router.post("/policies/approve", response_model=PolicyRecord)
def approve(req: ApproveRequest, adapter: EngineAdapter = Depends(get_adapter),
            store: PolicyStore = Depends(get_store)) -> PolicyRecord:
    """The human gate. The server re-validates -- the client's 'valid' flag is never trusted."""
    errors = adapter.validate(req.yog_source)
    if errors:
        raise HTTPException(status_code=422, detail="cannot approve an invalid policy: " + "; ".join(errors))
    try:
        rb = explain(adapter, req.yog_source)
    except EngineError as e:
        raise HTTPException(status_code=422, detail=str(e))
    if not any(c.kind in ("allow", "deny") for c in rb.clauses):
        raise HTTPException(status_code=422, detail="cannot approve a policy with no allow/deny clause")
    return store.save(req.yog_source, english_rules=req.english_rules, retrieved_examples=req.retrieved_examples,
                      attempts=req.attempts, evaluation=req.evaluation,
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
