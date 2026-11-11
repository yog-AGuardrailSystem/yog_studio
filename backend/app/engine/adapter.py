from abc import ABC, abstractmethod
from typing import Literal

from pydantic import BaseModel, Field


class EngineError(Exception):
    """The policy failed to tokenize / parse / pass the semantic check."""


class CheckResult(BaseModel):
    decision: Literal["ALLOW", "DENY"]
    reason: str
    trace: list[str]


class Diagnostic(BaseModel):
    """One problem found while compiling. `message` is the engine's own text; `hint` explains it in plain English."""
    code: str                          # stable id, e.g. "undefined_predicate" (the UI keys fixes off this)
    severity: Literal["error", "warning"] = "error"
    line: int | None = None            # 1-based; the reference engine reports lines only (no columns)
    message: str
    hint: str | None = None
    suggestion: str | None = None      # e.g. "Did you mean role/2?"
    fix: dict | None = None            # machine-applicable edit when we are certain: {"line": n, "find": "=", "replace": "=="}


class TokenInfo(BaseModel):
    kind: str
    value: str | int | None = None
    line: int


class PredicateInfo(BaseModel):
    name: str
    arity: int
    role: Literal["fact", "rule", "decision"]
    clauses: int                       # facts or clauses that define it
    line: int | None = None


class CompileInfo(BaseModel):
    ok: bool                           # tokenizes, parses and passes the semantic check
    diagnostics: list[Diagnostic] = Field(default_factory=list)
    tokens: list[TokenInfo] = Field(default_factory=list)
    ast: dict | None = None            # {facts, clauses, queries}; present whenever it parsed
    predicates: list[PredicateInfo] = Field(default_factory=list)


class QuerySpec(BaseModel):
    """A `query` statement of a program, in source order."""
    line: int
    pred: str
    terms: list[dict]                  # [{"const": x} | {"var": "X"} | {"wildcard": true}]
    text: str                          # e.g. can_delete(a_agent, database_1)


class AskResult(BaseModel):
    """Answer to a plain (non-decision) query: does the goal hold, and with which bindings."""
    answer: bool
    bindings: list[dict] = Field(default_factory=list)
    trace: list[str] = Field(default_factory=list)


class WhyStep(BaseModel):
    """One condition of a clause body, with the values the engine had at that point."""
    text: str
    ok: bool | None                    # True held, False failed here, None never reached
    note: str = ""


class ClauseWhy(BaseModel):
    kind: Literal["allow", "deny"]
    line: int
    head: str
    status: Literal["matched", "failed", "head_mismatch", "error"]
    steps: list[WhyStep] = Field(default_factory=list)
    failed_at: int | None = None       # index into steps


class WhyResult(BaseModel):
    """The proof behind one decision: every allow/deny clause of the action, matched or not, and where it stopped."""
    decision: Literal["ALLOW", "DENY"]
    reason: str                        # the engine's own reason (same as check())
    verdict: str                       # plain English, built from the clause results
    winner_line: int | None = None
    clauses: list[ClauseWhy] = Field(default_factory=list)
    context: list[str] = Field(default_factory=list)
    error: bool = False                # engine error: failed closed, explanation incomplete


class EngineAdapter(ABC):
    """Everything Studio needs from a YOG engine. Swap implementations here only."""

    @abstractmethod
    def check(self, policy: str, actor: str, action: str, resource: str,
              context: list[str] | None = None) -> CheckResult:
        """Decide one request. `context` = extra per-request facts, e.g. 'hour(now, 3)'.
        Raises EngineError if the policy does not compile."""

    @abstractmethod
    def validate(self, policy: str) -> list[str]:
        """Return a list of compile errors (empty list = policy is valid)."""

    @abstractmethod
    def program_info(self, policy: str) -> dict:
        """Parsed structure for the explainer. Raises EngineError on bad policy."""

    # -- optional capabilities (the workbench's compiler explorer). Engines that cannot do these raise EngineError.
    def compile_info(self, policy: str) -> CompileInfo:
        raise EngineError("this engine cannot expose its compiler stages")

    def queries(self, policy: str) -> list[QuerySpec]:
        raise EngineError("this engine cannot list the queries of a program")

    def ask(self, policy: str, pred: str, terms: list[dict]) -> AskResult:
        raise EngineError("this engine cannot answer plain queries")

    def explain(self, policy: str, actor: str, action: str, resource: str,
                context: list[str] | None = None) -> WhyResult:
        raise EngineError("this engine cannot explain its decisions clause by clause")
