from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app.api.analyze import analyze_source
from app.core.pyast import SourceError
from app.main import app

AGENTS = Path(__file__).resolve().parents[2] / "examples" / "agents"
client = TestClient(app)


def load(name: str):
    return analyze_source(name, (AGENTS / name).read_text(encoding="utf-8"))


# name -> (kind, confidence, {tool: hints})
EXPECTED = {
    "smart_home_mcp.py": ("mcp_server", 0.95, {
        "unlock_door": ["actuates"], "lock_door": ["actuates"], "set_thermostat": ["actuates"],
        "open_valve": ["actuates"], "get_status": []}),
    "file_ops_mcp.py": ("mcp_server", 0.95, {
        "read_file": ["filesystem"], "write_file": ["filesystem"],
        "delete_file": ["deletes", "filesystem"], "list_directory": ["filesystem"]}),
    "db_admin_mcp.py": ("mcp_server", 0.95, {
        "run_query": ["database"], "drop_table": ["deletes", "database"],
        "backup_database": ["filesystem", "database"]}),
    "finance_mcp.py": ("mcp_server", 0.95, {
        "transfer_funds": ["financial"], "get_balance": [], "send_receipt_email": ["network"]}),
    "openai_tools_agent.py": ("function_calling_agent", 1.0, {
        "delete_user_data": ["deletes"], "send_email": ["network"]}),
}


@pytest.mark.parametrize("name", list(EXPECTED))
def test_sample_detected_and_tools_extracted(name):
    kind, conf, tools = EXPECTED[name]
    r = load(name)
    assert r.detect.kind == kind
    assert r.detect.confidence == conf
    assert r.detect.evidence and all(e.startswith("line ") for e in r.detect.evidence)
    assert {t.name: t.side_effect_hints for t in r.tools} == tools
    assert r.candidates == []


def test_unknown_file_never_guesses():
    r = load("not_an_agent.py")
    assert r.detect.kind == "unknown" and r.detect.confidence == 0.0
    assert r.tools == []
    assert [c.name for c in r.candidates] == ["fibonacci", "celsius_to_fahrenheit", "slow_double"]


def test_smart_home_params_docstrings_and_lines():
    r = load("smart_home_mcp.py")
    t = {x.name: x for x in r.tools}
    unlock = t["unlock_door"]
    assert [(p.name, p.type_hint, p.default) for p in unlock.params] == [
        ("door_id", "str", None), ("pin", "str | None", "None")]
    assert unlock.docstring == "Unlock a door. Optionally supply a PIN."
    src = (AGENTS / "smart_home_mcp.py").read_text(encoding="utf-8").splitlines()
    assert src[unlock.source_line - 1].startswith("def unlock_door")
    assert [(p.name, p.default) for p in t["open_valve"].params] == [("valve_id", None), ("percent", "100")]


def test_decorator_rename_and_bare_decorator():
    r = load("file_ops_mcp.py")
    names = [t.name for t in r.tools]
    assert "list_directory" in names and "ls_dir" not in names
    assert "read_file" in names                       # bare `@mcp.tool`


def test_function_calling_params_from_schema():
    r = load("openai_tools_agent.py")
    t = {x.name: x for x in r.tools}
    assert [(p.name, p.type_hint) for p in t["delete_user_data"].params] == [
        ("user_id", "string"), ("hard_delete", "boolean")]
    assert t["send_email"].docstring == "Send an email to a recipient."
    assert any("delete_user_data" in e for e in r.detect.evidence)


def test_client_class_is_not_mistaken_for_server():
    src = "from mcp import ClientSession\nsession = ClientSession(None, None)\n\ndef f(x):\n    return x\n"
    r = analyze_source("c.py", src)
    assert r.detect.kind == "unknown"


def test_tool_decorator_without_mcp_import_is_not_enough():
    src = "def tool(f):\n    return f\n\nclass X:\n    tool = staticmethod(tool)\n\nx = X()\n\n@x.tool()\ndef f(a):\n    return a\n"
    assert analyze_source("x.py", src).detect.kind == "unknown"


def test_syntax_error_raises_and_api_422():
    with pytest.raises(SourceError):
        analyze_source("bad.py", "def (:\n")
    r = client.post("/analyze", json={"filename": "bad.py", "source": "def (:\n"})
    assert r.status_code == 422 and "not valid Python" in r.json()["detail"]


def test_uploaded_code_is_never_executed(tmp_path):
    marker = tmp_path / "pwned.txt"
    src = (
        "from mcp.server.fastmcp import FastMCP\n"
        f"open({str(marker)!r}, 'w').write('x')\n"
        "mcp = FastMCP('evil')\n\n"
        "@mcp.tool()\n"
        "def t(a: int) -> int:\n"
        "    raise SystemExit(1)\n"
    )
    r = client.post("/analyze", json={"filename": "evil.py", "source": src})
    assert r.status_code == 200
    assert r.json()["detect"]["kind"] == "mcp_server" and [t["name"] for t in r.json()["tools"]] == ["t"]
    assert not marker.exists()


def test_upload_endpoint():
    p = AGENTS / "smart_home_mcp.py"
    r = client.post("/analyze/upload", files={"file": (p.name, p.read_bytes(), "text/x-python")})
    assert r.status_code == 200
    j = r.json()
    assert j["filename"] == "smart_home_mcp.py" and j["detect"]["kind"] == "mcp_server" and len(j["tools"]) == 5


def test_upload_rejects_non_utf8():
    r = client.post("/analyze/upload", files={"file": ("x.py", b"\xff\xfe\x00bad", "text/plain")})
    assert r.status_code == 422


def test_async_and_kwonly_params():
    src = ("from mcp.server.fastmcp import FastMCP\nmcp = FastMCP('x')\n\n@mcp.tool()\n"
           "async def go(a, /, b: int = 2, *, c: str = 'z', **kw):\n    pass\n")
    t = analyze_source("a.py", src).tools[0]
    assert [(p.name, p.default) for p in t.params] == [("a", None), ("b", "2"), ("c", "'z'")]
