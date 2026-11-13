"""POST /compile, /run, /compile/c-lexer, GET /examples/team, GET /info, and the bundle guard."""
import os
from fastapi.testclient import TestClient

from app.core.team_examples import TEAM_FILE, load_groups
from app.main import app

client = TestClient(app)
WHOLE = TEAM_FILE.read_text(encoding="utf-8")


def compile_(source):
    r = client.post("/compile", json={"source": source})
    assert r.status_code == 200, r.text
    return r.json()


def run(source, **kw):
    r = client.post("/run", json={"source": source, **kw})
    assert r.status_code == 200, r.text
    return r.json()


# ---------------------------------------------------------------- /compile
def test_compile_returns_tokens_ast_and_predicates():
    j = compile_("fact role(alice, admin)\nallow can_x(U, R):\n    role(U, admin)\nquery can_x(alice, db)\n")
    assert j["ok"] and j["diagnostics"] == []
    kinds = [t["kind"] for t in j["tokens"]]
    assert kinds[:7] == ["KW", "IDENT", "(", "IDENT", ",", "IDENT", ")"]
    assert kinds[-1] == "EOF" and "INDENT" in kinds and "DEDENT" in kinds
    assert j["ast"]["facts"][0] == {"pred": "role", "args": [{"const": "alice"}, {"const": "admin"}], "line": 1}
    clause = j["ast"]["clauses"][0]
    assert clause["kind"] == "allow" and clause["head"]["pred"] == "can_x" and clause["body"][0]["type"] == "atom"
    assert j["ast"]["queries"][0]["pred"] == "can_x"
    assert {(p["name"], p["role"]) for p in j["predicates"]} == {("role", "fact"), ("can_x", "decision")}


def test_compile_represents_negation_comparison_and_wildcards():
    src = ("fact limit(u, 5)\nfact blocked(u)\nallow can_x(U, R):\n    limit(U, L)\n    not blocked(U)\n"
           "    L >= 3\n    limit(_, _)\n")
    j = compile_(src)
    assert j["ok"], j["diagnostics"]
    body = j["ast"]["clauses"][0]["body"]
    assert [b["type"] for b in body] == ["atom", "not", "cmp", "atom"]
    assert body[2]["op"] == ">=" and body[2]["lhs"] == {"var": "L"} and body[2]["rhs"] == {"const": 3}
    assert body[3]["args"] == [{"wildcard": True}, {"wildcard": True}]


def test_compile_error_returns_a_friendly_diagnostic_and_keeps_tokens():
    j = compile_("fact role(alice, admin)\nallow can_x(U, R)\n    role(U, admin)\n")
    assert not j["ok"] and j["ast"] is None
    d = j["diagnostics"][0]
    assert d["code"] == "expected_token" and d["line"] == 2 and "colon" in d["hint"]
    assert j["tokens"], "tokens are still returned when the parse fails"


def test_compile_tokenizer_error_has_no_tokens_but_a_diagnostic():
    j = compile_('fact role(a, "oops)\n')
    assert not j["ok"] and j["tokens"] == [] and j["diagnostics"][0]["code"] == "unterminated_string"


def test_compile_semantic_error_still_returns_the_ast():
    j = compile_("fact role(a, admin)\nallow can_x(U, R):\n    rol(U, admin)\n")
    assert not j["ok"] and j["ast"] is not None
    d = j["diagnostics"][0]
    assert d["code"] == "undefined_predicate" and d["line"] == 3 and d["suggestion"] == "Did you mean role/2?"


def test_compile_empty_source_is_ok():
    j = compile_("")
    assert j["ok"] and [t["kind"] for t in j["tokens"]] == ["EOF"]


def test_compile_rejects_oversized_source():
    r = client.post("/compile", json={"source": "x" * 200_001})
    assert r.status_code == 422


# ---------------------------------------------------------------- /run
def test_run_the_whole_team_file():
    j = run(WHOLE)
    assert j["ok"] and len(j["results"]) == 25
    assert j["passed"] == 13 and j["failed"] == 0 and j["untested"] == 12
    by_text = {r["text"]: r for r in j["results"]}
    assert by_text["can_delete(a_admin, database_1)"]["decision"] == "ALLOW"
    assert by_text["can_delete(a_agent, database_1)"]["decision"] == "DENY"
    assert by_text["can_access(r_alice, payroll_doc)"]["reason"].startswith("deny clause")
    assert by_text["can_access(r_alice, payroll_doc)"]["trace"], "a decision carries its trace"


def test_run_flags_a_failing_expectation():
    src = "fact role(a, dev)\nallow can_x(U, R):\n    role(U, admin)\nquery can_x(a, db)   # -> expect ALLOW\n"
    j = run(src)
    r = j["results"][0]
    assert r["decision"] == "DENY" and r["expected"] == "ALLOW" and r["passed"] is False
    assert (j["passed"], j["failed"]) == (0, 1)


def test_run_deny_beats_allow_even_for_queries():
    """The engine's plain query ignores DENY (engine_issues.md). /run must go through check()."""
    src = ("fact employee(al)\nfact confidential(doc)\nallow can_access(U, D):\n    employee(U)\n"
           "deny can_access(U, D):\n    employee(U)\n    confidential(D)\nquery can_access(al, doc)\n")
    assert run(src)["results"][0]["decision"] == "DENY"


def test_run_plain_queries_return_bindings():
    src = "fact role(alice, admin)\nfact role(bob, dev)\nquery role(X, admin)\nquery role(carol, admin)\n"
    a, b = run(src)["results"]
    assert a["kind"] == "fact-query" and a["answer"] is True and a["bindings"] == [{"X": "alice"}]
    assert b["answer"] is False and b["reason"] == "does not hold"


def test_run_decision_query_with_wrong_shape_is_unsupported_not_an_error():
    src = "fact role(a, admin)\nallow can_x(U, R):\n    role(U, admin)\nquery can_x(X, db)\n"
    r = run(src)["results"][0]
    assert r["kind"] == "unsupported" and "two constant arguments" in r["reason"]


def test_run_with_a_compile_error_returns_diagnostics_and_no_results():
    j = run("allow can_x(U, R)\n    role(U)\n")
    assert not j["ok"] and j["results"] == [] and j["diagnostics"]


def test_run_adhoc_check_with_context_facts_group_i():
    g = next(x for x in load_groups() if x.id == "I")
    adhoc = {"actor": "i_customer", "action": "can_transfer", "resource": "i_acct_999"}
    low = run(g.source, adhoc={**adhoc, "context": ["amount(i_acct_999, 9000)"]})["adhoc"]
    high = run(g.source, adhoc={**adhoc, "context": ["amount(i_acct_999, 50000)"]})["adhoc"]
    assert (low["decision"], high["decision"]) == ("ALLOW", "DENY")


def test_run_adhoc_bad_context_is_reported_not_raised():
    g = next(x for x in load_groups() if x.id == "I")
    j = run(g.source, adhoc={"actor": "i_customer", "action": "can_transfer", "resource": "r", "context": ["not a fact"]})
    assert j["adhoc"] is None and "bad context fact" in j["adhoc_error"]


# ---------------------------------------------------------------- /examples/team, /info, /compile/c-lexer
def test_team_examples_endpoint():
    j = client.get("/examples/team").json()
    assert len(j) == 14 and j[0]["id"] == "A" and "admin" in j[0]["english"].lower()
    assert all(g["source"].strip() for g in j)


def test_info_reports_the_offline_fake_provider():
    j = client.get("/info").json()
    assert j["provider"] == "fake" and j["offline_demo"] is True and j["engine"] == ("c" if os.environ.get("YOG_ENGINE") == "c" else "python-reference")


def test_c_lexer_endpoint_degrades_gracefully_without_a_binary(monkeypatch):
    monkeypatch.setattr("app.engine.c_lexer.find_binary", lambda build=True: None)
    j = client.post("/compile/c-lexer", json={"source": "fact role(a, b)\n"}).json()
    assert j["available"] is False and "not built" in j["reason"] and j["tokens"] == []


# ---------------------------------------------------------------- bundle guard
def test_bundle_refuses_the_offline_placeholder_policy(tmp_path, monkeypatch):
    from app.api.policies import get_store
    from app.policies.store import PolicyStore
    store = PolicyStore(tmp_path)
    placeholder = ("# OFFLINE FAKE PROVIDER: copied from the nearest example, not translated.\n"
                   "fact role(agent, assistant)\nallow can_read_file(Actor, Path):\n    role(Actor, assistant)\n")
    rec = store.save(placeholder)
    real = store.save("fact role(agent, assistant)\nallow can_read_file(Actor, Path):\n    role(Actor, assistant)\n")
    app.dependency_overrides[get_store] = lambda: store
    try:
        agent = "from mcp.server.fastmcp import FastMCP\nmcp = FastMCP('x')\n\n@mcp.tool()\ndef read_file(path: str) -> str:\n    return path\n"
        bad = client.post("/modify/bundle", json={"source": agent, "policy_id": rec.id})
        assert bad.status_code == 409 and "offline placeholder" in bad.json()["detail"]
        good = client.post("/modify/bundle", json={"source": agent, "policy_id": real.id})
        assert good.status_code == 200 and good.headers["content-type"] == "application/zip"
    finally:
        app.dependency_overrides.pop(get_store, None)


def test_regression_a_wildcard_query_is_answered_not_a_500():
    """`query role(_, admin)` crashed /run with a KeyError (the explorer sends wildcards as {"wildcard": true})."""
    r = client.post("/run", json={"source": "fact role(alice, admin)\nquery role(_, admin)\nquery role(X, _)\nquery role(_, user)\n"})
    assert r.status_code == 200, r.text
    res = [q for q in r.json()["results"] if q["kind"] == "fact-query"]
    assert [q["answer"] for q in res] == [True, True, False]
    assert res[0]["bindings"] == [] and res[1]["bindings"] == [{"X": "alice"}]
