"""Every message the reference engine can raise maps to a stable code and a plain-English hint."""
import pytest

from app.engine.python_prototype import PythonPrototypeAdapter

adapter = PythonPrototypeAdapter()

OK_BASE = "fact role(alice, admin)\n"


def diag(source: str):
    info = adapter.compile_info(source)
    assert not info.ok, "expected the source to be rejected"
    assert len(info.diagnostics) == 1
    return info.diagnostics[0]


@pytest.mark.parametrize("source, code, line", [
    # tokenizer
    (OK_BASE + "allow can_x(U, R):\n    role(U, admin)\n  role(U, a)\n", "bad_indentation", 4),
    ('fact role(a, "adm)\n', "unterminated_string", 1),
    ("fact role(a, b) ;\n", "unexpected_character", 1),
    ("fact role(a, b!)\n", "unexpected_character", 1),
    # parser
    (OK_BASE + "allow can_x(U, R)\n    role(U, admin)\n", "expected_token", 2),
    ("fact Role(a, b)\n", "expected_token", 1),
    ("fact role(a, b) extra\n", "expected_token", 1),
    ("not role(a, b)\n", "unexpected_keyword", 1),
    ("fact role(User, admin)\n", "fact_not_ground", 1),
    ("fact role(, a)\n", "expected_term", 1),
    # semantic check
    ("fact p(a)\nrule p(X):\n    p(X)\n", "predicate_role_conflict", None),
    (OK_BASE + "rule r(X, Y):\n    role(X, admin)\n", "unbound_head_variable", 2),
    (OK_BASE + "allow can_x(U, R):\n    not role(Z, admin)\n", "unbound_in_not", 3),
    (OK_BASE + "allow can_x(U, R):\n    Z > 3\n", "unbound_in_comparison", 3),
    (OK_BASE + "allow can_x(U, R):\n    rol(U, admin)\n", "undefined_predicate", 3),
    ("fact b(1)\nrule a(X):\n    c(X)\nrule c(X):\n    a(X)\n", "rule_cycle", None),
])
def test_every_engine_error_has_a_code_and_a_hint(source, code, line):
    d = diag(source)
    assert d.code == code, d
    assert d.hint, f"{code} has no plain-English hint"
    assert d.message, "the engine's own message must be kept verbatim"
    if line is not None:
        assert d.line == line


def test_undefined_predicate_suggests_the_closest_defined_one():
    d = diag(OK_BASE + "allow can_x(U, R):\n    rol(U, admin)\n")
    assert d.suggestion == "Did you mean role/2?"


def test_undefined_predicate_without_a_near_match_has_no_suggestion():
    d = diag(OK_BASE + "allow can_x(U, R):\n    zzzzzz(U, admin)\n")
    assert d.suggestion is None


def test_old_fact_syntax_gets_an_exact_rewrite():
    d = diag("fact role(alice) = admin   # from the old design doc\n")
    assert d.code == "old_fact_syntax"
    assert d.fix == {"line": 1, "find": "fact role(alice) = admin   # from the old design doc",
                     "replace": "fact role(alice, admin)  # from the old design doc"}


def test_old_syntax_fix_really_compiles():
    src = "fact role(alice) = admin\nfact environment(db1) = production\n"
    info = adapter.compile_info(src)
    fixed = src.splitlines()
    for d in [info.diagnostics[0]]:
        fixed[d.fix["line"] - 1] = d.fix["replace"]
    again = adapter.compile_info("\n".join(fixed) + "\n")
    # the first line is repaired; the next old-style line is then reported (one error at a time)
    assert again.diagnostics[0].line == 2 and again.diagnostics[0].code == "old_fact_syntax"


def test_single_equals_inside_a_body_offers_a_comparison_fix_that_compiles():
    src = "fact limit(u, 5)\nallow can_x(U, R):\n    limit(U, L)\n    L = 5\n"
    d = diag(src)
    assert d.code == "unexpected_character" and d.fix is not None
    lines = src.splitlines()
    lines[d.fix["line"] - 1] = d.fix["replace"]
    assert adapter.compile_info("\n".join(lines) + "\n").ok


def test_single_equals_outside_a_body_does_not_offer_a_wrong_fix():
    d = diag("fact limit(u) = 5 = 6\n")
    assert d.fix is None or d.code == "old_fact_syntax"


def test_unknown_message_still_returns_a_diagnostic():
    from app.engine.diagnostics import classify
    d = classify("line 4: something new the engine says")
    assert d.code == "error" and d.line == 4 and d.message.endswith("the engine says")
