"""Hostile or absurd input must produce a clean 4xx, never a 500, a hang, or a leak."""
import time

import pytest
from fastapi.testclient import TestClient

from app.main import app

client = TestClient(app, raise_server_exceptions=False)
MCP = "from mcp.server.fastmcp import FastMCP\nmcp = FastMCP('x')\n@mcp.tool()\ndef t(a: int):\n    pass\n"


def upload(text: str | bytes, name: str = "agent.py"):
    data = text.encode() if isinstance(text, str) else text
    return client.post("/analyze/upload", files={"file": (name, data, "text/x-python")})


ANALYZE_CASES = [
    ("very long attribute chain", MCP + "x = a" + ".b" * 6000 + "\n"),
    ("deeply nested brackets", MCP + "x = " + "[" * 150 + "]" * 150 + "\n"),
    ("huge nested dict literal", MCP + "TOOLS = " + "{'a': " * 90 + "1" + "}" * 90 + "\n"),
    ("long decorator chain", MCP.replace("@mcp.tool()", "@mcp" + ".tool" * 3000 + "()")),
    ("null bytes", "x = 1\x00\n"),
    ("only a BOM", "﻿"),
    ("empty file", ""),
    ("tabs and form feeds", "def f():\n\tpass\n\x0c\n"),
    ("unicode identifiers", "def ünïcode_ツール(): pass\n"),
]


@pytest.mark.parametrize("label,source", ANALYZE_CASES, ids=[c[0] for c in ANALYZE_CASES])
def test_analyze_never_crashes(label, source):
    r = upload(source)
    assert r.status_code in (200, 422), (label, r.status_code, r.text[:200])


def test_non_utf8_bytes_are_rejected_cleanly():
    r = upload(b"\xff\xfe\x00bad")
    assert r.status_code == 422 and "UTF-8" in r.json()["detail"]


def test_a_file_over_the_limit_is_refused_before_analysis():
    r = upload("x = 1\n" * 300_000)                       # ~1.8 MB: over both the body cap and the file cap
    assert r.status_code in (413, 422)


def test_analysis_of_a_big_but_legal_file_is_fast():
    big = MCP + "".join(f"def f{i}(a, b):\n    return a + b\n" for i in range(8000))     # ~250 KB
    t = time.time()
    r = upload(big)
    assert r.status_code == 200 and time.time() - t < 10


COMPILE_CASES = [
    "fact a(b)\n" * 20000,                                                         # many clauses
    "allow can_x(U, R):\n" + "    role(U, admin)\n" * 20000,                       # one huge body
    "fact a(" + "b, " * 50000 + "c)\n",                                             # absurd arity
    "\x00\x01\x02",
    "rule r(X):\n" + "    " * 10 + "x\n",
    "é" * 5000,
]


@pytest.mark.parametrize("source", COMPILE_CASES, ids=[f"case{i}" for i in range(len(COMPILE_CASES))])
def test_compile_and_run_survive_absurd_programs(source):
    t = time.time()
    c = client.post("/compile", json={"source": source})
    r = client.post("/run", json={"source": source})
    assert c.status_code in (200, 413, 422) and r.status_code in (200, 413, 422), (c.status_code, r.status_code)
    assert time.time() - t < 20


def test_an_oversized_yog_source_is_refused():
    r = client.post("/compile", json={"source": "x" * 300_000})
    assert r.status_code == 422


def test_unhandled_errors_return_a_request_id_and_no_internals(monkeypatch):
    import app.api.compile as mod

    def boom(*a, **k):
        raise RuntimeError("secret internal detail /home/user/app.py")
    monkeypatch.setattr(mod, "compile_source", boom, raising=False)
    monkeypatch.setattr("app.engine.python_prototype.PythonPrototypeAdapter.compile_info", boom)
    r = client.post("/compile", json={"source": "fact a(b)\n"})
    assert r.status_code == 500
    body = r.json()
    assert body["detail"] == "Something went wrong on the server." and body["request_id"]
    assert "secret" not in r.text and "app.py" not in r.text
    assert r.headers["x-request-id"] == body["request_id"]


def test_dotted_handles_chains_far_beyond_the_recursion_limit():
    import ast
    from app.core.pyast import dotted
    chain = "a" + ".b" * 5000
    assert dotted(ast.parse(chain, mode="eval").body) == chain
    assert dotted(ast.parse("f().x.y", mode="eval").body) is None          # not a plain dotted name
    assert dotted(ast.parse("x", mode="eval").body) == "x"


def test_request_ids_and_a_status_endpoint():
    r = client.get("/health")
    assert len(r.headers["x-request-id"]) == 12
    s = client.get("/status").json()
    assert s["status"] == "ok" and s["engine_ok"] is True and "counters" not in s and "live_budget" not in s   # public view is minimal
    import os
    os.environ["STATUS_TOKEN"] = "s3cret"
    try:
        assert "counters" not in client.get("/status", headers={"x-status-token": "wrong"}).json()
        full = client.get("/status", headers={"x-status-token": "s3cret"}).json()
        assert full["counters"]["requests"] >= 1 and "live_budget" in full and "key" not in str(full).lower().replace("api key", "")
    finally:
        del os.environ["STATUS_TOKEN"]


def test_validation_errors_do_not_echo_the_request_body():
    r = client.post("/compile", json={"source": 5, "secret_field": "hunter2"})
    assert r.status_code == 422 and "hunter2" not in r.text and "input" not in r.text
