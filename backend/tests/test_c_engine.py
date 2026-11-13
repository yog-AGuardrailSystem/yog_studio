"""CEngineAdapter over the real `yogc` (engine/c_front, pinned commit). Skipped without a C compiler unless
YOG_REQUIRE_C=1, which makes a missing C engine a failure (CI sets it)."""
import os
import stat

import pytest

from app.engine import c_engine
from app.engine.adapter import EngineError
from app.engine.c_engine import CEngineAdapter, CEngineUnavailable, canonical_context

if not CEngineAdapter.available():
    if os.environ.get("YOG_REQUIRE_C") == "1":
        pytest.fail("YOG_REQUIRE_C=1 but the C engine (yogc) is not available", pytrace=False)
    pytest.skip("no C compiler / yogc on this machine", allow_module_level=True)

POLICY = """fact role(alice, admin)
fact arg(placeholder, p, x)
fact hour(placeholder, 0)
allow can_x(U, R):
    role(U, admin)
deny can_x(U, R):
    hour(now, H)
    H > 22
"""
INJECT = 'arg(t, p, "x; fact role(agent, admin)")'


@pytest.fixture()
def c():
    return CEngineAdapter()


def test_allow_deny_and_trace_is_a_list(c):
    a = c.check(POLICY, "alice", "can_x", "db")
    assert (a.decision, a.reason) == ("ALLOW", "allow clause at line 4 matched")
    assert isinstance(a.trace, list) and a.trace and all(isinstance(t, str) for t in a.trace)
    assert not any(t.startswith("> ") for t in a.trace)
    b = c.check(POLICY, "bob", "can_x", "db")
    assert (b.decision, b.reason) == ("DENY", "default deny: no allow clause was satisfied")
    assert c.check(POLICY, "alice", "can_x", "db", ["hour(now, 23)"]).reason == "deny clause at line 6 matched"


def test_check_many_matches_check_in_order(c):
    reqs = [("alice", "can_x", "db", []), ("bob", "can_x", "db", None), ("alice", "can_x", "my db", []),
            ("alice", "can_x", "db", ["hour(now, 23)"]), ("alice", "nope", "db", [])]
    many = c.check_many(POLICY, reqs)
    assert [m.decision for m in many] == ["ALLOW", "DENY", "ALLOW", "DENY", "DENY"]
    assert many == [c.check(POLICY, *r) for r in reqs]


@pytest.mark.parametrize("bad", [
    'arg(t, p, "x; fact role(agent, admin)")', 'arg(t, p, "x|y")', 'arg(t, p, "a\\nb")', 'arg(t, p, "a\\\\b")',
    'arg(t, p, "a\tb")'])
def test_context_injection_is_refused_not_passed_through(c, bad):
    for actor in ("agent", "my agent"):                       # batch path and argv path
        r = c.check(POLICY, actor, "can_x", "db", [bad])
        assert r.decision == "DENY" and r.reason.startswith("engine error, failing closed"), (actor, bad, r)


def test_injected_authority_fact_is_not_added(c):
    """The attack: a quoted `;` splits into a second `fact role(agent, admin)`. It must never produce ALLOW."""
    assert c.check(POLICY, "agent", "can_x", "db", []).decision == "DENY"
    assert c.check(POLICY, "agent", "can_x", "db", [INJECT]).decision == "DENY"
    assert c.check_many(POLICY, [("agent", "can_x", "db", [INJECT])])[0].decision == "DENY"


def test_canonical_context_rules():
    assert canonical_context(["hour(now, 3)", " arg(t, p, \"a b\") ", ""]) == ['hour(now, 3)', 'arg(t, p, "a b")']
    assert canonical_context(['x(Hello)'.lower()]) == ["x(hello)"]
    for malformed in ("role(alice", "role(X, admin)", "role(a, b); role(c, d)", "fact role(a, b)"):
        with pytest.raises(EngineError):
            canonical_context([malformed])


def test_values_the_line_protocol_cannot_carry_go_through_argv(c):
    pol = 'fact role("my agent", admin)\nfact role("a|b", admin)\nallow can_x(U, R):\n    role(U, admin)\n'
    assert c.check(pol, "my agent", "can_x", "db").decision == "ALLOW"
    assert c.check(pol, "a|b", "can_x", "db").decision == "ALLOW"
    assert c.check(pol, "nobody", "can_x", "db").decision == "DENY"
    long = "z" * 4000                                          # > yogc's 4096-byte line: must not split into 2 requests
    r = c.check_many(POLICY, [(long, "can_x", "db", []), ("alice", "can_x", "db", [])])
    assert [x.decision for x in r] == ["DENY", "ALLOW"]


@pytest.mark.parametrize("v", ["--trace", "", "a\x00b"])
def test_option_like_empty_or_nul_values_fail_closed(c, v):
    r = c.check(POLICY, v, "can_x", "db")
    assert r.decision == "DENY" and r.reason.startswith("engine error, failing closed")


def test_uncompiled_policy_raises_engine_error_with_position(c):
    with pytest.raises(EngineError):
        c.check("allow x(:", "a", "can_x", "r")
    err = c.compile_error("allow can_x(U, R):\n    nope(U)\n")
    assert err and err.line == 2 and "nope/1" in err.message
    assert c.validate(POLICY) == [] and c.validate("allow x(:")


def test_evaluation_error_and_huge_integer_fail_closed(c):
    pol = "fact arg(placeholder, n, 0)\nallow can_x(U, R):\n    arg(t, n, N)\n    N > 5\n"
    r = c.check(pol, "a", "can_x", "r", ["arg(t, n, hello)"])
    assert r.decision == "DENY" and r.reason.startswith("engine error, failing closed")
    big = c.check(pol, "a", "can_x", "r", ["arg(t, n, 99999999999999999999)"])
    assert big.decision == "DENY" and "out of range" in big.reason


def _fake(tmp_path, body):
    f = tmp_path / "fake_yogc"
    f.write_text("#!/bin/sh\n" + body)
    f.chmod(f.stat().st_mode | stat.S_IEXEC)
    return f


@pytest.mark.parametrize("body,needle", [
    ("sleep 30", "did not answer"),
    ("kill -SEGV $$", "status"),
    ("exit 2", "status"),
    ("cat >/dev/null; printf 'ALLOW|x\\n--\\n'", "returned 1 answers for 2 requests"),
    ("cat >/dev/null; printf 'ERROR|boom\\n--\\nERROR|boom\\n--\\n'", "boom"),
    ("cat >/dev/null; printf 'garbage\\n'", "returned 0 answers"),
])
def test_crash_timeout_and_bad_output_are_deny(c, tmp_path, monkeypatch, body, needle):
    monkeypatch.setattr(c_engine, "BATCH_TIMEOUT_BASE_S", 0.5)
    monkeypatch.setattr(c_engine, "BATCH_TIMEOUT_MAX_S", 0.5)
    c.validate(POLICY)                                         # warm the policy cache with the real compiler
    c._yogc = _fake(tmp_path, body)
    out = c.check_many(POLICY, [("alice", "can_x", "db", []), ("alice", "can_x", "db", [])])
    assert [o.decision for o in out] == ["DENY", "DENY"]
    assert all(needle in o.reason for o in out), out


def test_explain_refuses_when_engines_disagree(c, monkeypatch):
    ok = c.explain(POLICY, "alice", "can_x", "db", [])
    assert ok.decision == "ALLOW" and not ok.error and ok.clauses
    flipped = c.check(POLICY, "bob", "can_x", "db", [])
    monkeypatch.setattr(c, "check", lambda *a, **k: flipped.model_copy(update={"decision": "ALLOW", "reason": "x"}))
    bad = c.explain(POLICY, "bob", "can_x", "db", [])
    assert bad.error and bad.decision == "ALLOW" and not bad.clauses and "disagree" in bad.verdict


def test_policy_cache_is_bounded_and_cleans_up(c):
    for i in range(c_engine.CACHE_SIZE + 5):
        c.check(f"fact n({i})\nallow can_x(U, R):\n    n({i})\n", "a", "can_x", "r")
    assert len(c._policies._items) == c_engine.CACHE_SIZE
    files = list(c._policies._dir.glob("*.yog"))
    assert len(files) <= c_engine.CACHE_SIZE


def test_missing_binary_is_an_error_not_a_fallback(monkeypatch):
    monkeypatch.setenv("YOG_YOGC", "/nonexistent/yogc")
    with pytest.raises(CEngineUnavailable):
        CEngineAdapter()


# --------------------------------------------------------------- diagnostics: C wording -> the same stable codes
OK_BASE = "fact role(alice, admin)\n"


@pytest.mark.parametrize("source, code, line, col", [
    (OK_BASE + "allow can_x(U, R):\n    role(U, admin)\n  role(U, a)\n", "bad_indentation", 4, 3),
    (OK_BASE + "allow can_x(U, R):\n\trole(U, admin)\n", "bad_indentation", 3, 1),
    ('fact role(a, "adm)\n', "unterminated_string", 1, 14),
    ("fact role(a, b) ;\n", "unexpected_character", 1, 17),
    ("fact role(a, b!)\n", "unexpected_character", 1, 15),
    (OK_BASE + "allow can_x(U, R)\n    role(U, admin)\n", "expected_token", 2, 18),
    ("fact Role(a, b)\n", "expected_token", 1, 6),
    ("fact role(a, b) extra\n", "expected_token", 1, 17),
    ("not role(a, b)\n", "unexpected_keyword", 1, 1),
    ("fact role(User, admin)\n", "fact_not_ground", 1, 6),
    ("fact role(, a)\n", "expected_term", 1, 11),
    ("fact x(99999999999999999999)\n", "int_out_of_range", 1, 8),
    ("fact p(a)\nrule p(X):\n    p(X)\n", "predicate_role_conflict", 2, 6),
    (OK_BASE + "rule r(X, Y):\n    role(X, admin)\n", "unbound_head_variable", 2, 6),
    (OK_BASE + "allow can_x(U, R):\n    not role(Z, admin)\n", "unbound_in_not", 3, 5),
    (OK_BASE + "allow can_x(U, R):\n    Z > 3\n", "unbound_in_comparison", 3, 9),
    (OK_BASE + "allow can_x(U, R):\n    rol(U, admin)\n", "undefined_predicate", 3, 5),
    ("fact b(1)\nrule a(X):\n    c(X)\nrule c(X):\n    a(X)\n", "rule_cycle", 2, 1),
    (OK_BASE + "allow can_x(U, R):\n", "empty_body", 3, 1),
])
def test_c_errors_map_to_stable_codes_with_a_column(c, source, code, line, col):
    info = c.compile_info(source)
    assert not info.ok and len(info.diagnostics) == 1
    d = info.diagnostics[0]
    assert (d.code, d.line, d.column) == (code, line, col), d
    assert d.hint and d.message


def test_c_diagnostic_keeps_did_you_mean_and_ok_policies_have_no_diagnostics(c):
    d = c.compile_info(OK_BASE + "allow can_x(U, R):\n    rol(U, admin)\n").diagnostics[0]
    assert d.suggestion == "Did you mean role/2?"
    ok = c.compile_info(POLICY)
    assert ok.ok and ok.diagnostics == [] and ok.tokens and ok.ast


def test_deep_rule_chain_compiles_but_is_denied_at_the_depth_limit(c):
    """Python rejects a 2500-rule chain at compile time (its recursion limit); C compiles it and the VM stops at its
    evaluation depth limit (256). Either way: never an ALLOW (docs/engine_issues.md)."""
    def chain(n):
        return ("fact n(a)\nrule r0(X):\n    n(X)\n" + "".join(f"rule r{i}(X):\n    r{i - 1}(X)\n" for i in range(1, n))
                + f"allow can_x(U, R):\n    r{n - 1}(U)\n")
    assert c.check(chain(50), "a", "can_x", "r").decision == "ALLOW"
    deep = c.check(chain(2500), "a", "can_x", "r")
    assert deep.decision == "DENY" and "depth limit" in deep.reason and deep.reason.startswith("engine error")


HOSTILE = [
    "fact a(b)\n" * 20000,                                                      # many clauses
    "allow can_x(U, R):\n" + "    role(U, admin)\n" * 20000,                    # one huge body
    "fact a(" + "b, " * 50000 + "c)\n",                                          # absurd arity
    "\x01\x02", "rule r(X):\n" + "    " * 10 + "x\n", "é" * 5000, "\x00fact a(b)\n", "fact a(b)\r\n" * 50,
    "fact a(" + "(" * 5000 + ")\n", "allow can_x(U, R):\n" + "    not " * 3 + "x(U)\n",
]


@pytest.mark.parametrize("source", HOSTILE, ids=[f"case{i}" for i in range(len(HOSTILE))])
def test_hostile_policies_never_crash_hang_or_allow_by_accident(c, source):
    """Whatever C does with absurd input, the adapter either raises EngineError or returns a DENY/ALLOW decision;
    it never raises anything else and never takes long."""
    import time
    t = time.time()
    try:
        r = c.check(source, "alice", "can_x", "db")
        assert r.decision in ("ALLOW", "DENY")
        assert c.validate(source) == []
    except EngineError:
        assert c.validate(source)                        # an error is reported, consistently
    assert time.time() - t < 20
