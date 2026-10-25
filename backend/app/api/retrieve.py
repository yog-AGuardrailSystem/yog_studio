from functools import lru_cache

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from app.llm.factory import get_provider
from app.llm.provider import LLMError
from app.rag.examples import PolicyExample, load_examples
from app.rag.retriever import Retrieved, Retriever

router = APIRouter()


@lru_cache(maxsize=1)
def get_retriever() -> Retriever:
    return Retriever(get_provider())


class RetrieveRequest(BaseModel):
    english: str
    tools: list[str] = Field(default_factory=list)
    k: int = Field(default=3, ge=1, le=10)


class RetrieveResponse(BaseModel):
    results: list[Retrieved]


@router.post("/retrieve", response_model=RetrieveResponse)
def retrieve(req: RetrieveRequest, retriever: Retriever = Depends(get_retriever)) -> RetrieveResponse:
    try:
        return RetrieveResponse(results=retriever.search(req.english, req.tools, req.k))
    except LLMError as e:
        raise HTTPException(status_code=502, detail=str(e))


@router.get("/examples", response_model=list[PolicyExample])
def examples() -> list[PolicyExample]:
    return load_examples()
