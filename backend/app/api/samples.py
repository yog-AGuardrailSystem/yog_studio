"""Serves the bundled example agents / demo policy so the demo works without a file dialog."""
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from app.core.config import EXAMPLES_DIR

router = APIRouter(prefix="/samples")
AGENTS_DIR = EXAMPLES_DIR / "agents"
DEMO_POLICY = EXAMPLES_DIR / "policies" / "demo_smart_home.yog"

DEMO_RULES = [
    "The agent may never unlock the door between 11pm and 6am.",
    "Thermostat must stay between 16 and 28 degrees.",
    "The agent may not open a valve more than 50 percent.",
]


def _names() -> list[str]:
    return sorted(p.name for p in AGENTS_DIR.glob("*.py"))


@router.get("/agents")
def list_agents() -> list[str]:
    return _names()


@router.get("/agents/{name}")
def get_agent(name: str) -> dict:
    if name not in _names():            # whitelist lookup: no path traversal possible
        raise HTTPException(status_code=404, detail="no such sample")
    return {"filename": name, "source": (AGENTS_DIR / name).read_text(encoding="utf-8")}


class DemoPolicy(BaseModel):
    yog_source: str
    english_rules: list[str]
    note: str


@router.get("/demo-policy", response_model=DemoPolicy)
def demo_policy() -> DemoPolicy:
    """A hand-written policy for the smart-home demo. Clearly labelled: it is NOT produced by the translator."""
    return DemoPolicy(yog_source=DEMO_POLICY.read_text(encoding="utf-8"), english_rules=DEMO_RULES,
                      note="Prepared demo policy (hand-written, not LLM generated)")
