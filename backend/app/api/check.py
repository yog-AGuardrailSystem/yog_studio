from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from app.api.deps import get_adapter
from app.engine.adapter import CheckResult, EngineAdapter, EngineError

router = APIRouter()


class CheckRequest(BaseModel):
    policy: str
    actor: str
    action: str
    resource: str
    context: list[str] = Field(default_factory=list)


@router.post("/check", response_model=CheckResult)
def check(req: CheckRequest, adapter: EngineAdapter = Depends(get_adapter)) -> CheckResult:
    try:
        return adapter.check(req.policy, req.actor, req.action, req.resource, req.context)
    except EngineError as e:
        raise HTTPException(status_code=422, detail=str(e))
