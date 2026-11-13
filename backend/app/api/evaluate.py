from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, Field

from app.api.deps import enforce_live_default, get_adapter, get_llm
from app.core.models import Tool
from app.engine.adapter import EngineAdapter, EngineError
from app.evaluate.evaluator import Report, evaluate
from app.evaluate.scenarios import Scenario
from app.llm.provider import LLMProvider

router = APIRouter()


class EvaluateRequest(BaseModel):
    # evaluate() runs one engine check per scenario plus the generated probes, so every list is capped (the same
    # figures the Studio tools use) and the policy is held to the common 200,000-character limit.
    yog_source: str = Field(max_length=200_000)
    english_rules: list[Annotated[str, Field(max_length=2000)]] = Field(default_factory=list, max_length=50)
    tools: list[Tool] = Field(default_factory=list, max_length=100)
    user_scenarios: list[Scenario] = Field(default_factory=list, max_length=200)
    use_llm: bool = True


@router.post("/evaluate", response_model=Report)
def evaluate_policy(req: EvaluateRequest, request: Request, adapter: EngineAdapter = Depends(get_adapter),
                    provider: LLMProvider = Depends(get_llm)) -> Report:
    if req.use_llm:
        enforce_live_default(provider, request)          # a live default provider spends quota here too
    try:
        return evaluate(adapter, req.yog_source, rules=req.english_rules, tools=req.tools,
                        user_scenarios=req.user_scenarios, provider=provider if req.use_llm else None)
    except EngineError as e:
        raise HTTPException(status_code=422, detail=str(e))
