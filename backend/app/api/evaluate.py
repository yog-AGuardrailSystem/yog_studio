from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from app.api.deps import get_adapter, get_llm
from app.core.models import Tool
from app.engine.adapter import EngineAdapter, EngineError
from app.evaluate.evaluator import Report, evaluate
from app.evaluate.scenarios import Scenario
from app.llm.provider import LLMProvider

router = APIRouter()


class EvaluateRequest(BaseModel):
    yog_source: str
    english_rules: list[str] = Field(default_factory=list)
    tools: list[Tool] = Field(default_factory=list)
    user_scenarios: list[Scenario] = Field(default_factory=list)
    use_llm: bool = True


@router.post("/evaluate", response_model=Report)
def evaluate_policy(req: EvaluateRequest, adapter: EngineAdapter = Depends(get_adapter),
                    provider: LLMProvider = Depends(get_llm)) -> Report:
    try:
        return evaluate(adapter, req.yog_source, rules=req.english_rules, tools=req.tools,
                        user_scenarios=req.user_scenarios, provider=provider if req.use_llm else None)
    except EngineError as e:
        raise HTTPException(status_code=422, detail=str(e))
