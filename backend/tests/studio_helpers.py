"""Shared helpers for the Studio tool tests."""
from fastapi.testclient import TestClient

from app.core.config import EXAMPLES_DIR
from app.engine.python_prototype import PythonPrototypeAdapter
from app.main import app

DEMO_PATH = EXAMPLES_DIR / "policies" / "demo_smart_home.yog"
DEMO = DEMO_PATH.read_text(encoding="utf-8")
DEMO_TOOLS = ["unlock_door", "lock_door", "set_thermostat", "open_valve", "get_status"]
AGENTS = EXAMPLES_DIR / "agents"


def adapter() -> PythonPrototypeAdapter:
    return PythonPrototypeAdapter()


def client() -> TestClient:
    """A fresh visitor: its own cookie, so its own policies, device and audit log."""
    return TestClient(app)


def approve(c: TestClient, source: str = DEMO, **extra) -> dict:
    r = c.post("/policies/approve", json={"yog_source": source, "english_rules": ["a rule"], **extra})
    assert r.status_code == 200, r.text
    return r.json()
