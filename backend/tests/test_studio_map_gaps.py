"""Policy Map and Gap Analyzer."""
import pytest

from app.studio.common import Budget, BudgetExceeded, shape
from app.studio.gaps import analyze, contradiction, shadows, targeted_probes
from app.studio.pmap import Axis, MapRequest, build_map, suggest
from tests.studio_helpers import DEMO, DEMO_TOOLS, adapter, client

A = adapter()


# ----------------------------------------------------------------------------- map
def grid(**kw):
    return build_map(A, DEMO, MapRequest(**kw), Budget())


def test_map_shows_the_night_band():
    m = grid(action="can_unlock_door", x=Axis(kind="hour"), y=Axis(kind="day"))
    assert len(m.cells) == 7 and all(len(r) == 24 for r in m.cells)
    for row in m.cells:
        assert "".join(row) == "DDDDDD" + "A" * 17 + "D"                 # denied 23:00-05:59, allowed in between
    assert (m.allow, m.deny) == (119, 49)
    assert m.x_title == "hour of day" and m.y_title == "day of week" and m.x_labels[3] == "03"


def test_map_with_an_argument_axis_and_one_row():
    m = grid(action="can_set_thermostat", x=Axis(kind="arg", tool="set_thermostat", param="temperature", values=[15, 16, 28, 29]))
    assert m.y_labels == [""] and m.cells == [["D", "A", "A", "D"]]


def test_map_two_axes_hour_by_argument():
    m = grid(action="can_open_valve", x=Axis(kind="hour"), y=Axis(kind="arg", tool="open_valve", param="percent", values=[10, 50, 51, 100]))
    assert m.cells[0][12] == "A" and m.cells[1][12] == "A" and m.cells[2][12] == "D" and m.cells[3][12] == "D"


def test_fixed_facts_are_replaced_by_the_axis_not_duplicated():
    m = grid(action="can_unlock_door", context=["hour(now, 3)"], x=Axis(kind="hour"))
    assert m.cells[0][12] == "A"                                         # the axis hour wins over the fixed hour(now, 3)


def test_map_rejects_bad_axes_and_big_grids():
    with pytest.raises(ValueError):
        grid(action="can_unlock_door", x=Axis(kind="hour"), y=Axis(kind="hour"))
    with pytest.raises(ValueError):
        grid(action="can_unlock_door", x=Axis(kind="arg"))
    with pytest.raises(BudgetExceeded):
        build_map(A, DEMO, MapRequest(action="can_unlock_door", x=Axis(kind="hour"), y=Axis(kind="day")), Budget(50))


def test_suggest_lists_what_the_policy_mentions():
    s = suggest(shape(A.program_info(DEMO)))
    assert "can_unlock_door" in s.actions and s.uses_hour and s.actors == ["agent"]
    assert {(k.tool, k.param) for k in s.arg_keys} == {("set_thermostat", "temperature"), ("open_valve", "percent")}
    assert 28 in s.arg_keys[0].values


def test_map_api():
    c = client()
    s = c.post("/studio/map/suggest", json={"policy_id": "demo"}).json()
    assert s["uses_hour"] and s["policy_label"].startswith("demo")
    r = c.post("/studio/map", json={"policy_id": "demo", "action": "can_unlock_door", "x": {"kind": "hour"}, "y": {"kind": "day"}})
    assert r.status_code == 200 and r.json()["allow"] == 119 and r.json()["reasons"][0][3].startswith("deny clause")
    bad = c.post("/studio/map", json={"policy_id": "demo", "action": "can_unlock_door", "x": {"kind": "hour"}, "y": {"kind": "hour"}})
    assert bad.status_code == 422
    big = c.post("/studio/map", json={"policy_id": "demo", "action": "can_open_valve", "x": {"kind": "arg", "tool": "open_valve", "param": "percent", "values": list(range(61))}})
    assert big.status_code == 422                                       # more values than an axis may hold


# ----------------------------------------------------------------------------- gaps: pure helpers
def clause(src: str, n: int = 0) -> dict:
    return [c for c in A.program_info(src)["clauses"] if c["kind"] in ("allow", "deny")][n]


HEAD = "fact role(a, r)\nfact hour(placeholder, 0)\nfact arg(placeholder, placeholder, 0)\n"


def test_contradiction_finds_empty_ranges_and_conflicting_equalities():
    c = clause(HEAD + "allow can_x(U, R):\n    hour(now, H)\n    H > 10\n    H < 5\n")
    assert "at least 11 and at most 4" in contradiction(c)
    assert contradiction(clause(HEAD + "allow can_x(U, R):\n    hour(now, H)\n    H >= 5\n    H <= 5\n")) is None
    assert contradiction(clause(HEAD + "allow can_x(U, R):\n    hour(now, H)\n    H >= 5\n    H <= 5\n    H != 5\n"))
    assert "equal" in contradiction(clause(HEAD + "allow can_x(U, R):\n    hour(now, H)\n    H == 3\n    H == 4\n"))
    assert contradiction(clause(HEAD + "allow can_x(U, R):\n    hour(now, H)\n    H >= 3\n    H == 1\n"))
    assert contradiction(clause(HEAD + "allow can_x(U, R):\n    hour(now, H)\n    3 < H\n    H < 5\n")) is None      # H = 4 exists


def test_flipped_comparison_sides_are_understood():
    assert contradiction(clause(HEAD + "allow can_x(U, R):\n    hour(now, H)\n    10 < H\n    H < 5\n"))


def test_shadows_needs_a_subset_of_conditions():
    allow = clause(HEAD + "allow can_x(U, R):\n    role(U, r)\n    hour(now, H)\n    H > 3\n", 0)
    deny_sub = clause(HEAD + "deny can_x(A, B):\n    hour(now, T)\n    T > 3\n", 0)
    deny_more = clause(HEAD + "deny can_x(U, R):\n    role(U, r)\n    hour(now, H)\n    H > 3\n    H < 9\n", 0)
    assert shadows(deny_sub, allow)                                      # variables renamed, conditions a subset
    assert not shadows(deny_more, allow)                                 # the deny asks for more than the allow does
    other_action = clause(HEAD + "deny can_y(U, R):\n    hour(now, H)\n    H > 3\n", 0)
    assert not shadows(other_action, allow)


def test_shadows_respects_constant_heads():
    allow = clause(HEAD + "allow can_x(U, vault):\n    role(U, r)\n", 0)
    deny_desk = clause(HEAD + "deny can_x(U, desk):\n    role(U, r)\n", 0)
    deny_any = clause(HEAD + "deny can_x(U, R):\n    role(U, r)\n", 0)
    assert not shadows(deny_desk, allow) and shadows(deny_any, allow)


# ----------------------------------------------------------------------------- gaps: report
def findings(src, **kw):
    return {f.id: f for f in analyze(A, src, **kw).findings}


def test_demo_policy_has_no_proved_problems_and_full_clause_coverage():
    r = analyze(A, DEMO, tools=DEMO_TOOLS)
    assert [f for f in r.findings if f.certainty == "proved" and f.severity == "warning"] == []
    assert r.governed == r.total == 5 and r.coverage_pct == 100.0 and r.clause_coverage_pct == 100.0
    assert all(c.matched > 0 for c in r.clauses)


def test_regression_coverage_is_unknown_not_100_without_the_tool_list():
    """The scorecard used to say '5 of 5 tools covered' for a policy whose agent was never uploaded."""
    r = analyze(A, DEMO)
    assert r.coverage_pct is None and r.clause_coverage_pct == 100.0


def test_uncovered_tool_and_coverage_percent():
    r = analyze(A, DEMO, tools=DEMO_TOOLS + ["delete_all"])
    f = next(x for x in r.findings if x.id == "uncovered_tool")
    assert "delete_all" in f.title and f.certainty == "proved" and (r.governed, r.total) == (5, 6) and r.coverage_pct == 83.3


def test_demo_policy_fails_open_without_context():
    f = findings(DEMO)
    assert f["fails_open"].certainty == "heuristic" and f["fails_open"].severity == "warning"


def test_every_finding_kind_on_a_deliberately_bad_policy():
    bad = HEAD + ("allow can_x(U, R):\n    role(U, r)\n"            # 4: duplicated below, and shadowed by the deny
                  "allow can_x(U, R):\n    role(U, r)\n"            # 6
                  "deny can_x(U, R):\n    role(U, r)\n"             # 8
                  "deny can_y(U, R):\n    hour(now, H)\n    H > 10\n    H < 5\n"       # 10: dead, and can_y can never be allowed
                  "fact lonely(a, b)\n"
                  "rule unused_rule(U):\n    role(U, r)\n")
    f = findings(bad)
    for kind in ("shadowed_allow", "duplicate_clause", "never_allowed", "dead_clause", "unused_fact", "unused_rule"):
        assert kind in f, kind
    assert f["dead_clause"].lines == [10] and f["never_allowed"].action == "can_y"
    assert f["unused_fact"].certainty == "heuristic" and f["shadowed_allow"].certainty == "proved"


def test_untested_clause_is_reported_when_probes_never_reach_it():
    pol = HEAD + "allow can_x(U, R):\n    role(U, r)\n    hour(now, H)\n    H > 100\n"
    r = analyze(A, pol, scenarios=[])
    # H > 100 is reachable by the boundary probe 101; with an explicit scenario list that skips it, it is not
    from app.evaluate.scenarios import Scenario
    only = [Scenario(actor="a", action="can_x", resource="r", context=["hour(now, 3)"], expected="DENY")]
    r2 = analyze(A, pol, scenarios=only)
    assert any(f.id == "untested_clause" for f in r2.findings) and r2.clause_coverage_pct == 0.0
    assert r.probes > r2.probes


def test_targeted_probes_stay_within_caps_and_cover_each_action():
    probes = targeted_probes(shape(A.program_info(DEMO)))
    assert {p[1] for p in probes} == set(shape(A.program_info(DEMO)).actions)
    assert len(probes) <= 5 * 60


def test_gaps_api():
    c = client()
    r = c.post("/studio/gaps", json={"policy_id": "demo", "tools": ["unlock_door", "nope"]})
    j = r.json()
    assert r.status_code == 200 and j["coverage_pct"] == 50.0 and "can_unlock_door" in j["source"]
    assert any(f["id"] == "uncovered_tool" for f in j["findings"])
    assert c.post("/studio/gaps", json={"policy_id": "demo", "tools": ["t"] * 101}).status_code == 422
