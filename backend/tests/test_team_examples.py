"""The team's all_examples.yog: split into standalone groups, and verified against the engine."""
import re

import pytest

from app.api.compile import parse_expectation
from app.core.team_examples import TEAM_FILE, load_groups
from app.engine.python_prototype import PythonPrototypeAdapter

adapter = PythonPrototypeAdapter()
GROUPS = load_groups()
WHOLE = TEAM_FILE.read_text(encoding="utf-8")


def _decisions(source: str) -> dict[tuple[str, str, str], str]:
    """(actor, predicate, resource) -> decision for every 2-argument decision query in a program."""
    out = {}
    info = adapter.compile_info(source)
    roles = {(p.name, p.arity): p.role for p in info.predicates}
    for q in adapter.queries(source):
        if len(q.terms) == 2 and roles.get((q.pred, 2)) == "decision":
            a, r = q.terms[0]["const"], q.terms[1]["const"]
            out[(a, q.pred, r)] = adapter.check(source, a, q.pred, r, []).decision
    return out


def test_the_file_is_split_into_the_expected_groups():
    ids = [g.id for g in GROUPS]
    assert ids == list("ABCDEFGHIJKL") + ["M/N/O/P/Q", "R"]


def test_titles_are_clean_and_every_group_has_plain_english():
    for g in GROUPS:
        assert ".md" not in g.title, f"{g.id}: team source-doc reference leaked into the title: {g.title!r}"
        assert g.title and g.english, g.id


def test_the_whole_file_compiles_with_no_diagnostics():
    info = adapter.compile_info(WHOLE)
    assert info.ok and not info.diagnostics
    assert len(info.ast["facts"]) == 48 and len(info.ast["clauses"]) == 26 and len(info.ast["queries"]) == 25


@pytest.mark.parametrize("group", GROUPS, ids=[g.id for g in GROUPS])
def test_each_group_compiles_on_its_own(group):
    info = adapter.compile_info(group.source)
    assert info.ok, [d.message for d in info.diagnostics]


def test_group_queries_add_up_to_the_whole_file():
    assert sum(g.queries for g in GROUPS) == 25


def test_groups_alone_decide_exactly_like_the_whole_file():
    """The team warns that reusing a predicate name across groups would silently OR their rules together.
    If that ever happened, a group alone and the whole file would disagree here."""
    whole = _decisions(WHOLE)
    assert whole, "no decision queries found"
    for g in GROUPS:
        for key, decision in _decisions(g.source).items():
            assert whole[key] == decision, f"group {g.id}: {key} -> {decision} alone but {whole[key]} in the whole file"


def test_every_query_the_team_annotated_agrees_with_the_engine():
    """Comments such as '# staging -> expect TRUE' are the team's own expected results (13 of them)."""
    lines = WHOLE.splitlines()
    info = adapter.compile_info(WHOLE)
    assert info.ok
    checked = 0
    for q in adapter.queries(WHOLE):
        expected = parse_expectation(lines[q.line - 1])
        if expected is None:
            continue
        got = adapter.check(WHOLE, q.terms[0]["const"], q.pred, q.terms[1]["const"], []).decision
        assert got == expected, f"line {q.line}: {q.text} -> {got}, the team's comment says {expected}"
        checked += 1
    assert checked == 13


def test_group_i_needs_context_and_gets_the_right_answers():
    """Transfers depend on the amount of each request: injected as a context fact, not stored in the policy."""
    g = next(x for x in GROUPS if x.id == "I")
    assert g.uses_context and g.queries == 0
    ok = adapter.check(g.source, "i_customer", "can_transfer", "i_acct_999", ["amount(i_acct_999, 9000)"])
    no = adapter.check(g.source, "i_customer", "can_transfer", "i_acct_999", ["amount(i_acct_999, 50000)"])
    assert (ok.decision, no.decision) == ("ALLOW", "DENY")


def test_group_r_deny_overrides_allow():
    g = next(x for x in GROUPS if x.id == "R")
    assert adapter.check(g.source, "r_alice", "can_access", "normal_doc", []).decision == "ALLOW"
    r = adapter.check(g.source, "r_alice", "can_access", "payroll_doc", [])
    assert r.decision == "DENY" and "deny clause" in r.reason


def test_the_vendored_file_matches_its_recorded_commit_note():
    version = (TEAM_FILE.parent / "VERSION").read_text(encoding="utf-8")
    assert re.search(r"commit: [0-9a-f]{40}", version)
