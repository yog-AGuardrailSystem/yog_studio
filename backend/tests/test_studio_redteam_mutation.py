"""Red-Team and Test Strength (mutation testing)."""
from app.studio import mutation, redteam
from app.studio.common import Budget, shape
from tests.studio_helpers import DEMO, adapter, client

A = adapter()
HEAD = "fact role(agent, a)\nfact hour(placeholder, 0)\nfact arg(placeholder, placeholder, 0)\n"
WEAK = HEAD + "allow can_unlock_door(U, R):\n    role(U, a)\n"                      # no night rule at all
SMALL = HEAD + "allow can_x(U, R):\n    role(U, a)\ndeny can_x(U, R):\n    hour(now, H)\n    H >= 23\n"
NIGHT = redteam.Invariant(action="can_unlock_door", must="DENY", hour_min=23, hour_max=5)


def rt(src, invs=()):
    return redteam.run(A, src, shape(A.program_info(src)), list(invs), Budget())


# ----------------------------------------------------------------------------- red-team
def test_invariant_wraps_midnight_and_checks_the_decision():
    assert redteam._in_hours(23, 23, 5) and redteam._in_hours(0, 23, 5) and redteam._in_hours(5, 23, 5) and not redteam._in_hours(6, 23, 5)
    assert redteam._in_hours(9, 9, 17) and not redteam._in_hours(18, 9, 17)
    assert not redteam._in_hours(24, 23, 5) and not redteam._in_hours(99, 23, 5) and not redteam._in_hours(-1, 23, 5)
    assert redteam._violation(NIGHT, ["hour(now, 3)"], "ALLOW")
    assert not redteam._violation(NIGHT, ["hour(now, 3)"], "DENY")
    assert not redteam._violation(NIGHT, ["hour(now, 12)"], "ALLOW")           # outside the stated hours
    assert not redteam._violation(NIGHT, [], "ALLOW")                          # hour unknown: cannot be called a violation


def test_invariant_on_an_argument_range():
    inv = redteam.Invariant(action="can_set_thermostat", must="DENY", arg=redteam.ArgCond(tool="set_thermostat", param="temperature", min=29))
    assert redteam._violation(inv, ["arg(set_thermostat, temperature, 35)"], "ALLOW")
    assert not redteam._violation(inv, ["arg(set_thermostat, temperature, 20)"], "ALLOW")
    assert not redteam._violation(inv, ["arg(set_thermostat, temperature, 35)"], "DENY")


def test_demo_policy_keeps_its_promises():
    invs = [NIGHT, redteam.Invariant(action="can_set_thermostat", must="DENY", arg=redteam.ArgCond(tool="set_thermostat", param="temperature", min=29)),
            redteam.Invariant(action="can_open_valve", must="DENY", arg=redteam.ArgCond(tool="open_valve", param="percent", min=51))]
    r = rt(DEMO, invs)
    assert r.counterexamples == 0 and r.checked > 200
    assert {f.family for f in r.families} >= {"boundary", "time", "dropped_context", "unknown_actor", "normalisation", "extreme"}
    assert all(f.total > 0 for f in r.families)


def test_a_policy_without_the_night_rule_is_caught():
    r = rt(WEAK, [NIGHT])
    bad = [a for a in r.attacks if a.violates == 0]
    assert r.counterexamples == len(bad) >= 7                                  # hours 23, 0..5 at least
    assert all(a.family == "time" and a.decision == "ALLOW" for a in bad)
    assert bad[0].context and bad[0].context[0].startswith("hour(now, ")


def test_without_invariants_nothing_is_called_a_violation():
    r = rt(WEAK)
    assert r.counterexamples == 0 and r.suspicious > 0 and "No invariants were given" in r.note
    assert all(a.violates is None for a in r.attacks)


def test_suspicious_allows_are_listed_for_missing_context():
    r = rt(DEMO)
    assert any(a.family == "dropped_context" and a.suspicious for a in r.attacks)
    assert not any(a.family == "time" and a.suspicious for a in r.attacks)       # a time-of-day ALLOW is not flagged by itself


def test_attack_rows_are_capped_and_ordered_violations_first():
    r = rt(WEAK, [NIGHT])
    assert len(r.attacks) <= redteam.MAX_ROWS and r.attacks[0].violates is not None
    assert r.invariants == ["can_unlock_door must be DENY when the hour is 23 to 5"]


def test_redteam_api():
    c = client()
    j = c.post("/studio/redteam", json={"policy_id": "demo", "invariants": [{"action": "can_unlock_door", "must": "DENY", "hour_min": 23, "hour_max": 5}]}).json()
    assert j["counterexamples"] == 0 and j["checked"] > 0
    assert c.post("/studio/redteam", json={"policy_id": "demo", "invariants": [{"action": "a", "hour_min": 99}]}).status_code == 422
    assert c.post("/studio/redteam", json={"policy_id": "demo", "invariants": [{"action": "a"}] * 21}).status_code == 422


# ----------------------------------------------------------------------------- mutation
def mut(src, tests=(), n=40):
    return mutation.run(A, src, shape(A.program_info(src)), list(tests), n, Budget(20000))


def test_mutants_are_deterministic_and_each_differs_from_the_original():
    a, b = mutation.generate(SMALL), mutation.generate(SMALL)
    assert [m[:5] for m in a] == [m[:5] for m in b] and a
    assert all(m[5]() != SMALL for m in a)
    kinds = {m[1] for m in a}
    assert {"flip comparison", "shift number", "drop deny rule", "drop allow rule"} <= kinds


def test_dropping_the_only_condition_of_a_clause_is_not_offered():
    kinds = [m[1] for m in mutation.generate(SMALL) if m[3].startswith("role(U, a)")]
    assert "drop condition" not in kinds                                       # single-condition bodies cannot lose their only line


def test_invalid_mutants_are_counted_not_scored():
    r = mut(SMALL)
    assert r.valid + r.invalid == len(r.mutants) and r.killed + r.survived == r.valid


def test_weak_tests_score_lower_than_strong_tests():
    TC = mutation.TestCase
    weak = [TC(actor="agent", action="can_x", resource="r", context=["hour(now, 12)"], expected="ALLOW")]
    strong = weak + [TC(actor="agent", action="can_x", resource="r", context=[f"hour(now, {h})"], expected="DENY" if h >= 23 else "ALLOW") for h in (0, 22, 23)] + \
        [TC(actor="stranger", action="can_x", resource="r", context=["hour(now, 12)"], expected="DENY")]
    w, s = mut(SMALL, weak), mut(SMALL, strong)
    assert w.tests_source == s.tests_source == "yours"
    assert s.score > w.score and s.survived < w.survived
    assert next(m for m in s.mutants if m.status == "killed").caught_by


def test_scenarios_the_original_already_fails_are_excluded_not_blamed():
    TC = mutation.TestCase
    wrong = TC(actor="agent", action="can_x", resource="r", context=["hour(now, 12)"], expected="DENY")      # actually ALLOW
    r = mut(SMALL, [wrong])
    assert r.tests_excluded == 1 and r.tests_used == 0 and r.killed == 0


def test_baseline_probes_are_used_when_there_are_no_scenarios():
    r = mut(DEMO)
    assert r.tests_source == "baseline" and r.tests_used > 50 and r.score is not None and r.score >= 90
    assert "generated from the policy itself" in r.note


def test_mutant_cap_is_spread_over_the_file():
    r = mut(DEMO, n=5)
    assert len(r.mutants) == 5
    assert len({m.line for m in r.mutants}) > 2                                 # not just the first five lines


def test_budget_exhaustion_returns_a_partial_report_not_an_error():
    r = mutation.run(A, DEMO, shape(A.program_info(DEMO)), [], 40, Budget(400))
    assert isinstance(r, mutation.MutationReport)


def test_mutation_api():
    c = client()
    j = c.post("/studio/mutation", json={"policy_id": "demo"}).json()
    assert j["score"] is not None and j["tests_source"] == "baseline"
    one = {"actor": "agent", "action": "can_unlock_door", "resource": "front_door", "context": ["hour(now, 3)"], "expected": "DENY"}
    j2 = c.post("/studio/mutation", json={"policy_id": "demo", "scenarios": [one]}).json()
    assert j2["tests_source"] == "yours" and j2["tests_used"] == 1
    assert c.post("/studio/mutation", json={"policy_id": "demo", "max_mutants": 500}).status_code == 422
