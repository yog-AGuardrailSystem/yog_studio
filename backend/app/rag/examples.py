"""Loads the English<->YOG example pairs from examples/policies/*.yaml (CLAUDE.md section 11 schema)."""
from typing import Literal

import yaml
from pydantic import BaseModel, Field

from app.core.config import EXAMPLES_DIR

POLICIES_DIR = EXAMPLES_DIR / "policies"


class ExampleScenario(BaseModel):
    actor: str
    action: str
    resource: str
    context: list[str] = Field(default_factory=list)
    expected: Literal["ALLOW", "DENY"]


class PolicyExample(BaseModel):
    id: str
    english: str
    tools_context: list[str] = Field(default_factory=list)
    gold_yog: str
    scenarios: list[ExampleScenario] = Field(default_factory=list)
    source: str = "unknown"


def load_examples(directory=POLICIES_DIR) -> list[PolicyExample]:
    out: list[PolicyExample] = []
    for path in sorted(directory.glob("*.yaml")):
        data = yaml.safe_load(path.read_text(encoding="utf-8")) or []
        out.extend(PolicyExample(**item) for item in data)
    ids = [e.id for e in out]
    dupes = {i for i in ids if ids.count(i) > 1}
    if dupes:
        raise ValueError(f"duplicate example ids: {sorted(dupes)}")
    return out
