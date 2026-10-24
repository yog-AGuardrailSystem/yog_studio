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


class DetectResult(BaseModel):
    kind: Literal["mcp_server", "function_calling_agent", "unknown"]
    confidence: float
    evidence: list[str]
