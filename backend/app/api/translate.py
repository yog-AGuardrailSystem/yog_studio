from functools import lru_cache

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, Field

from app.api.deps import get_adapter, get_llm
from app.api.retrieve import Mode, get_retriever, resolve_mode
from app.core.models import PolicyDraft, Tool
from app.engine.adapter import EngineAdapter
from app.llm.provider import LLMProvider
from app.rag.retriever import Retriever
from app.translate.jobs import JobStore, JobView
from app.translate.translator import translate

router = APIRouter()


class TranslateRequest(BaseModel):
    english_rules: list[str] = Field(max_length=20)
    tools: list[Tool] = Field(default_factory=list, max_length=100)
    mode: Mode | None = None            # None = the server default; 'real' | 'offline' = per-request Real LLM / Offline switch
    rerank: bool = False                # optional LLM reranker (real mode only)
    # None = automatic: check the draft against independent scenarios whenever a real LLM is configured.
    # With the offline fake there is no independent oracle, so nothing would be checked.
    verify: bool | None = None


@lru_cache(maxsize=1)
def get_jobs() -> JobStore:
    return JobStore()


def _verify(req: TranslateRequest, provider: LLMProvider) -> bool:
    return provider.name != "fake" if req.verify is None else req.verify


@router.post("/translate", response_model=PolicyDraft)
def translate_rules(req: TranslateRequest, request: Request, adapter: EngineAdapter = Depends(get_adapter),
                    retriever: Retriever = Depends(get_retriever),
                    provider: LLMProvider = Depends(get_llm)) -> PolicyDraft:
    """Draft only. Nothing here makes a policy live -- see /policies/approve."""
    provider, retriever = resolve_mode(req.mode, provider, retriever, request)
    return translate(req.english_rules, req.tools, provider, retriever, adapter, verify=_verify(req, provider),
                     rerank=req.rerank)


class StartResponse(BaseModel):
    job_id: str


@router.post("/translate/start", response_model=StartResponse)
def start_translation(req: TranslateRequest, request: Request, adapter: EngineAdapter = Depends(get_adapter),
                      retriever: Retriever = Depends(get_retriever), provider: LLMProvider = Depends(get_llm),
                      jobs: JobStore = Depends(get_jobs)) -> StartResponse:
    """Same as /translate, but returns at once; poll /translate/{job_id} for live progress."""
    provider, retriever = resolve_mode(req.mode, provider, retriever, request)
    verify = _verify(req, provider)

    def run(emit, cancelled):
        return translate(req.english_rules, req.tools, provider, retriever, adapter, verify=verify,
                         rerank=req.rerank, on_event=emit, should_cancel=cancelled)
    return StartResponse(job_id=jobs.start(run))


@router.get("/translate/{job_id}", response_model=JobView)
def poll_translation(job_id: str, since: int = 0, jobs: JobStore = Depends(get_jobs)) -> JobView:
    view = jobs.view(job_id, since)
    if view is None:
        raise HTTPException(status_code=404, detail="no such translation job (it may have expired)")
    return view


@router.post("/translate/{job_id}/cancel")
def cancel_translation(job_id: str, jobs: JobStore = Depends(get_jobs)) -> dict:
    if not jobs.cancel(job_id):
        raise HTTPException(status_code=404, detail="no such translation job (it may have expired)")
    return {"cancelled": True}
