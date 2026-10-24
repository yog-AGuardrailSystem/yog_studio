import json

import pytest
from fastapi.testclient import TestClient

from app.api.deps import get_llm
from app.api.policies import get_store
from app.core import facts
from app.core.models import Tool
from app.engine.python_prototype import PythonPrototypeAdapter
from app.evaluate.evaluator import evaluate
from app.evaluate.scenarios import Scenario, characterization, generate_independent
from app.llm.fake import FakeProvider
from app.main import app
from app.policies.store import PolicyStore
from app.rag.examples import load_examples

adapter = PythonPrototypeAdapter()
EX = {e.id: e for e in load_examples()}
NIGHT = EX["sh-night-lock"].gold_yog
TOOLS = [Tool(name="unlock_door", source_line=1)]
RULES = ["The agent may never unlock the door between 11pm and 6am."]


def scripted(rows):
    return FakeProvider([json.dumps(rows)])


GOOD_ROWS = [
    {"actor": "agent", "action": "can_unlock_door", "resource": "front_door", "context": ["hour(now, 3)"], "expected": "DENY"},
    {"actor": "agent", "action": "can_unlock_door", "resource": "front_door", "context": ["hour(now, 14)"], "expected": "ALLOW"},
]


# ------------------------------------------------------------- facts normalisation

@pytest.mark.parametrize("raw,expected", [
    (True, 1), (False, 0), (21.5, 22), (7, 7), ("USD", "usd"), ("Front Door", "front_door"),
    ("123abc", "v_123abc"), ("", "empty"), (None, None), ([1, 2, 3], 3)])
def test_value_normalisation(raw, expected):
    assert facts.value(raw) == expected


def test_facts_from_call_always_adds_time_and_skips_none():
    f = facts.facts_from_call("Set_Thermostat", {"temperature": 21.5, "zone": "Living Room", "x": None}, 27, "Sat")
    assert f == ["hour(now, 3)", "day(now, sat)", "arg(set_thermostat, temperature, 22)",
                 "arg(set_thermostat, zone, living_room)"]


@pytest.mark.parametrize("raw", [21.5, "USD", True, "Front Door", None, ["a"], "9lives"])
def test_normalised_facts_are_always_accepted_by_the_engine(raw):
    pol = "fact arg(placeholder, placeholder, 0)\nfact role(agent, a)\nallow can_x(A, R):\n    role(A, a)\n"
    adapter.check(pol, "agent", "can_x", "r", facts.facts_from_call("t", {"p": raw}, 3, "mon"))


# ------------------------------------------------------------- characterization

def test_characterization_rows_are_unconfirmed_and_never_counted():
    rep = evaluate(adapter, NIGHT)
    assert rep.results and all(r.unconfirmed for r in rep.results)
    assert rep.summary.independent_total == 0 and rep.summary.pass_pct is None and not rep.summary.all_green
    assert rep.summary.unconfirmed == len(rep.results)
    assert any("No independent scenarios" in w for w in rep.warnings)


def test_boundary_hours_probed():
    scen, _ = characterization(adapter, NIGHT)
    hours = {c for s in scen for c in s.context}
    assert {"hour(now, 22)", "hour(now, 23)", "hour(now, 5)", "hour(now, 6)"} <= hours


def test_no_context_allow_is_warned():
    _, warnings = characterization(adapter, NIGHT)
    assert any("no time/argument information" in w for w in warnings)


def test_numeric_arg_boundaries():
    scen, _ = characterization(adapter, EX["sh-thermostat-range"].gold_yog)
    ctx = {c for s in scen for c in s.context}
    assert {"arg(set_thermostat, temperature, 15)", "arg(set_thermostat, temperature, 16)",
            "arg(set_thermostat, temperature, 28)", "arg(set_thermostat, temperature, 29)"} <= ctx


# ------------------------------------------------------------- independent scenarios

def test_llm_scenarios_graded_independently():
    rep = evaluate(adapter, NIGHT, rules=RULES, tools=TOOLS, provider=scripted(GOOD_ROWS))
    assert rep.summary.independent_total == 2 and rep.summary.independent_passed == 2
    assert rep.summary.pass_pct == 100.0 and rep.summary.all_green


def test_wrong_policy_shows_red():
    wrong = NIGHT.replace("H >= 23", "H >= 25")          # never denies at 11pm... and 3am still denied
    rows = GOOD_ROWS + [{"actor": "agent", "action": "can_unlock_door", "resource": "front_door",
                         "context": ["hour(now, 23)"], "expected": "DENY"}]
    rep = evaluate(adapter, wrong, rules=RULES, tools=TOOLS, provider=scripted(rows))
    bad = [r for r in rep.results if not r.unconfirmed and not r.passed]
    assert len(bad) == 1 and bad[0].context == ["hour(now, 23)"] and bad[0].actual == "ALLOW"
    assert not rep.summary.all_green and rep.summary.pass_pct == pytest.approx(66.7, abs=0.1)


def test_generator_never_sees_the_yog():
    p = scripted(GOOD_ROWS)
    evaluate(adapter, NIGHT, rules=RULES, tools=TOOLS, provider=p)
    assert "fact role" not in p.prompts[0] and "deny can_unlock_door" not in p.prompts[0]
    assert RULES[0] in p.prompts[0]


def test_bad_rows_are_skipped_individually():
    rows = GOOD_ROWS + [{"actor": "agent"}, {"actor": "a", "action": "can_nope", "resource": "r", "expected": "DENY"},
                        {"actor": "a", "action": "can_unlock_door", "resource": "r", "expected": "MAYBE"}]
    scen, problems = generate_independent(RULES, TOOLS, scripted(rows))
    assert len(scen) == 2 and len(problems) == 3


def test_bad_context_fails_one_row_not_the_run():
    rows = GOOD_ROWS + [{"actor": "agent", "action": "can_unlock_door", "resource": "r",
                         "context": ["this is not a fact"], "expected": "DENY"}]
    rep = evaluate(adapter, NIGHT, rules=RULES, tools=TOOLS, provider=scripted(rows))
    errs = [r for r in rep.results if r.error]
    assert len(errs) == 1 and rep.summary.errors == 1 and not rep.summary.all_green
    assert rep.summary.independent_passed == 2


@pytest.mark.parametrize("reply", ["no json here", "[not json", ""])
def test_garbage_llm_reply_is_a_warning(reply):
    rep = evaluate(adapter, NIGHT, rules=RULES, tools=TOOLS, provider=FakeProvider([reply]))
    assert rep.summary.independent_total == 0 and rep.warnings


def test_user_scenarios_count_as_independent():
    s = Scenario(actor="agent", action="can_unlock_door", resource="front_door", context=["hour(now, 2)"],
                 expected="DENY", source="user", unconfirmed=True)       # even if wrongly flagged, user rows are independent
    rep = evaluate(adapter, NIGHT, user_scenarios=[s])
    assert rep.summary.independent_total == 1 and rep.summary.all_green


def test_uncovered_tool_warned():
    rep = evaluate(adapter, NIGHT, tools=TOOLS + [Tool(name="open_valve", source_line=2)])
    assert any("open_valve" in w and "denied by default" in w for w in rep.warnings)


def test_invalid_policy_raises():
    from app.engine.adapter import EngineError
    with pytest.raises(EngineError):
        evaluate(adapter, "allow x(:")


@pytest.mark.parametrize("ex", list(EX.values()), ids=lambda e: e.id)
def test_gold_scenarios_all_green_as_user_scenarios(ex):
    us = [Scenario(**s.model_dump(), source="user") for s in ex.scenarios]
    rep = evaluate(adapter, ex.gold_yog, user_scenarios=us)
    assert rep.summary.all_green and rep.summary.independent_total == len(ex.scenarios)


# ------------------------------------------------------------- API + server-side approval evidence

def test_api_evaluate_and_approve_stores_server_side_evaluation(tmp_path):
    store = PolicyStore(tmp_path / "p")
    app.dependency_overrides[get_store] = lambda: store
    app.dependency_overrides[get_llm] = lambda: scripted(GOOD_ROWS)
    try:
        c = TestClient(app)
        r = c.post("/evaluate", json={"yog_source": NIGHT, "english_rules": RULES,
                                      "tools": [t.model_dump() for t in TOOLS]})
        assert r.status_code == 200 and r.json()["summary"]["all_green"] is True
        assert c.post("/evaluate", json={"yog_source": "allow x(:"}).status_code == 422
        # client-supplied "evaluation" is ignored; the server computes its own
        rec = c.post("/policies/approve", json={"yog_source": NIGHT, "evaluation": {"summary": "FAKE"}}).json()
        assert rec["evaluation"]["summary"] != "FAKE"
        assert rec["evaluation"]["summary"]["unconfirmed"] > 0
    finally:
        app.dependency_overrides.clear()
