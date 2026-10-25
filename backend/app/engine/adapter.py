from abc import ABC, abstractmethod
from typing import Literal

from pydantic import BaseModel


class EngineError(Exception):
    """The policy failed to tokenize / parse / pass the semantic check."""


class CheckResult(BaseModel):
    decision: Literal["ALLOW", "DENY"]
    reason: str
    trace: list[str]


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
