from functools import lru_cache
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, Field, field_validator

from app.api.deps import get_adapter, get_llm
from app.api.retrieve import Mode, get_retriever, resolve_mode
from app.core.models import PolicyDraft, Tool
from app.engine.adapter import EngineAdapter
from app.llm.provider import LLMProvider
from app.rag.retriever import Retriever
from app.translate.jobs import JobStore, JobView
from app.translate.translator import translate

router = APIRouter()


MAX_RULE_CHARS = 2000          # the same bound /retrieve puts on one English rule
MAX_TOOL_TEXT = 2000           # a tool's docstring / parameter text; names and parameters are far shorter


def _bound_tool(t: Tool) -> Tool:
    """Prompts and embeddings are built from these strings and a live request is charged one budget unit however much
    text it carries, so the text is bounded before it can reach a provider."""
    return t.model_copy(update={
        "name": t.name[:200],
        "docstring": t.docstring[:MAX_TOOL_TEXT] if t.docstring else t.docstring,
        "params": [p.model_copy(update={"name": p.name[:200], "type_hint": (p.type_hint or "")[:200] or None,
                                        "default": (p.default or "")[:200] or None}) for p in t.params[:50]],
        "side_effect_hints": [h[:100] for h in t.side_effect_hints[:20]],
    })


class TranslateRequest(BaseModel):
    english_rules: list[Annotated[str, Field(max_length=MAX_RULE_CHARS)]] = Field(max_length=20)
    tools: list[Tool] = Field(default_factory=list, max_length=100)

    @field_validator("tools")
    @classmethod
    def _bounded_tools(cls, tools: list[Tool]) -> list[Tool]:
        return [_bound_tool(t) for t in tools]

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
