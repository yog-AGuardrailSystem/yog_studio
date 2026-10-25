import pytest
from fastapi.testclient import TestClient

from app.api.analyze import analyze_source
from app.api.retrieve import get_retriever
from app.core.config import EXAMPLES_DIR
from app.engine.python_prototype import PythonPrototypeAdapter
from app.llm.fake import FakeProvider
from app.llm.provider import LLMError, LLMProvider, load_prompt
from app.main import app
from app.rag.examples import load_examples
from app.rag.retriever import Retriever
from app.translate.translator import extract_yog, format_tools, translate

GOOD = """```yog
fact role(agent, assistant)
fact hour(placeholder, 0)
allow can_unlock_door(Actor, Door):
    role(Actor, assistant)
deny can_unlock_door(Actor, Door):
    hour(now, H)
    H >= 23
deny can_unlock_door(Actor, Door):
    hour(now, H)
    H < 6
```"""
BAD_SYNTAX = "```yog\nallow can_unlock_door(Actor Door):\n    role(Actor, assistant)\n```"
BAD_UNDEFINED = "```yog\nallow can_unlock_door(Actor, Door):\n    mystery(Actor)\n```"
WRONG_TOOL = "```yog\nfact role(agent, assistant)\nallow can_launch_rocket(A, R):\n    role(A, assistant)\n```"

RULE = "The agent may never unlock the door between 11pm and 6am."
adapter = PythonPrototypeAdapter()
smart = analyze_source("s.py", (EXAMPLES_DIR / "agents" / "smart_home_mcp.py").read_text(encoding="utf-8"))


@pytest.fixture()
def retriever(tmp_path):
    return Retriever(FakeProvider(), load_examples(), tmp_path / "i.npz")


def run(replies, retriever, tools=None, rules=None, **kw):
    p = FakeProvider(replies)
    d = translate(rules or [RULE], smart.tools if tools is None else tools, p, retriever, adapter, **kw)
    return d, p


def test_valid_on_first_try(retriever):
    d, p = run([GOOD], retriever)
    assert d.valid and d.attempts == 1 and d.errors == []
    assert "can_unlock_door" in d.yog_source and "```" not in d.yog_source
    assert "sh-night-lock" in d.retrieved_examples
    assert len(p.prompts) == 1


def test_repaired_on_second_try_and_error_is_fed_back(retriever):
    d, p = run([BAD_SYNTAX, GOOD], retriever)
    assert d.valid and d.attempts == 2
    assert len(p.prompts) == 2
    assert "Problems found" in p.prompts[1]
    assert "allow can_unlock_door(Actor Door)" in p.prompts[1]        # the previous draft is shown
    assert "line 1" in p.prompts[1]                                    # the compiler's message is included


def test_never_valid_reports_three_attempts_and_errors(retriever):
    d, p = run([BAD_SYNTAX, BAD_UNDEFINED, BAD_UNDEFINED], retriever)
    assert not d.valid and d.attempts == 3 and len(p.prompts) == 3
    assert d.errors and "mystery" in d.errors[0]
    assert d.yog_source.strip()                                         # last draft is kept so the user can fix it


def test_decision_for_unknown_tool_is_rejected(retriever):
    d, _ = run([WRONG_TOOL, GOOD], retriever)
    assert d.valid and d.attempts == 2


def test_wrong_tool_error_text(retriever):
    d, _ = run([WRONG_TOOL] * 3, retriever)
    assert not d.valid and "does not match any tool" in d.errors[0]


def test_no_tools_means_no_name_check(retriever):
    d, _ = run([WRONG_TOOL], retriever, tools=[])
    assert d.valid


def test_empty_reply_is_an_error(retriever):
    d, _ = run(["", GOOD], retriever)
    assert d.valid and d.attempts == 2


def test_llm_failure_is_reported_not_raised(retriever):
    class Boom(LLMProvider):
        name = "fake"
        def generate(self, prompt, system=None): raise LLMError("quota exceeded")
        def embed(self, texts): return FakeProvider().embed(texts)
    d = translate([RULE], smart.tools, Boom(), retriever, adapter)
    assert not d.valid and "quota exceeded" in d.errors[0]


def test_no_rules():
    d = translate(["  "], [], FakeProvider([]), Retriever(FakeProvider(), []), adapter)
    assert not d.valid and d.attempts == 0


def test_extract_yog_variants():
    assert extract_yog("```yog\nfact a(b)\n```") == "fact a(b)\n"
    assert extract_yog("Here you go:\n```\nfact a(b)\n```\nbye") == "fact a(b)\n"
    assert extract_yog("fact a(b)") == "fact a(b)\n"
    assert extract_yog("   ") == ""


def test_prompts_come_from_files_and_have_slots():
    t, r = load_prompt("translate"), load_prompt("repair")
    for slot in ("{{tools}}", "{{examples}}", "{{rules}}"):
        assert slot in t
    for slot in ("{{previous}}", "{{errors}}", "{{rules}}", "{{tools}}"):
        assert slot in r


def test_prompt_contains_tools_rules_and_examples(retriever):
    _, p = run([GOOD], retriever)
    assert "[can_unlock_door]" in p.prompts[0] and RULE in p.prompts[0] and "Similar solved examples" in p.prompts[0]
    assert "{{" not in p.prompts[0]                                    # every slot filled


def test_format_tools_uses_decision_names():
    assert "[can_set_thermostat]" in format_tools(smart.tools)


@pytest.mark.parametrize("ex", [e for e in load_examples() if len(e.tools_context) == 1][:15], ids=lambda e: e.id)
def test_gold_examples_pass_the_translator_lint(ex, retriever):
    """The default offline provider echoes the nearest example; for an identical rule it must come out valid."""
    from app.core.models import Tool
    tools = [Tool(name=t.split("(")[0], source_line=1) for t in ex.tools_context]
    d = translate([ex.english], tools, FakeProvider(), retriever, adapter)
    assert d.valid, d.errors


def test_api_translate(tmp_path):
    app.dependency_overrides[get_retriever] = lambda: Retriever(FakeProvider(), load_examples(), tmp_path / "i.npz")
    try:
        r = TestClient(app).post("/translate", json={
            "english_rules": [RULE], "tools": [t.model_dump() for t in smart.tools]})
        assert r.status_code == 200
        j = r.json()
        assert set(j) == {"english_rules", "yog_source", "retrieved_examples", "attempts", "valid", "errors"}
        assert j["valid"] is True and "OFFLINE FAKE" in j["yog_source"]
    finally:
        app.dependency_overrides.clear()
