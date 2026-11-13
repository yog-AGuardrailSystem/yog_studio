"""Why-Explainer: the proof behind one decision, checked against the engine's own answer."""
from typing import Annotated

from pydantic import BaseModel, Field

from app.engine.adapter import EngineAdapter, WhyResult
from app.studio.common import PolicyRef


class WhyRequest(PolicyRef):
    actor: str = Field(max_length=200)
    action: str = Field(max_length=200)
    resource: str = Field(max_length=200)
    context: list[Annotated[str, Field(max_length=200)]] = Field(default_factory=list, max_length=60)


class WhyResponse(BaseModel):
    policy_label: str
    source: str
    result: WhyResult
    consistent: bool                     # False: the explanation disagreed with check() and was withheld


def explain_checked(adapter: EngineAdapter, source: str, actor: str, action: str, resource: str,
                    context: list[str]) -> tuple[WhyResult, bool]:
    """Explain a decision, then compare the verdict with adapter.check(). The engine's answer always wins: if the two
    ever disagree the page shows check()'s decision and says the explanation is unavailable."""
    res = adapter.explain(source, actor, action, resource, context)
    chk = adapter.check(source, actor, action, resource, context)
    if chk.decision != res.decision:
        return WhyResult(decision=chk.decision, reason=chk.reason, error=True, context=context,
                         verdict=f"{chk.decision}: {chk.reason}. The clause-by-clause explanation did not agree with "
                                 "the engine, so it is hidden."), False
    return res, True
