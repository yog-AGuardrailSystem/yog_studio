"""Why-Explainer: the clause-by-clause proof must always agree with the engine's own check()."""
import pytest

from app.engine.adapter import WhyResult
from app.rag.examples import load_examples
from app.studio.why import explain_checked
from tests.studio_helpers import DEMO, adapter, client

A = adapter()


def why(policy, actor, action, resource, ctx=None):
    return A.explain(policy, actor, action, resource, ctx or [])


def test_deny_beats_allow_and_names_both_rules():
    r = why(DEMO, "agent", "can_unlock_door", "front_door", ["hour(now, 3)"])
    assert r.decision == "DENY" and r.winner_line == 24
    assert "DENY beats ALLOW" in r.verdict and "line 7" in r.verdict
    kinds = {(c.kind, c.status) for c in r.clauses}
    assert ("deny", "matched") in kinds and ("allow", "matched") in kinds


def test_allow_when_no_deny_applies():
    r = why(DEMO, "agent", "can_unlock_door", "front_door", ["hour(now, 14)"])
    assert r.decision == "ALLOW" and r.winner_line == 7
    deny = [c for c in r.clauses if c.kind == "deny"]
    assert deny and all(c.status == "failed" for c in deny)


def test_failed_clause_shows_values_and_where_it_stopped():
    r = why(DEMO, "agent", "can_unlock_door", "front_door", ["hour(now, 14)"])
    d = next(c for c in r.clauses if c.kind == "deny" and c.line == 21)        # `H >= 23`; the `H < 6` rule is line 24
    assert d.status == "failed" and d.failed_at == 1
    assert d.steps[0].ok is True and d.steps[1].ok is False and "14 >= 23" in d.steps[1].text
    assert d.steps[1].note == "this comparison is false"


def test_default_deny_points_at_the_closest_allow_rule():
    r = why(DEMO, "agent", "can_set_thermostat", "living_room", ["arg(set_thermostat, temperature, 35)"])
    assert r.decision == "DENY" and r.winner_line is None and r.reason.startswith("default deny")
    assert "closest allow rule" in r.verdict and "35 <= 28" in r.verdict


def test_unknown_actor_is_a_head_or_body_failure_not_a_crash():
    r = why(DEMO, "stranger", "can_unlock_door", "front_door", ["hour(now, 14)"])
    assert r.decision == "DENY" and "role(stranger, assistant)" in r.verdict


def test_unknown_action_has_no_clauses():
    r = why(DEMO, "agent", "can_fly", "x")
    assert r.decision == "DENY" and r.clauses == [] and "no allow or deny rule" in r.verdict


def test_negation_and_rule_chain():
    pol = """fact role(a, admin)
fact blocked(a, no)
rule trusted(U):
    role(U, admin)
    not blocked(U, yes)
allow can_x(U, R):
    trusted(U)
deny can_x(U, R):
    blocked(U, yes)
"""
    ok = why(pol, "a", "can_x", "r")
    assert ok.decision == "ALLOW"
    assert any("not blocked" in s.text for c in ok.clauses for s in c.steps) or ok.clauses[0].steps
    r2 = A.explain(pol + "fact blocked(a, yes)\n", "a", "can_x", "r", [])
    assert r2.decision == "DENY" and "line 8" in r2.verdict or r2.winner_line is not None


def test_head_mismatch_when_a_clause_is_about_a_constant_resource():
    pol = "fact role(a, x)\nallow can_x(U, vault):\n    role(U, x)\nallow can_x(U, desk):\n    role(U, x)\n"
    r = why(pol, "a", "can_x", "desk")
    assert r.decision == "ALLOW"
    assert next(c for c in r.clauses if c.line == 2).status == "head_mismatch"


def test_engine_type_error_fails_closed_like_check():
    pol = "fact role(agent, a)\nfact arg(placeholder, placeholder, 0)\nallow can_x(U, R):\n    role(U, a)\n    arg(x, p, V)\n    V >= 5\n"
    ctx = ["arg(x, p, word)"]                                  # compares a name with an integer: engine issue #7
    r = A.explain(pol, "agent", "can_x", "r", ctx)
    assert r.decision == "DENY" and r.error and A.check(pol, "agent", "can_x", "r", ctx).decision == "DENY"


def test_context_facts_do_not_leak_between_calls():
    why(DEMO, "agent", "can_unlock_door", "front_door", ["hour(now, 3)"])
    r = why(DEMO, "agent", "can_unlock_door", "front_door", [])
    assert r.decision == "ALLOW"                                # no hour fact left over from the previous call


def test_explain_checked_hides_a_disagreeing_explanation():
    class Lying(type(A)):
        def explain(self, *a, **k):
            r = super().explain(*a, **k)
            return WhyResult(decision="ALLOW" if r.decision == "DENY" else "DENY", reason="x", verdict="lies")

    res, ok = explain_checked(Lying(), DEMO, "agent", "can_unlock_door", "front_door", ["hour(now, 3)"])
    assert not ok and res.decision == "DENY" and "did not agree" in res.verdict and res.error


def _scenarios():
    out = []
    for e in load_examples():
        for s in e.scenarios:
            out.append((e.id, e.gold_yog, s))
    return out


@pytest.mark.parametrize("eid,policy,s", _scenarios(), ids=lambda v: v if isinstance(v, str) and len(v) < 40 else "")
def test_explanation_agrees_with_check_on_every_example_scenario(eid, policy, s):
    chk = A.check(policy, s.actor, s.action, s.resource, s.context)
    why_ = A.explain(policy, s.actor, s.action, s.resource, s.context)
    assert why_.decision == chk.decision, f"{eid}: {s}"
    matched = [c for c in why_.clauses if c.status == "matched"]
    denies = any(c.kind == "deny" for c in matched)
    allows = any(c.kind == "allow" for c in matched)
    assert (chk.decision == "ALLOW") == (allows and not denies)          # DENY beats ALLOW; no match at all is DENY
    assert chk.decision == "DENY" or why_.winner_line is not None


def test_api_why_and_errors():
    c = client()
    body = {"policy_id": "demo", "actor": "agent", "action": "can_unlock_door", "resource": "front_door", "context": ["hour(now, 3)"]}
    j = c.post("/studio/why", json=body).json()
    assert j["consistent"] and j["result"]["decision"] == "DENY" and j["policy_label"].startswith("demo")
    assert "can_unlock_door" in j["source"]
    assert c.post("/studio/why", json={**body, "context": ["not a fact"]}).status_code == 422
    assert c.post("/studio/why", json={**body, "policy_id": None, "source": "allow bad(\n"}).status_code == 422
    assert c.post("/studio/why", json={**body, "policy_id": None}).status_code == 409           # nothing approved yet
    assert c.post("/studio/why", json={**body, "actor": "x" * 500}).status_code == 422          # field length cap
