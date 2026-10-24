import ast
import asyncio
import importlib
import io
import os
import re
import subprocess
import sys
import zipfile
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app.api.analyze import analyze_source
from app.api.policies import get_store
from app.core import facts
from app.core.config import ENGINE_PATH, EXAMPLES_DIR
from app.main import app
from app.modify.modifier import ModifyError, modify
from app.policies.store import PolicyStore
from app.rag.examples import load_examples

AGENTS = EXAMPLES_DIR / "agents"
RUNTIME = Path(__file__).resolve().parents[1] / "app" / "modify" / "yog_runtime.py"
NIGHT = next(e for e in load_examples() if e.id == "sh-night-lock").gold_yog
SAMPLES = ["smart_home_mcp.py", "file_ops_mcp.py", "db_admin_mcp.py", "finance_mcp.py", "openai_tools_agent.py"]


def src(name):
    return (AGENTS / name).read_text(encoding="utf-8")


@pytest.mark.parametrize("name", SAMPLES)
def test_minimal_diff_only_insertions_and_still_analyses_the_same(name):
    original = src(name)
    r = modify(original, filename=name)
    assert r.removed_lines == 0                                   # never rewrites a line
    assert r.added_lines == len(r.guarded) + 1                   # one decorator per tool + one import
    ast.parse(r.patched_source)
    before, after = analyze_source(name, original), analyze_source(name, r.patched_source)
    assert [t.name for t in before.tools] == [t.name for t in after.tools] == r.guarded
    assert before.detect.kind == after.detect.kind
    # the original lines survive in order
    patched_lines = iter(r.patched_source.splitlines())
    assert all(any(l == p for p in patched_lines) for l in original.splitlines())


def test_decorator_sits_directly_above_def_innermost():
    r = modify(src("smart_home_mcp.py"))
    lines = r.patched_source.splitlines()
    for i, l in enumerate(lines):
        if l.startswith("@yog_guard"):
            assert lines[i + 1].lstrip().startswith(("def ", "async def "))
            assert lines[i - 1].startswith("@mcp.tool")


def test_import_after_docstring_and_future_import():
    s = '"""doc"""\nfrom __future__ import annotations\nfrom mcp.server.fastmcp import FastMCP\nmcp = FastMCP("x")\n\n@mcp.tool()\ndef f(a: int): return a\n'
    r = modify(s)
    lines = r.patched_source.splitlines()
    assert lines[:3] == ['"""doc"""', "from __future__ import annotations", "from yog_runtime import yog_guard"]
    ast.parse(r.patched_source)


def test_shebang_and_no_docstring():
    s = '#!/usr/bin/env python\nfrom mcp.server.fastmcp import FastMCP\nmcp = FastMCP("x")\n\n@mcp.tool()\ndef f(a): return a\n'
    r = modify(s)
    assert r.patched_source.splitlines()[:2] == ["#!/usr/bin/env python", "from yog_runtime import yog_guard"]


def test_crlf_preserved_and_no_trailing_newline():
    s = 'from mcp.server.fastmcp import FastMCP\r\nmcp = FastMCP("x")\r\n\r\n@mcp.tool()\r\ndef f(a): return a'
    r = modify(s)
    assert "\n" not in r.patched_source.replace("\r\n", "")        # every newline is CRLF
    assert r.patched_source.endswith("return a")
    assert r.removed_lines == 0


def test_methods_in_classes_keep_indentation():
    s = ('from mcp.server.fastmcp import FastMCP\nmcp = FastMCP("x")\n\nclass A:\n    @mcp.tool()\n'
         '    def go(self, a: int):\n        return a\n')
    r = modify(s)
    assert '    @yog_guard("go")\n    def go' in r.patched_source
    ast.parse(r.patched_source)


def test_idempotent():
    once = modify(src("smart_home_mcp.py"))
    twice = modify(once.patched_source)
    assert twice.guarded == [] and sorted(twice.already_guarded) == sorted(once.guarded)
    assert twice.patched_source == once.patched_source


def test_only_subset_and_unknown_names():
    r = modify(src("smart_home_mcp.py"), only=["unlock_door", "nope"])
    assert r.guarded == ["unlock_door"] and any("nope" in s for s in r.skipped)


def test_renamed_tool_uses_registered_name():
    r = modify(src("file_ops_mcp.py"))
    assert '@yog_guard("list_directory")' in r.patched_source and "ls_dir" not in "".join(r.guarded)


def test_function_calling_missing_implementation_is_reported():
    s = ('from openai import OpenAI\nTOOLS=[{"type":"function","function":{"name":"ghost","description":"d",'
         '"parameters":{"type":"object","properties":{}}}}]\nc=OpenAI()\nc.chat.completions.create(model="m",messages=[],tools=TOOLS)\n')
    r = modify(s)
    assert r.guarded == [] and any("ghost" in x for x in r.skipped)


def test_unknown_file_refused():
    with pytest.raises(ModifyError):
        modify(src("not_an_agent.py"))


# ---------------------------------------------------------------- runtime

def test_runtime_is_standalone():
    tree = ast.parse(RUNTIME.read_text(encoding="utf-8"))
    mods = {n.module.split(".")[0] for n in ast.walk(tree) if isinstance(n, ast.ImportFrom) and n.module}
    mods |= {a.name.split(".")[0] for n in ast.walk(tree) if isinstance(n, ast.Import) for a in n.names}
    assert "app" not in mods


def test_runtime_normalisation_equals_studio_normalisation():
    rt = importlib.util.spec_from_file_location("rt_copy", RUNTIME)
    m = importlib.util.module_from_spec(rt)
    rt.loader.exec_module(m)
    for args in ({"temperature": 21.5, "zone": "Living Room", "on": True, "x": None, "n": [1, 2]}, {"a": "USD"}, {}):
        assert m.facts_from_call("Set_T", args, 27, "Sat") == facts.facts_from_call("Set_T", args, 27, "Sat")


@pytest.fixture()
def bundle_dir(tmp_path):
    (tmp_path / "yog.py").write_text(ENGINE_PATH.read_text(encoding="utf-8"), encoding="utf-8")
    (tmp_path / "yog_runtime.py").write_text(RUNTIME.read_text(encoding="utf-8"), encoding="utf-8")
    (tmp_path / "policy.yog").write_text(NIGHT, encoding="utf-8")
    return tmp_path


def run_in(dir_: Path, code: str, now: str):
    env = {**os.environ, "YOG_NOW": now}
    env.pop("PYTHONPATH", None)
    p = subprocess.run([sys.executable, "-I", "-c", "import sys; sys.path.insert(0, %r)\n" % str(dir_) + code],
                       capture_output=True, text=True, cwd=dir_, env=env, timeout=30)
    return p.returncode, p.stdout.strip(), p.stderr.strip()


GUARD_CODE = '''
import asyncio
from yog_runtime import yog_guard, YogDenied
import inspect

@yog_guard("unlock_door")
def unlock_door(door_id: str, pin: str | None = None) -> str:
    """doc"""
    return "OPENED " + door_id

@yog_guard("unlock_door")
async def aunlock(door_id: str) -> str:
    return "AOPENED"

print(inspect.signature(unlock_door), unlock_door.__name__, unlock_door.__doc__)
for fn, call in ((unlock_door, lambda: unlock_door("front_door")), (aunlock, lambda: asyncio.run(aunlock("front_door")))):
    try:
        print(call())
    except YogDenied as e:
        print("DENIED")
'''


def test_runtime_allows_by_day_and_denies_at_3am(bundle_dir):
    code, out, err = run_in(bundle_dir, GUARD_CODE, "14,mon")
    assert code == 0, err
    assert "(door_id: str, pin: str | None = None)" in out.splitlines()[0] and "unlock_door" in out and "doc" in out
    assert out.splitlines()[1:] == ["OPENED front_door", "AOPENED"]
    code, out, err = run_in(bundle_dir, GUARD_CODE, "3,mon")
    assert code == 0, err
    assert out.splitlines()[1:] == ["DENIED", "DENIED"]


def test_runtime_fails_closed_without_policy(bundle_dir):
    (bundle_dir / "policy.yog").unlink()
    code, out, err = run_in(bundle_dir, GUARD_CODE, "14,mon")
    assert code == 0 and out.splitlines()[1:] == ["DENIED", "DENIED"]


def test_runtime_unknown_tool_denied(bundle_dir):
    code_str = ('from yog_runtime import yog_guard, YogDenied\n@yog_guard("launch_missile")\ndef f(x: str): return 1\n'
                'try:\n    f("a")\nexcept YogDenied:\n    print("DENIED")\n')
    assert run_in(bundle_dir, code_str, "14,mon")[1] == "DENIED"


# ---------------------------------------------------------------- API

def test_api_modify_and_bundle(tmp_path):
    store = PolicyStore(tmp_path / "p")
    app.dependency_overrides[get_store] = lambda: store
    try:
        c = TestClient(app)
        body = {"filename": "smart_home_mcp.py", "source": src("smart_home_mcp.py")}
        j = c.post("/modify", json=body).json()
        assert j["removed_lines"] == 0 and j["diff"].startswith("--- a/smart_home_mcp.py") and len(j["guarded"]) == 5
        assert c.post("/modify", json={"source": "def (:"}).status_code == 422
        assert c.post("/modify", json={"source": src("not_an_agent.py")}).status_code == 422
        assert c.post("/modify/bundle", json={**body, "policy_id": "p-20200101000000-deadbeef"}).status_code == 404
        pid = store.save(NIGHT).id
        r = c.post("/modify/bundle", json={**body, "policy_id": pid})
        assert r.status_code == 200 and r.headers["content-type"] == "application/zip"
        z = zipfile.ZipFile(io.BytesIO(r.content))
        assert sorted(z.namelist()) == ["README.txt", "policy.yog", "smart_home_mcp.py", "yog.py", "yog_runtime.py"]
        assert z.read("policy.yog").decode() == NIGHT
        assert "@yog_guard(" in z.read("smart_home_mcp.py").decode()
    finally:
        app.dependency_overrides.clear()
