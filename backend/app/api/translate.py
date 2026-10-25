from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field

from app.api.deps import get_adapter, get_llm
from app.api.retrieve import get_retriever
from app.core.models import PolicyDraft, Tool
from app.engine.adapter import EngineAdapter
from app.llm.provider import LLMProvider
from app.rag.retriever import Retriever
from app.translate.translator import translate

router = APIRouter()


class TranslateRequest(BaseModel):
    english_rules: list[str]
    tools: list[Tool] = Field(default_factory=list)


@router.post("/translate", response_model=PolicyDraft)
def translate_rules(req: TranslateRequest, adapter: EngineAdapter = Depends(get_adapter),
                    retriever: Retriever = Depends(get_retriever),
                    provider: LLMProvider = Depends(get_llm)) -> PolicyDraft:
    """Draft only. Nothing here makes a policy live -- see /policies/approve."""
    return translate(req.english_rules, req.tools, provider, retriever, adapter)
