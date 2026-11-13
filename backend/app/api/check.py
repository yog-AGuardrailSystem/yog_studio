from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from app.api.deps import get_adapter
from app.engine.adapter import CheckResult, EngineAdapter, EngineError

router = APIRouter()


class CheckRequest(BaseModel):
    policy: str = Field(max_length=200_000)                  # same cap as /compile and the Studio tools
    actor: str = Field(max_length=200)
    action: str = Field(max_length=200)
    resource: str = Field(max_length=200)
    context: list[Annotated[str, Field(max_length=200)]] = Field(default_factory=list, max_length=60)


@router.post("/check", response_model=CheckResult)
def check(req: CheckRequest, adapter: EngineAdapter = Depends(get_adapter)) -> CheckResult:
    try:
        res = adapter.check(req.policy, req.actor, req.action, req.resource, req.context)
        res.trace = res.trace[:200]                      # a completed evaluation can leave a very long trace
        return res
    except EngineError as e:
        raise HTTPException(status_code=422, detail=str(e))
