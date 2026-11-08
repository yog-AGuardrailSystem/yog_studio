"""Turn the reference engine's raw error strings into friendly, structured diagnostics.

The engine only raises `YogError("line 7: expected :, got 'NEWLINE'")`-style text. We keep that text verbatim in
`Diagnostic.message` (so nothing is hidden) and add a stable `code`, a plain-English `hint`, and, where we can
be certain, a "did you mean" suggestion or a machine-applicable `fix`. The mapping is pattern based and covered by
tests/test_diagnostics.py against every message `engine/yog.py` can raise.
"""
import difflib
import re

from app.engine.adapter import Diagnostic

_LINE = re.compile(r"^line (\d+):\s*(.*)$", re.S)


def _split(message: str) -> tuple[int | None, str]:
    m = _LINE.match(message)
    return (int(m.group(1)), m.group(2)) if m else (None, message)


def _closest(name: str, arity: int | None, known: dict[tuple[str, int], str]) -> str | None:
    """Best 'did you mean' among defined predicates. Same arity is preferred."""
    pool = [k for k in known if arity is None or k[1] == arity] or list(known)
    names = {n for n, _ in pool}
    near = difflib.get_close_matches(name, sorted(names), n=1, cutoff=0.6)
    if not near:
        return None
    arity_of = next(a for n, a in pool if n == near[0])
    return f"{near[0]}/{arity_of}"


def _locate(line: int | None, needle: str, source_lines: list[str] | None) -> int | None:
    """The engine reports semantic errors at the clause head. Point at the exact body line matching `needle`."""
    if not source_lines or not line or not (1 <= line <= len(source_lines)):
        return line
    for i in range(line - 1, len(source_lines)):
        text = source_lines[i]
        if i > line - 1 and text.strip() and not text[:1].isspace():
            break                                             # next top-level statement: stop
        if re.search(needle, text.split("#", 1)[0]):
            return i + 1
    return line


def classify(message: str, known: dict[tuple[str, int], str] | None = None,
             source_lines: list[str] | None = None) -> Diagnostic:
    """`known` maps (predicate, arity) -> role for 'did you mean'. `source_lines` lets a fix target exact text."""
    known = known or {}
    line, body = _split(message)

    def d(code: str, hint: str | None = None, suggestion: str | None = None, fix: dict | None = None) -> Diagnostic:
        return Diagnostic(code=code, line=line, message=message, hint=hint, suggestion=suggestion, fix=fix)

    if body.startswith("inconsistent indentation"):
        return d("bad_indentation",
                 "Every condition under a rule, allow or deny must be indented by the same number of spaces "
                 "(4 is conventional). Tabs are not allowed: use spaces.")
    if body.startswith("unterminated string"):
        return d("unterminated_string", "A quoted value needs a closing double quote on the same line.")
    m = re.match(r"unexpected character (.+)$", body)
    if m:
        ch = m.group(1).strip("'\"")
        if ch == "=":
            text = source_lines[line - 1] if source_lines and line and 1 <= line <= len(source_lines) else ""
            # The older design docs wrote facts as `fact role(alice) = admin`. Offer the exact rewrite.
            old = re.match(r"^(\s*)fact\s+(\w+)\(([^()]*)\)\s*=\s*(\S+)\s*(#.*)?$", text)
            if old:
                indent, pred, args, val = old.group(1), old.group(2), old.group(3).strip(), old.group(4)
                new = f"{indent}fact {pred}({args}, {val})" + (f"  {old.group(5)}" if old.group(5) else "")
                return d("old_fact_syntax",
                         "This is the older `fact role(alice) = admin` form. In YOG the value is just another "
                         f"argument: `fact {pred}({args}, {val})`.",
                         fix={"line": line, "find": text, "replace": new})
            fix = None
            if text[:1].isspace():                              # inside a body: it was meant as a comparison
                at = [i for i, c in enumerate(text) if c == "=" and text[i - 1:i] not in ("=", "!", "<", ">")
                      and text[i + 1:i + 2] != "="]
                if len(at) == 1:
                    fix = {"line": line, "find": text, "replace": text[:at[0]] + "==" + text[at[0] + 1:]}
            return d("unexpected_character",
                     "A single = is not an operator in YOG. Use == to compare two values. Facts are written "
                     "like `fact role(alice, admin)`, with no equals sign.", fix=fix)
        if ch == "!":
            return d("unexpected_character",
                     "Use != for 'not equal'. To negate a whole condition, put `not` in front of it.")
        if ch == ";":
            return d("unexpected_character", "YOG statements end at the end of the line; remove the semicolon.")
        return d("unexpected_character", f"The character {ch!r} is not part of YOG.")
    if body.startswith("expected a term"):                  # must precede the generic "expected X, got Y"
        return d("expected_term", "An argument was expected here: a name, a quoted string, a number, a variable or _.")
    m = re.match(r"expected (.+?), got (.+)$", body)
    if m:
        want, got = m.group(1).strip(), m.group(2).strip()
        if want == ":":
            return d("expected_token",
                     "The head of a rule, allow or deny ends with a colon. The conditions go on the next lines, "
                     "indented.")
        if want == "NEWLINE":
            return d("expected_token",
                     "Put each fact, query and condition on its own line (something extra follows this one).")
        if want == "INDENT":
            return d("expected_token", "The conditions must be indented below their head line.")
        if want == "(":
            return d("expected_token", "A predicate needs parentheses around its arguments: role(User, admin).")
        if want == ")":
            return d("expected_token", "A closing parenthesis is missing, or two arguments are not separated by a comma.")
        if want == "IDENT":
            if got[:1] in ("'",) and got.strip("'")[:1].isupper():
                return d("expected_token", f"Predicate names must start with a lowercase letter (found {got}). "
                                           "Capitalised names are variables.")
            return d("expected_token", "A predicate name was expected here (lowercase, like role or can_delete).")
        if want == "KW":
            return d("expected_token",
                     "Each statement starts with fact, rule, allow, deny or query. Conditions belong on indented "
                     "lines under a head.")
        return d("expected_token", f"Expected {want} here but found {got}.")
    m = re.match(r"unexpected keyword (.+)$", body)
    if m:
        return d("unexpected_keyword",
                 f"{m.group(1)} cannot start a statement. Use fact, rule, allow, deny or query; "
                 "`not` only goes in front of a condition inside a body.")
    if body.startswith("facts must be ground"):
        return d("fact_not_ground",
                 "A fact states concrete data, so it cannot contain variables (names that start with a capital "
                 "letter). Use lowercase names, or write a rule/allow clause instead.")
    if body.startswith("empty rule body"):
        return d("empty_body", "A rule, allow or deny needs at least one condition on an indented line below it.")
    m = re.match(r"predicate (\S+?)/(\d+) (is both a fact and a rule head|is both a fact and a decision head|"
                 r"is both a rule and a decision head); pick one role for it", body)
    if m:
        return d("predicate_role_conflict",
                 f"{m.group(1)}/{m.group(2)} plays two roles. Each predicate is exactly one of: data (fact), "
                 "derived (rule) or decision (allow/deny). Rename one of them.")
    m = re.match(r"variable (\S+) in head of (\S+) is never bound by the body", body)
    if m:
        return d("unbound_head_variable",
                 f"In a rule, every variable in the head must appear in a condition below it, but {m.group(1)} "
                 f"does not. Add a condition that mentions {m.group(1)}.")
    m = re.match(r"unbound variable\(s\) (\[.*?\]) inside `not`", body)
    if m:
        line = _locate(line, r"\bnot\b", source_lines)
        return d("unbound_in_not",
                 f"Variables inside `not` must already be bound by an earlier condition ({m.group(1)}). "
                 "Move the `not` line below the line that binds them.")
    m = re.match(r"unbound variable\(s\) (\[.*?\]) in comparison", body)
    if m:
        line = _locate(line, r"(==|!=|<=|>=|<|>)", source_lines)
        return d("unbound_in_comparison",
                 f"A comparison can only use variables that an earlier condition has bound ({m.group(1)}). "
                 "Put the line that binds them above the comparison.")
    m = re.match(r"(\S+?)/(\d+) is not defined by any fact or rule", body)
    if m:
        name, arity = m.group(1), int(m.group(2))
        near = _closest(name, arity, known)
        line = _locate(line, r"\b" + re.escape(name) + r"\(", source_lines)
        return d("undefined_predicate",
                 f"{name}/{arity} is used here but nothing defines it. Add a fact or rule for it, or fix the spelling.",
                 suggestion=f"Did you mean {near}?" if near else None)
    if body.startswith("rule cycle"):
        return d("rule_cycle",
                 "Rules may not depend on themselves, directly or through other rules (YOG guarantees every "
                 "question terminates). Break the loop by removing one of the dependencies.")
    if body.startswith("syntax error"):
        return d("syntax_error", "The file ended unexpectedly. Check for an unfinished statement or a missing ).")
    return d("error", None)
