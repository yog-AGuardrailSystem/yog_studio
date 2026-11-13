"""Regression tests for the problems the security audit (run-1) confirmed or could not rule out. Each test names the
finding it covers. All inputs are small dummy data; the pathological-policy tests rely on the new work budget to end
quickly, which is exactly what they check."""
import time

import pytest
from fastapi.testclient import TestClient

from app.api.deps import get_llm
from app.api.device import get_sim
from app.api.translate import MAX_RULE_CHARS, MAX_TOOL_TEXT, TranslateRequest
from app.core import session
from app.core.models import Param, Tool
from app.device.simulator import MAX_ARG_CHARS, MAX_ARGS
from app.engine import python_prototype as pp
from app.llm.fake import FakeProvider
from app.main import app
from app.studio import gaps as gaps_mod
from app.studio import mutation
from app.studio.common import Budget, shape
from tests.studio_helpers import DEMO, adapter, approve, client

A = adapter()


# ----------------------------------------------------------------------------- device simulator
def test_regression_cookieless_gets_do_not_evict_real_simulators():
    """device-sim-lru-eviction-by-cookieless-get: GET /device/state minted a session and an LRU entry per request."""
    get_sim.cache_clear()
    real = client()
    approve(real)
    assert real.post("/device/clock", json={"hour": 3, "day": "tue"}).status_code == 200
    drifter = TestClient(app)
    for _ in range(540):                                       # more than MAX_SIMS (500) cookie-less reads
        drifter.cookies.clear()
        assert drifter.get("/device/state").status_code == 200
    assert real.get("/device/state").json()["clock"] == {"hour": 3, "day": "tue"}


def test_a_first_get_shows_a_fresh_device_without_storing_it():
    get_sim.cache_clear()
    c = client()
    s = c.get("/device/state").json()
    assert s["clock"] == {"hour": 14, "day": "mon"} and s["log"] == []
    assert c.post("/device/clock", json={"hour": 5, "day": "wed"}).status_code == 200      # a write creates the real one
    assert c.get("/device/state").json()["clock"] == {"hour": 5, "day": "wed"}


def test_regression_device_arguments_are_bounded_in_bytes():
    """device-command-args-unbounded-sim-log-and-audit: values went into the log and the audit file at any length."""
    get_sim.cache_clear()
    c = client()
    ok = c.post("/device/command", json={"tool": "get_status", "args": {"device_id": "a" * MAX_ARG_CHARS}, "guard": False})
    assert ok.status_code == 200
    long_ = c.post("/device/command", json={"tool": "get_status", "args": {"device_id": "a" * (MAX_ARG_CHARS + 1)}, "guard": False})
    assert long_.status_code == 422 and "too long" in long_.json()["detail"]
    many = c.post("/device/command", json={"tool": "get_status", "args": {f"k{i}": 1 for i in range(MAX_ARGS + 1)}, "guard": False})
    assert many.status_code == 422
    nested = c.post("/device/command", json={"tool": "get_status", "args": {"device_id": {"x": [1]}}, "guard": False})
    assert nested.status_code == 422
    audit = c.get("/studio/audit").json()
    assert audit["total"] == 1 and max(len(str(e["args"])) for e in audit["entries"]) < 400      # refused ones were not logged


# ----------------------------------------------------------------------------- sessions
def test_regression_the_shared_fallback_session_is_not_acceptable_as_a_cookie():
    """The all-zero id is for requests that bypass the middleware; a client must not be able to land in it."""
    assert not session.acceptable_cookie(session.ANONYMOUS)
    assert session.acceptable_cookie("ab" * 16)
    c = TestClient(app)
    r = c.get("/health", headers={"Cookie": f"yog_sid={session.ANONYMOUS}"})
    assert "yog_sid=" in r.headers.get("set-cookie", "") and session.ANONYMOUS not in r.headers["set-cookie"]


def test_regression_session_id_regex_rejects_a_trailing_newline():
    assert session.valid("a" * 32) and not session.valid("a" * 32 + "\n") and not session.valid("a" * 31)


# ----------------------------------------------------------------------------- live LLM guard follows the provider
class _LiveStub(FakeProvider):
    name = "gemini"                                            # looks like a live provider; makes no network call


@pytest.fixture()
def live_default(monkeypatch):
    monkeypatch.setenv("LIVE_RATE_PER_MIN", "2")
    monkeypatch.setenv("LIVE_LLM_DAILY_CAP", "300")
    app.dependency_overrides[get_llm] = lambda: _LiveStub()
    yield
    app.dependency_overrides.pop(get_llm, None)


def test_regression_live_default_provider_is_rate_limited_without_mode(live_default):
    """live-guard-bypass-default-provider-mode: omitting `mode` skipped live_guard when the default provider is live."""
    c = client()
    body = {"english": "never unlock at night", "tools": []}
    codes = [c.post("/retrieve", json=body).status_code for _ in range(4)]
    assert codes[:2] == [200, 200] and 429 in codes[2:]


def test_regression_live_default_provider_honours_the_kill_switch(live_default, monkeypatch):
    monkeypatch.setenv("ALLOW_LIVE_LLM", "0")
    c = client()
    r = c.post("/retrieve", json={"english": "x", "tools": []})
    assert r.status_code == 409 and "switched off" in r.json()["detail"]


def test_regression_evaluate_with_a_live_default_provider_is_guarded(live_default):
    c = client()
    body = {"yog_source": DEMO, "english_rules": ["r"], "use_llm": True}
    codes = [c.post("/evaluate", json=body).status_code for _ in range(4)]
    assert 429 in codes
    assert c.post("/evaluate", json={**body, "use_llm": False}).status_code == 200            # no LLM, no quota, no guard


def test_the_offline_default_is_never_guarded():
    c = client()
    for _ in range(10):
        assert c.post("/retrieve", json={"english": "never unlock at night", "tools": []}).status_code == 200


# ----------------------------------------------------------------------------- size caps
def test_regression_translate_text_is_bounded_before_it_reaches_a_provider():
    """live-llm-budget-counts-requests-not-cost-unbounded-rule-text."""
    with pytest.raises(Exception):
        TranslateRequest(english_rules=["x" * (MAX_RULE_CHARS + 1)])
    t = Tool(name="n" * 500, docstring="d" * 50_000, source_line=1,
             params=[Param(name="p" * 500, type_hint="t" * 500, default="v" * 500) for _ in range(80)],
             side_effect_hints=["h" * 300] * 40)
    req = TranslateRequest(english_rules=["ok"], tools=[t])
    b = req.tools[0]
    assert len(b.name) == 200 and len(b.docstring) == MAX_TOOL_TEXT and len(b.params) == 50 and len(b.side_effect_hints) == 20
    assert max(len(p.name) for p in b.params) == 200 and max(len(h) for h in b.side_effect_hints) == 100


def test_regression_translate_route_rejects_oversized_rules():
    c = client()
    assert c.post("/translate", json={"english_rules": ["x" * (MAX_RULE_CHARS + 1)], "tools": []}).status_code == 422


def test_regression_stateless_routes_have_the_same_caps_as_the_studio_tools():
    c = client()
    big = "fact a(b)\n" * 25_000                                           # 250,000 characters
    assert c.post("/check", json={"policy": big, "actor": "a", "action": "can_x", "resource": "r"}).status_code == 422
    assert c.post("/check", json={"policy": "fact a(b)\n", "actor": "a", "action": "can_x", "resource": "r", "context": ["hour(now, 1)"] * 61}).status_code == 422
    assert c.post("/evaluate", json={"yog_source": big}).status_code == 422
    scen = {"actor": "a", "action": "can_x", "resource": "r", "expected": "DENY"}
    assert c.post("/evaluate", json={"yog_source": DEMO, "user_scenarios": [scen] * 201, "use_llm": False}).status_code == 422
    assert c.post("/explain", json={"yog_source": big}).status_code == 422
    assert c.post("/policies/approve", json={"yog_source": big, "english_rules": []}).status_code == 422
    assert c.post("/policies/approve", json={"yog_source": DEMO, "english_rules": ["r"] * 51}).status_code == 422
    assert c.post("/policies/approve", json={"yog_source": DEMO, "english_rules": ["r" * 2001]}).status_code == 422
    assert c.post("/policies/approve", json={"yog_source": DEMO, "english_rules": ["fine"]}).status_code == 200


# ----------------------------------------------------------------------------- engine work budget
JOIN = ("".join(f"fact item(i{i})\n" for i in range(9)) + "fact flag(no)\n"
        "allow can_x(U, R):\n" + "".join(f"    item(V{i})\n" for i in range(9)) + "    flag(yes)\n")


def test_regression_a_small_exponential_policy_fails_closed_instead_of_running_forever():
    """engine-evaluation-unbounded-work-and-memory: nine joins over nine facts is 9^9 steps before a late failure."""
    assert A.validate(JOIN) == []                                         # the compiler accepts it: the budget is the control
    t = time.time()
    r = A.check(JOIN, "u", "can_x", "r")
    assert r.decision == "DENY" and "evaluation budget exceeded" in r.reason
    assert time.time() - t < 30
    w = A.explain(JOIN, "u", "can_x", "r")
    assert w.decision == "DENY" and w.error and "failed closed" in w.verdict
    assert A.ask(JOIN, "item", [{"var": "X"}]).answer is True            # an ordinary query is unaffected
    assert not A.ask(JOIN, "can_x", [{"const": "u"}, {"const": "r"}]).answer


def test_the_budget_does_not_touch_honest_policies_and_resets_per_decision():
    assert A.check(DEMO, "agent", "can_unlock_door", "front_door", ["hour(now, 14)"]).decision == "ALLOW"
    for _ in range(3):                                                    # a budget exhausted by one check is not carried over
        assert A.check(JOIN, "u", "can_x", "r").decision == "DENY"
        assert A.check(DEMO, "agent", "can_unlock_door", "front_door", ["hour(now, 3)"]).decision == "DENY"
    assert pp.MAX_SOLVE_STEPS >= 100_000


def test_regression_the_budget_counts_the_facts_each_goal_is_tried_against():
    """engine-step-budget-ignores-fact-scan-cost (found in review of the first fix): the engine has no fact index, so one
    goal over a 12,000-fact predicate costs 12,000 unifications; counting goals alone let ~90k such goals through."""
    facts = "".join(f"fact q(n{i})\n" for i in range(12_000)) + "".join(f"fact s(a{i})\nfact t(b{i})\n" for i in range(200))
    pol = facts + "allow can_x(U, R):\n    s(X)\n    t(Y)\n    q(zz)\n"
    assert len(pol) < 200_000
    t = time.time()
    r = A.check(pol, "u", "can_x", "r")
    assert r.decision == "DENY" and "evaluation budget exceeded" in r.reason
    assert time.time() - t < 30


def test_a_policy_with_many_facts_but_cheap_goals_is_unaffected():
    pol = "".join(f"fact role(u{i}, admin)\n" for i in range(2000)) + "allow can_x(U, R):\n    role(U, admin)\n"
    r = A.check(pol, "u1999", "can_x", "r")
    assert r.decision == "ALLOW" and "budget" not in r.reason


def test_regression_deep_rule_chains_are_a_compile_error_not_a_crash():
    chain = "fact n(a)\nrule r0(X):\n    n(X)\n" + "".join(f"rule r{i}(X):\n    r{i - 1}(X)\n" for i in range(1, 2500)) + "allow can_x(U, R):\n    r2499(U)\n"
    errors = A.validate(chain)
    assert errors and "too deeply" in errors[0]
    from app.engine.adapter import EngineError
    with pytest.raises(EngineError):
        A.check(chain, "a", "can_x", "r")
    assert client().post("/check", json={"policy": chain, "actor": "a", "action": "can_x", "resource": "r"}).status_code == 422


def test_regression_a_huge_digit_run_is_a_compile_error_not_a_500():
    errors = A.validate("fact n(" + "9" * 5000 + ")\n")
    assert errors and "could not parse" in errors[0]


def test_regression_the_parse_cache_only_holds_small_policies():
    """parse-cache-retains-large-programs (found in review of the first fix): a parsed policy is far larger than its text."""
    pp._parse_cached.cache_clear()
    big = "".join(f"fact p(n{i})\n" for i in range(5000)) + "allow can_x(U, R):\n    p(U)\n"          # ~65,000 characters
    assert len(big) > pp.CACHE_MAX_CHARS
    A.check(big, "n1", "can_x", "r")
    A.check(big, "n1", "can_x", "r")
    assert pp._parse_cached.cache_info().currsize == 0
    A.check(DEMO, "agent", "can_unlock_door", "front_door")
    assert pp._parse_cached.cache_info().currsize == 1


def test_regression_run_adhoc_and_evaluate_scenarios_have_length_caps():
    """unbounded-context-facts-adhoc-and-scenario: /run and /evaluate accepted uncapped context lists and strings."""
    c = client()
    base = {"source": "fact a(b)\n"}
    assert c.post("/run", json={**base, "adhoc": {"actor": "a", "action": "can_x", "resource": "r", "context": ["p(1)"] * 61}}).status_code == 422
    assert c.post("/run", json={**base, "adhoc": {"actor": "a" * 201, "action": "can_x", "resource": "r"}}).status_code == 422
    assert c.post("/run", json={**base, "adhoc": {"actor": "a", "action": "can_x", "resource": "r", "context": ["p(" + "1" * 300 + ")"]}}).status_code == 422
    assert c.post("/run", json={**base, "adhoc": {"actor": "a", "action": "can_x", "resource": "r", "context": ["hour(now, 3)"]}}).status_code == 200
    scen = {"actor": "a" * 201, "action": "can_x", "resource": "r", "expected": "DENY"}
    assert c.post("/evaluate", json={"yog_source": DEMO, "user_scenarios": [scen], "use_llm": False}).status_code == 422


def test_context_facts_do_not_leak_after_a_budget_failure():
    A.check(JOIN, "u", "can_x", "r", ["flag(yes)"])
    assert A.check(JOIN, "u", "can_x", "r").decision == "DENY"


def test_regression_policy_text_is_parsed_once_not_once_per_check():
    """engine-check-reparses-whole-policy: cost per check scaled with policy size."""
    pp._parse_cached.cache_clear()
    for h in range(20):
        A.check(DEMO, "agent", "can_unlock_door", "front_door", [f"hour(now, {h})", "day(now, mon)"])
    info = pp._parse_cached.cache_info()
    assert info.misses == 1 and info.hits >= 19                            # one parse; context facts never enter the cache
    assert info.currsize == 1


def test_a_bad_policy_text_is_still_an_engine_error_every_time():
    for _ in range(2):
        assert A.validate("allow nonsense(\n")                             # exceptions are not cached


# ----------------------------------------------------------------------------- Gap Analyzer and Test Strength bounds
def _clause(src: str, n: int) -> dict:
    return [c for c in A.program_info(src)["clauses"] if c["kind"] in ("allow", "deny")][n]


def test_regression_shadows_ends_quickly_when_a_deny_goal_cannot_match():
    """studio-gaps-shadows-exponential-backtracking (the shape from the verified candidate)."""
    pre = "fact q(a)\nfact s(a)\n"
    allow = pre + "allow can_x(U, A, R):\n" + "".join(f"    q(B{i})\n" for i in range(10))
    deny = pre + "deny can_x(U, A, R):\n" + "".join(f"    q(V{i})\n" for i in range(11)) + "    s(V12)\n"
    t = time.time()
    assert gaps_mod.shadows(_clause(deny, 0), _clause(allow, 0)) is False
    assert time.time() - t < 1


def test_regression_shadows_has_a_step_cap_for_shapes_the_prefilter_lets_through():
    pre = "fact q(a)\nfact s(a)\nfact s(b)\n"
    allow = pre + "allow can_x(U, A, R):\n" + "".join(f"    q(B{i})\n" for i in range(10)) + "    s(b)\n"
    deny = pre + "deny can_x(U, A, R):\n" + "".join(f"    q(V{i})\n" for i in range(11)) + "    s(a)\n"   # same shapes, constants differ
    t = time.time()
    assert gaps_mod.shadows(_clause(deny, 0), _clause(allow, 0)) is False
    assert time.time() - t < 10


def test_shadows_still_finds_a_real_shadow():
    pre = "fact role(a, r)\nfact hour(placeholder, 0)\n"
    allow = _clause(pre + "allow can_x(U, R):\n    role(U, r)\n    hour(now, H)\n    H > 3\n", 0)
    deny = _clause(pre + "deny can_x(A, B):\n    hour(now, T)\n    T > 3\n", 0)
    assert gaps_mod.shadows(deny, allow)


def test_regression_mutation_generation_is_lazy_and_capped():
    """studio-mutation-generate-materialises-all-mutant-sources."""
    body = "".join(f"    H > {i}\n" for i in range(3000))
    src = "fact hour(placeholder, 0)\nfact role(a, r)\ndeny can_x(U, R):\n    hour(now, H)\n" + body
    out = mutation.generate(src)
    assert 0 < len(out) <= mutation.MAX_SITES
    assert all(callable(m[5]) and hasattr(m[5], "key") for m in out)        # no source text was built
    text = out[0][5]()
    assert isinstance(text, str) and text != src
    r = mutation.run(A, src, shape(A.program_info(src)), [], 5, Budget(20000))
    assert len(r.mutants) <= 5


def test_regression_red_team_and_probes_cap_the_argument_keys():
    atoms = "".join(f"    arg(t, p{i}, V{i})\n" for i in range(300))
    src = "fact arg(placeholder, placeholder, 0)\nfact role(agent, r)\nallow can_t(U, R):\n    role(U, r)\n" + atoms
    sh = shape(A.program_info(src))
    from app.studio.common import MAX_ARG_KEYS
    assert len(sh.arg_keys) == MAX_ARG_KEYS


def test_regression_characterization_stops_probing_past_the_row_cap():
    from app.evaluate.scenarios import MAX_PER_ACTION, characterization
    calls = []
    real = A.check

    class Counting(type(A)):
        def check(self, *a, **k):
            calls.append(1)
            return real(*a, **k)

    rows, _ = characterization(Counting(), DEMO)
    per = {}
    for s in rows:
        per[s.action] = per.get(s.action, 0) + 1
    assert max(per.values()) <= MAX_PER_ACTION
    assert len(calls) <= len(per) * (MAX_PER_ACTION + 10) + 5               # the probes stop once the cap is reachable


# ----------------------------------------------------------------------------- lossy fact normalisation (owner's decisions)
def test_regression_decimals_are_refused_in_every_copy_of_the_fact_builder():
    """facts-float-rounding-bypasses-numeric-bounds: 28.4 used to become 28 and pass 'temperature <= 28'."""
    from app.core import facts
    assert facts.value(28.0) == 28 and facts.value(-3.0) == -3 and facts.value(7) == 7
    for bad in (28.4, 28.5, 15.6, 50.4, float("nan"), float("inf"), float("-inf")):
        with pytest.raises(facts.FactError):
            facts.value(bad)
    with pytest.raises(facts.FactError) as e:
        facts.facts_from_call("set_thermostat", {"zone": "x", "temperature": 28.4}, 3, "mon")
    assert "temperature" in str(e.value) and "whole number" in str(e.value)


def test_regression_path_like_values_are_refused_not_merged():
    """facts-ident-collapses-distinct-paths-allowlist-bypass: ../notes.txt, /notes.txt and NOTES.TXT all became notes_txt."""
    from app.core import facts
    for bad in ("../notes.txt", "/notes.txt", "a/b", "a\\b", "a..b", "~/../x"):
        with pytest.raises(facts.FactError):
            facts.value(bad)
    assert facts.value("notes.txt") == "notes_txt" and facts.value("Front Door") == "front_door"   # plain names still work


def test_regression_sdk_try_and_replay_deny_what_the_guard_denies():
    c = client()
    d = c.post("/studio/sdk/try", json={"policy_id": "demo", "tool": "set_thermostat", "args": {"zone": "z", "temperature": 28.4}, "hour": 12}).json()
    assert d["decision"] == "DENY" and "not a whole number" in d["reason"]
    ok = c.post("/studio/sdk/try", json={"policy_id": "demo", "tool": "set_thermostat", "args": {"zone": "z", "temperature": 28}, "hour": 12}).json()
    assert ok["decision"] == "ALLOW"
    text = '{"tool": "set_thermostat", "args": {"zone": "z", "temperature": 28.4}, "hour": 12}\n{"tool": "set_thermostat", "args": {"zone": "z", "temperature": 28}, "hour": 12}\n'
    r = c.post("/studio/replay", json={"policy": {"policy_id": "demo"}, "text": text, "format": "jsonl"}).json()
    assert [x["decision"] for x in r["rows"]] == ["DENY", "ALLOW"] and "refused" in r["rows"][0]["reason"]
    cmp = c.post("/studio/replay", json={"policy": {"policy_id": "demo"}, "compare": {"policy_id": "demo"}, "text": text, "format": "jsonl"}).json()
    assert cmp["summary"]["changed"] == 0
