"""Whole-system test: the demo script from CLAUDE.md section 12, end to end through the HTTP API."""
import io
import json
import os
import subprocess
import sys
import zipfile

from fastapi.testclient import TestClient

from app.api.deps import get_llm
from app.api.policies import get_store
from app.api.retrieve import get_retriever
from app.core.config import EXAMPLES_DIR
from app.llm.fake import FakeProvider
from app.main import app
from app.policies.store import PolicyStore
from app.rag.examples import load_examples
from app.rag.retriever import Retriever

POLICY = (EXAMPLES_DIR / "policies" / "demo_smart_home.yog").read_text(encoding="utf-8")
RULES = ["The agent may never unlock the door between 11pm and 6am.", "Thermostat must stay between 16 and 28 degrees."]
SCENARIOS = [
    {"actor": "agent", "action": "can_unlock_door", "resource": "front_door", "context": ["hour(now, 3)"], "expected": "DENY"},
    {"actor": "agent", "action": "can_unlock_door", "resource": "front_door", "context": ["hour(now, 14)"], "expected": "ALLOW"},
    {"actor": "agent", "action": "can_set_thermostat", "resource": "hall", "context": ["arg(set_thermostat, temperature, 30)"], "expected": "DENY"},
    {"actor": "agent", "action": "can_set_thermostat", "resource": "hall", "context": ["arg(set_thermostat, temperature, 20)"], "expected": "ALLOW"},
]


def test_full_demo_pipeline(tmp_path):
    store = PolicyStore(tmp_path / "policies")
    # Scripted LLM replies in call order: translate (1 reply), then scenario generation (1 reply).
    llm = FakeProvider(["```yog\n" + POLICY + "```", json.dumps(SCENARIOS)])
    app.dependency_overrides[get_store] = lambda: store
    app.dependency_overrides[get_llm] = lambda: llm
    app.dependency_overrides[get_retriever] = lambda: Retriever(FakeProvider(), load_examples(), tmp_path / "i.npz")
    try:
        c = TestClient(app)

        # 1-3  upload -> detector -> tools
        src = (EXAMPLES_DIR / "agents" / "smart_home_mcp.py").read_text(encoding="utf-8")
        a = c.post("/analyze", json={"filename": "smart_home_mcp.py", "source": src}).json()
        assert a["detect"]["kind"] == "mcp_server" and a["detect"]["confidence"] == 0.95
        names = [t["name"] for t in a["tools"]]
        assert {"unlock_door", "set_thermostat", "open_valve"} <= set(names)

        # 4-5  English rules -> retrieved examples -> draft (valid, within 3 attempts)
        d = c.post("/translate", json={"english_rules": RULES, "tools": a["tools"]}).json()
        assert d["valid"] and d["attempts"] == 1 and d["retrieved_examples"]

        # readback + (not yet live)
        ex = c.post("/explain", json={"yog_source": d["yog_source"]}).json()
        assert ex["valid"] and any("DENY" in cl["text"] for cl in ex["readback"]["clauses"])
        assert c.get("/policies").json() == []                               # nothing is live yet

        # 6  evaluation: independent scenarios all green
        rep = c.post("/evaluate", json={"yog_source": d["yog_source"], "english_rules": RULES, "tools": a["tools"]}).json()
        assert rep["summary"]["independent_total"] == 4 and rep["summary"]["all_green"] is True

        # approval gate: human click
        rec = c.post("/policies/approve", json={"yog_source": d["yog_source"], "english_rules": RULES,
                                                "retrieved_examples": d["retrieved_examples"], "attempts": d["attempts"]}).json()
        assert rec["id"] and rec["evaluation"]["summary"]["unconfirmed"] > 0
        assert len(c.get("/policies").json()) == 1

        # 7  diff + bundle
        m = c.post("/modify", json={"filename": "smart_home_mcp.py", "source": src}).json()
        assert m["removed_lines"] == 0 and len(m["guarded"]) == len(names)
        z = zipfile.ZipFile(io.BytesIO(c.post("/modify/bundle", json={
            "filename": "smart_home_mcp.py", "source": src, "policy_id": rec["id"]}).content))
        z.extractall(tmp_path / "bundle")

        # the patched agent, run for real (without the mcp package: a stub FastMCP is provided), blocks 3am
        stub = tmp_path / "bundle" / "mcp" / "server"
        stub.mkdir(parents=True)
        (tmp_path / "bundle" / "mcp" / "__init__.py").write_text("")
        (stub / "__init__.py").write_text("")
        (stub / "fastmcp.py").write_text(
            "class FastMCP:\n    def __init__(self, name): self.name=name\n"
            "    def tool(self, *a, **k):\n        return lambda f: f\n    def run(self): pass\n")
        code = ("import smart_home_mcp as m, yog_runtime\n"
                "for h in ('3','14'):\n"
                "    import os; os.environ['YOG_NOW']=h+',mon'\n"
                "    try:\n        print(h, m.unlock_door('front_door'))\n"
                "    except yog_runtime.YogDenied:\n        print(h, 'DENIED')\n")
        p = subprocess.run([sys.executable, "-I", "-c", "import sys; sys.path.insert(0,'.')\n" + code],
                           cwd=tmp_path / "bundle", capture_output=True, text=True, timeout=60,
                           env={k: v for k, v in os.environ.items() if k != "PYTHONPATH"})
        assert p.returncode == 0, p.stderr
        assert p.stdout.split("\n")[:2] == ["3 DENIED", "14 front_door unlocked"]

        # 8  device simulator: 3am unlock is blocked, door stays locked, reason shown
        c.post("/device/reset")
        c.post("/device/clock", json={"hour": 3, "day": "tue"})
        r = c.post("/device/command", json={"tool": "unlock_door", "args": {"door_id": "front_door"}}).json()
        assert r["decision"] == "DENY" and r["executed"] is False and "deny clause" in r["reason"]
        snap = c.get("/device/state").json()
        assert snap["state"]["doors"]["front_door"] == "locked" and snap["policy_id"] == rec["id"]
        c.post("/device/clock", json={"hour": 14, "day": "tue"})
        ok = c.post("/device/command", json={"tool": "unlock_door", "args": {"door_id": "front_door"}}).json()
        assert ok["decision"] == "ALLOW" and ok["executed"] is True
    finally:
        app.dependency_overrides.clear()


def test_device_and_bundle_refuse_without_approval(tmp_path):
    store = PolicyStore(tmp_path / "policies")
    app.dependency_overrides[get_store] = lambda: store
    try:
        c = TestClient(app)
        assert c.post("/device/command", json={"tool": "lock_door", "args": {"door_id": "front_door"}}).status_code == 409
        assert c.post("/modify/bundle", json={"source": "x", "policy_id": "p-20200101000000-deadbeef"}).status_code == 404
    finally:
        app.dependency_overrides.clear()


def test_draft_that_never_compiles_cannot_reach_the_device(tmp_path):
    store = PolicyStore(tmp_path / "policies")
    app.dependency_overrides[get_store] = lambda: store
    app.dependency_overrides[get_llm] = lambda: FakeProvider(["```yog\nallow broken(:\n```"] * 3)
    app.dependency_overrides[get_retriever] = lambda: Retriever(FakeProvider(), load_examples(), tmp_path / "i.npz")
    try:
        c = TestClient(app)
        d = c.post("/translate", json={"english_rules": RULES}).json()
        assert not d["valid"] and d["attempts"] == 3 and d["errors"]
        assert c.post("/policies/approve", json={"yog_source": d["yog_source"]}).status_code == 422
        assert c.post("/device/command", json={"tool": "lock_door", "args": {"door_id": "front_door"}}).status_code == 409
    finally:
        app.dependency_overrides.clear()
