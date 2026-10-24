"""Serves the bundled example agents so the demo works without a file dialog."""
from fastapi import APIRouter, HTTPException

from app.core.config import EXAMPLES_DIR

router = APIRouter(prefix="/samples")
AGENTS_DIR = EXAMPLES_DIR / "agents"


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
