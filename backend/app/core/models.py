"""Data contracts shared with the UI (CLAUDE.md section 9). Keep these stable."""
from typing import Literal

from pydantic import BaseModel, Field


class Param(BaseModel):
    name: str
    type_hint: str | None = None
    default: str | None = None


class Tool(BaseModel):
    name: str
    params: list[Param] = Field(default_factory=list)
    docstring: str | None = None
    source_line: int
    side_effect_hints: list[str] = Field(default_factory=list)


class RetrievedExample(BaseModel):
    """An example that was really put into the prompt, with its similarity score."""
    id: str
    english: str
    score: float
    source: str = "unknown"            # team | claude-draft | reviewed-by:<name> ...
    relevant: bool = True              # cleared the relevance floor; only relevant examples are put into the prompt
    lexical: float = 0.0               # keyword (BM25) score, 0..1 within the query
    rerank: float | None = None        # 0..10 from the optional LLM reranker


class AttemptLog(BaseModel):
    """What happened on one generate -> compile -> check round (shown live in the UI)."""
    n: int
    compiled: bool
    errors: list[str] = Field(default_factory=list)              # compiler / lint errors
    scenario_failures: list[str] = Field(default_factory=list)   # independent-check disagreements, in plain English
    yog_source: str = ""


class ScenarioSummary(BaseModel):
    total: int
    passed: int
    failures: list[str] = Field(default_factory=list)


class PolicyDraft(BaseModel):
    english_rules: list[str]
    yog_source: str
    retrieved_examples: list[str]      # example ids, shown in the UI
    attempts: int                      # validator retries used
    valid: bool                        # compiles and passes Studio's structural lint
    errors: list[str]
    # additive (older clients ignore them)
    retrieved: list[RetrievedExample] = Field(default_factory=list)
    attempt_log: list[AttemptLog] = Field(default_factory=list)
    verified: bool | None = None       # True/False = independent scenarios agree/disagree; None = no independent check ran
    scenario_summary: ScenarioSummary | None = None
    # grounding: did retrieval find anything close enough to learn from, and which examples did the model say it used?
    grounded: bool = True              # False = no retrieved example cleared the floor; the draft is the model's alone
    cited_examples: list[str] = Field(default_factory=list)       # ids the model cited AND that were really in the prompt
    citation_problems: list[str] = Field(default_factory=list)    # missing citation, or an id that was never retrieved
    floor: float | None = None
    floor_calibrated: bool | None = None
    reranked: bool = False


class DetectResult(BaseModel):
    kind: Literal["mcp_server", "function_calling_agent", "unknown"]
    confidence: float
    evidence: list[str]
    framework: str | None = None       # additive: langchain | openai_agents | crewai | pydantic_ai when one was recognised
