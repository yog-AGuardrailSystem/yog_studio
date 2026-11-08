"""The real C lexer side by side with the Python reference.

Two kinds of test live here, deliberately kept apart:

* Logic tests use a TEST DOUBLE for the lexdump process (patched subprocess.run). They prove our parsing, kind
  mapping, comparison, timeout and error handling. They do NOT prove anything about the real C lexer.
* `real_binary` tests build and run the engine team's actual lexdump. They skip when no C compiler is available
  (e.g. on a locked-down Windows laptop) and run for real in CI, where gcc exists.
"""
import random
import subprocess

import pytest

from app.core.team_examples import TEAM_FILE, load_groups
from app.engine import c_lexer
from app.engine.c_lexer import KNOWN_DIFFERENCES, compare, find_binary, parse_dump, run_c_lexer
from app.engine.python_prototype import PythonPrototypeAdapter

adapter = PythonPrototypeAdapter()

DUMP = """1:1 FACT
1:6 IDENT role
1:10 LPAREN
1:11 IDENT alice
1:16 COMMA
1:18 IDENT admin
1:23 RPAREN
1:24 NEWLINE
2:1 ALLOW
2:7 IDENT can_x
2:12 LPAREN
2:13 VAR U
2:14 RPAREN
2:15 COLON
2:16 NEWLINE
3:5 INDENT
3:5 VAR L
3:7 LTE
3:10 INT -7
3:12 STRING hi there
3:20 WILDCARD
3:21 NEWLINE
4:1 DEDENT
4:1 EOF
"""


def py_tokens(source):
    return [(t.kind, t.value, t.line) for t in adapter.compile_info(source).tokens]


# ------------------------------------------------------------------ logic, with a test double
def test_parse_dump_maps_c_types_to_reference_kinds():
    toks = parse_dump(DUMP)
    by = [(t.kind, t.value) for t in toks]
    assert by[0] == ("KW", "fact") and by[1] == ("IDENT", "role") and by[2] == ("(", "(")
    assert ("VAR", "U") in by and (":", ":") in by
    assert ("OP", "<=") in by and ("INT", -7) in by and ("STR", "hi there") in by and ("WILD", None) in by
    assert toks[-1].kind == "EOF" and toks[7].c_type == "NEWLINE"
    assert toks[0].line == 1 and toks[0].column == 1


def test_parse_dump_ignores_non_token_lines():
    assert parse_dump("garbage\n\n") == []


def test_compare_reports_the_first_difference_and_length_gaps():
    c = parse_dump("1:1 FACT\n1:6 IDENT a\n1:7 EOF\n")
    same = [("KW", "fact", 1), ("IDENT", "a", 1), ("EOF", None, 1)]
    assert compare(c, same) == (3, [])
    differ = [("KW", "fact", 1), ("IDENT", "b", 1), ("EOF", None, 1)]
    n, m = compare(c, differ)
    assert n == 3 and len(m) == 1 and (m[0].index, m[0].python, m[0].c) == (1, "IDENT:b", "IDENT:a")
    n, m = compare(c, same[:2])
    assert any(x.python == "<missing>" for x in m)


def _fake_run(monkeypatch, stdout="", stderr="", code=0, raises=None):
    monkeypatch.setattr(c_lexer, "find_binary", lambda build=True: c_lexer.Path("lexdump"))

    def fake(cmd, **kw):
        if raises:
            raise raises
        return subprocess.CompletedProcess(cmd, code, stdout, stderr)
    monkeypatch.setattr(c_lexer.subprocess, "run", fake)


def test_run_c_lexer_success_compares_with_python(monkeypatch):
    _fake_run(monkeypatch, DUMP)
    toks = parse_dump(DUMP)
    res = run_c_lexer("anything", [(t.kind, t.value, t.line) for t in toks])
    assert res.available and res.ok and res.compared == len(toks) and res.mismatches == []
    assert res.known_differences == KNOWN_DIFFERENCES


def test_run_c_lexer_lexical_error_is_reported_not_raised(monkeypatch):
    _fake_run(monkeypatch, "", "input.yog:2:9: lexical error: tabs are not allowed", code=1)
    res = run_c_lexer("x")
    assert res.available and not res.ok and "tabs are not allowed" in res.reason


def test_run_c_lexer_timeout(monkeypatch):
    _fake_run(monkeypatch, raises=subprocess.TimeoutExpired("lexdump", 5))
    res = run_c_lexer("x")
    assert res.available and not res.ok and "did not finish" in res.reason


def test_run_c_lexer_oversized_input_is_refused_before_running(monkeypatch):
    called = []
    monkeypatch.setattr(c_lexer, "find_binary", lambda build=True: called.append(1))
    res = run_c_lexer("x" * (c_lexer.MAX_SOURCE_BYTES + 1))
    assert not res.available and "larger than" in res.reason and not called


def test_run_c_lexer_without_a_binary_says_so(monkeypatch):
    monkeypatch.setattr(c_lexer, "find_binary", lambda build=True: None)
    res = run_c_lexer("fact a(b)\n")
    assert not res.available and "not built" in res.reason


def test_vendored_c_front_is_pinned_and_licensed():
    base = c_lexer.C_FRONT
    assert (base / "VERSION").read_text().count("commit:") == 1
    assert "MIT" in (base / "LICENSE").read_text()
    for f in ("src/lexer/lexer.c", "src/lexer/lexer.h", "src/lexer/token.h", "tools/lexdump.c"):
        assert (base / f).is_file(), f


def test_kind_map_covers_every_token_the_c_lexer_defines():
    header = (c_lexer.C_FRONT / "src" / "lexer" / "token.h").read_text()
    import re
    names = re.findall(r'X\(TOK_\w+,\s+"(\w+)"\)', header)
    assert names, "could not read the token table"
    assert [n for n in names if n not in c_lexer.KIND_MAP and n != "ERROR"] == [], "unmapped C token type"


# ------------------------------------------------------------------ the real C lexer (skips without a compiler)
real_binary = pytest.mark.skipif(find_binary() is None, reason="no C compiler / lexdump on this machine (runs in CI)")


def _both(source):
    res = run_c_lexer(source, py_tokens(source))
    assert res.available, res.reason
    return res


@real_binary
@pytest.mark.parametrize("group", load_groups(), ids=[g.id for g in load_groups()])
def test_real_c_lexer_matches_python_on_each_team_group(group):
    res = _both(group.source)
    assert res.ok, res.reason
    assert res.mismatches == [], [m.model_dump() for m in res.mismatches[:5]]
    assert res.compared > 20


@real_binary
def test_real_c_lexer_matches_python_on_the_whole_team_file():
    res = _both(TEAM_FILE.read_text(encoding="utf-8"))
    assert res.ok and res.compared == 1137 and res.mismatches == []


@real_binary
def test_real_c_lexer_rejects_a_tab_as_documented():
    res = run_c_lexer("allow can_x(U, R):\n\trole(U, a)\n")
    assert res.available and not res.ok and res.reason


@pytest.mark.c_differential
@real_binary
def test_real_c_lexer_differential_on_mutated_programs():
    """Like the engine team's own differential test: mutate real programs and require both lexers to agree on
    every input they BOTH accept. Mutations use printable ASCII + newlines only, so the documented differences
    (tabs, non-ASCII, >64-bit integers, >63 indent levels) cannot explain a mismatch. Any failure here is a real
    finding for docs/engine_issues.md."""
    rng = random.Random(20261108)
    base = [g.source for g in load_groups()]
    alphabet = list("abcXYZ_09 \n(),:#\"=!<>-.")
    both_ok = disagreements = 0
    findings: list[str] = []
    for _ in range(400):
        s = list(rng.choice(base))
        for _ in range(rng.randint(1, 4)):
            op, pos = rng.choice(("del", "ins", "dup")), rng.randrange(len(s))
            if op == "del":
                del s[pos]
            elif op == "ins":
                s.insert(pos, rng.choice(alphabet))
            else:
                s[pos:pos] = s[max(0, pos - 20):pos]
        src = "".join(s)
        py_ok = bool(adapter.compile_info(src).tokens)          # tokens exist only if the reference tokenizer accepted
        res = run_c_lexer(src, py_tokens(src) if py_ok else None)
        if res.ok and py_ok:
            both_ok += 1
            if res.mismatches:
                findings.append(f"token mismatch {res.mismatches[0].model_dump()} in {src[:60]!r}")
        elif res.ok != py_ok:
            disagreements += 1
            findings.append(f"acceptance differs: C ok={res.ok} ({res.reason}) python ok={py_ok} in {src[:60]!r}")
    assert both_ok > 50, "mutations were too destructive to compare anything"
    assert findings == [], f"{len(findings)} finding(s); first: {findings[0]}"
