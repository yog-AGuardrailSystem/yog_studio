import pytest

from app.engine.adapter import EngineError
from app.engine.python_prototype import PythonPrototypeAdapter

SAMPLE = """
fact role(alice, admin)
fact role(bob, viewer)
fact environment(db1, production)
fact environment(db2, staging)

rule is_prod(R):
    environment(R, production)

allow can_delete(User, Res):
    role(User, admin)

allow can_delete(User, Res):
    role(User, viewer)

deny can_delete(User, Res):
    is_prod(Res)
    not role(User, admin)
"""


@pytest.fixture(scope="module")
def adapter():
    return PythonPrototypeAdapter()


def test_allow(adapter):
    r = adapter.check(SAMPLE, "alice", "can_delete", "db1")
    assert r.decision == "ALLOW"
    assert "allow clause" in r.reason


def test_default_deny(adapter):
    r = adapter.check("fact role(alice, admin)\nallow can_x(U, R):\n    role(U, admin)\n",
                      "bob", "can_x", "r1")
    assert r.decision == "DENY"
    assert "default deny" in r.reason


def test_deny_beats_allow(adapter):
    # bob is a viewer -> an allow clause matches; db1 is production and bob is not admin -> deny matches.
    r = adapter.check(SAMPLE, "bob", "can_delete", "db1")
    assert r.decision == "DENY"
    assert "deny clause" in r.reason
    # same actor on staging: only the allow clause matches
    assert adapter.check(SAMPLE, "bob", "can_delete", "db2").decision == "ALLOW"


def test_unknown_action_is_deny(adapter):
    r = adapter.check(SAMPLE, "alice", "can_fly", "db1")
    assert r.decision == "DENY"
    assert "no allow/deny clause defines action" in r.reason


POLICY_CTX = """
fact role(agent, bot)
fact amount(placeholder, 0)
allow can_transfer(A, Acct):
    role(A, bot)
    amount(Acct, N)
    N <= 10000
"""


def test_context_fact_changes_decision_and_does_not_leak(adapter):
    low = adapter.check(POLICY_CTX, "agent", "can_transfer", "acct_1", ["amount(acct_1, 5000)"])
    high = adapter.check(POLICY_CTX, "agent", "can_transfer", "acct_1", ["amount(acct_1, 50000)"])
    none = adapter.check(POLICY_CTX, "agent", "can_transfer", "acct_1")
    assert (low.decision, high.decision, none.decision) == ("ALLOW", "DENY", "DENY")


def test_syntax_error_raises(adapter):
    with pytest.raises(EngineError):
        adapter.check("allow can_x(U R):\n    role(U, a)\n", "a", "can_x", "r")


def test_undefined_predicate_raises(adapter):
    with pytest.raises(EngineError, match="not defined"):
        adapter.check("allow can_x(U, R):\n    mystery(U)\n", "a", "can_x", "r")


def test_bad_context_raises(adapter):
    with pytest.raises(EngineError, match="bad context fact"):
        adapter.check(SAMPLE, "alice", "can_delete", "db1", ["not a fact"])


def test_trace_is_nonempty_on_match(adapter):
    r = adapter.check(SAMPLE, "alice", "can_delete", "db2")
    assert r.trace and all(isinstance(t, str) for t in r.trace)


def test_validate(adapter):
    assert adapter.validate(SAMPLE) == []
    errs = adapter.validate("allow can_x(U, R):\n    mystery(U)\n")
    assert len(errs) == 1 and "mystery" in errs[0]


def test_empty_policy_is_valid_and_denies(adapter):
    assert adapter.validate("") == []
    assert adapter.check("", "a", "can_x", "r").decision == "DENY"


def test_program_info_shape(adapter):
    info = adapter.program_info(SAMPLE)
    kinds = [c["kind"] for c in info["clauses"]]
    assert kinds.count("allow") == 2 and kinds.count("deny") == 1 and kinds.count("rule") == 1
    assert info["facts"][0]["pred"] == "role"


def test_engine_type_error_fails_closed(adapter):
    # regression: docs/engine_issues.md #7 -- int vs name comparison crashed the engine
    pol = ("fact role(a, bot)\nfact arg(t, p, 0)\nallow can_x(A, R):\n    role(A, bot)\n"
           "    arg(t, p, V)\n    V < usd\n")
    r = adapter.check(pol, "a", "can_x", "r")
    assert r.decision == "DENY" and "failing closed" in r.reason
