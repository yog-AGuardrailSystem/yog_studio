"""LangChain, OpenAI Agents SDK, CrewAI and PydanticAI: detected from the AST, tools extracted, agent patched with
insertions only. Nothing is imported or run."""
import ast

import pytest

from app.core.pyast import parse_source
from app.detect.detector import detect
from app.detect.frameworks import scan_frameworks
from app.extract.ast_extractor import extract_tools
from app.modify.modifier import modify
from tests.studio_helpers import AGENTS

CASES = {
    "langchain_tools_agent.py": ("langchain", ["delete_file", "send_report", "archive_folder"]),
    "openai_agents_sdk_agent.py": ("openai_agents", ["transfer_money", "close_account", "get_balance"]),
    "crewai_agent.py": ("crewai", ["run shell command", "publish release", "read build log"]),
    "pydantic_ai_agent.py": ("pydantic_ai", ["refund_order", "cancel_order", "lookup_order"]),
}


def load(name):
    src = (AGENTS / name).read_text(encoding="utf-8")
    return src, parse_source(src)


@pytest.mark.parametrize("name", CASES)
def test_detected_with_evidence_and_the_right_framework(name):
    src, tree = load(name)
    d = detect(tree, src)
    fw, tools = CASES[name]
    assert d.kind == "function_calling_agent" and d.framework == fw and d.confidence == 0.95
    assert any("import" in e for e in d.evidence) and sum("tool '" in e for e in d.evidence) == len(tools)


@pytest.mark.parametrize("name", CASES)
def test_tools_extracted_with_names_params_and_lines(name):
    src, tree = load(name)
    tools = extract_tools(tree, detect(tree, src))
    assert [t.name for t in tools] == CASES[name][1]
    assert all(t.source_line > 0 and t.docstring for t in tools)


def test_renamed_tools_use_the_registered_name_not_the_function_name():
    src, tree = load("openai_agents_sdk_agent.py")
    assert "close_account" in [t.name for t in extract_tools(tree, detect(tree, src))]                # def close_account_impl
    src, tree = load("crewai_agent.py")
    t = next(t for t in extract_tools(tree, detect(tree, src)) if t.name == "run shell command")
    assert [p.name for p in t.params] == ["command"] and t.docstring == "Run a shell command on the build server."


@pytest.mark.parametrize("name", CASES)
def test_patch_is_insertions_only_and_guards_directly_above_def(name):
    src, _ = load(name)
    r = modify(src, filename=name)
    assert r.removed_lines == 0 and sorted(r.guarded) == sorted(CASES[name][1]) and r.skipped == []
    assert r.added_lines == len(r.guarded) + 1                                                            # one guard each + the import
    ast.parse(r.patched_source)
    lines = r.patched_source.split("\n")
    for i, ln in enumerate(lines):
        if ln.startswith("@yog_guard("):
            assert lines[i + 1].lstrip().startswith(("def ", "async def "))                              # innermost: right above def


def test_langchain_keeps_its_decorator_outside_the_guard():
    src, _ = load("langchain_tools_agent.py")
    lines = modify(src).patched_source.split("\n")
    i = lines.index('@yog_guard("delete_file")')
    assert lines[i - 1] == "@tool"


def test_patch_is_idempotent():
    src, _ = load("pydantic_ai_agent.py")
    once = modify(src)
    twice = modify(once.patched_source)
    assert twice.guarded == [] and sorted(twice.already_guarded) == sorted(once.guarded) and twice.patched_source == once.patched_source


def test_only_subset():
    src, _ = load("crewai_agent.py")
    r = modify(src, ["publish release"])
    assert r.guarded == ["publish release"] and r.added_lines == 2


def test_a_stray_tool_decorator_without_the_import_is_not_a_framework():
    src = "def tool(f):\n    return f\n\n@tool\ndef delete_everything(path: str):\n    pass\n"
    tree = parse_source(src)
    assert scan_frameworks(tree).framework is None
    assert detect(tree, src).kind == "unknown"


def test_import_without_a_decorated_function_is_not_enough():
    src = "from langchain_core.tools import tool\n\ndef helper(x: str):\n    return x\n"
    tree = parse_source(src)
    d = detect(tree, src)
    assert d.kind == "unknown" and d.framework is None


def test_aliased_import_and_module_style_decorator():
    src = "from langchain_core.tools import tool as lc_tool\nimport crewai.tools as ct\n\n@lc_tool\ndef a(x: str):\n    pass\n"
    scan = scan_frameworks(parse_source(src))
    assert scan.framework == "langchain" and [t.name for t in scan.tools] == ["a"]
    src2 = "import langchain_core.tools as lt\n\n@lt.tool\ndef b(x: str):\n    pass\n"
    assert [t.name for t in scan_frameworks(parse_source(src2)).tools] == ["b"]


def test_async_functions_are_guardable():
    src = "from agents import function_tool\n\n@function_tool\nasync def fetch(url: str) -> str:\n    return url\n"
    r = modify(src)
    assert r.guarded == ["fetch"] and "async def fetch" in r.patched_source


def test_pydantic_ai_needs_an_agent_instance_for_the_attribute_form():
    src = "from pydantic_ai import Agent\n\nother = object()\n\n@other.tool\ndef f(x: str):\n    pass\n"
    assert scan_frameworks(parse_source(src)).tools == []


def test_the_older_detectors_are_unchanged():
    for name, kind in (("smart_home_mcp.py", "mcp_server"), ("openai_tools_agent.py", "function_calling_agent"), ("not_an_agent.py", "unknown")):
        src = (AGENTS / name).read_text(encoding="utf-8")
        d = detect(parse_source(src), src)
        assert d.kind == kind and d.framework is None


def test_schema_tools_and_decorated_tools_combine_without_duplicates():
    src = ('from agents import function_tool\nTOOLS = [{"type": "function", "function": {"name": "lookup", "description": "d", "parameters": {"type": "object", "properties": {}}}}]\n'
           '@function_tool\ndef lookup(q: str):\n    pass\n@function_tool\ndef other(q: str):\n    pass\n')
    tree = parse_source(src)
    names = [t.name for t in extract_tools(tree, detect(tree, src))]
    assert sorted(names) == ["lookup", "other"]


def test_analyze_api_reports_the_framework():
    from tests.studio_helpers import client
    c = client()
    src = (AGENTS / "langchain_tools_agent.py").read_text(encoding="utf-8")
    r = c.post("/analyze", json={"filename": "langchain_tools_agent.py", "source": src})
    assert r.status_code == 200, r.text
    j = r.json()
    assert j["detect"]["framework"] == "langchain" and [t["name"] for t in j["tools"]] == CASES["langchain_tools_agent.py"][1]
