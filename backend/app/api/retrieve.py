from functools import lru_cache
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, Field

from app.core.guard import live_guard
from app.api.deps import get_llm
from app.llm.factory import get_provider, get_provider_for
from app.llm.provider import LLMError, LLMProvider
from app.rag.examples import PolicyExample, load_examples, load_retrieval_examples
from app.rag.retriever import Retrieved, Retriever

router = APIRouter()


Mode = Literal["real", "offline"]


@lru_cache(maxsize=8)
def retriever_for(provider: LLMProvider) -> Retriever:
    """One retriever (and one index file) per provider, so switching modes never rebuilds anything."""
    return Retriever(provider, load_retrieval_examples())


@lru_cache(maxsize=1)
def get_retriever() -> Retriever:
    return retriever_for(get_provider())


def resolve_mode(mode: Mode | None, provider: LLMProvider, retriever: Retriever,
                 request: Request) -> tuple[LLMProvider, Retriever]:
    """mode=None keeps the injected (server default) provider. An explicit mode picks it per request.
    Real mode needs a key and passes the live-AI guard (rate limit + daily budget); Offline is always available."""
    if mode is None:
        return provider, retriever
    try:
        chosen = get_provider_for(mode)
    except LLMError as e:
        raise HTTPException(status_code=409, detail=str(e))
    if mode == "real":
        live_guard(request)
    return chosen, retriever_for(chosen)


class RetrieveRequest(BaseModel):
    english: str = Field(max_length=2000)
    tools: list[str] = Field(default_factory=list, max_length=100)
    k: int = Field(default=3, ge=1, le=10)
    mode: Mode | None = None


class RetrieveResponse(BaseModel):
    results: list[Retrieved]
    floor: float | None = None            # relevance floor in force for this provider
    floor_calibrated: bool | None = None
    grounded: bool = True                 # at least one result clears the floor
    provider: str | None = None


@router.post("/retrieve", response_model=RetrieveResponse)
def retrieve(req: RetrieveRequest, request: Request, retriever: Retriever = Depends(get_retriever),
             provider: LLMProvider = Depends(get_llm)) -> RetrieveResponse:
    _, retriever = resolve_mode(req.mode, provider, retriever, request)
    try:
        results = retriever.search(req.english, req.tools, req.k)
    except LLMError as e:
        raise HTTPException(status_code=502, detail=str(e))
    info = retriever.floor_info() if hasattr(retriever, "floor_info") else {}
    return RetrieveResponse(results=results, floor=info.get("floor"), floor_calibrated=info.get("calibrated"),
                            grounded=any(r.relevant for r in results), provider=retriever.provider.name)


@router.get("/examples", response_model=list[PolicyExample])
def examples() -> list[PolicyExample]:
    return load_examples()
