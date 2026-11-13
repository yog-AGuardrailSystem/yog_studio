# Engine issues found by Studio (for the engine team)

Studio does not patch `engine/yog.py`; it works around these and records them here.

| # | Issue | Studio workaround |
|---|---|---|
| 1 | `query` ignores DENY clauses; only `Engine.check()` applies DENY > ALLOW. | Studio always calls `check()`, never `ask()`. |
| 2 | The `__main__` demo in `yog.py` passes `delete`/`deploy`/`transfer` instead of the decision predicate names (`can_delete`, ...). | Not used by Studio. |
| 3 | Decision predicates take exactly `(Actor, Resource)`. Tool arguments and time can only reach a policy as per-request context facts. | Convention: `hour(now, H)`, `arg(<tool>, <param>, V)` (see `docs/conventions.md`). |
| 4 | A context fact whose predicate is not defined by any `fact`/`rule` in the policy makes `check_program` fail (C4) when a clause uses it. | Policies that read context facts declare a placeholder base fact, e.g. `fact hour(placeholder, 0)`. |
| 5 | Grammar is not formally frozen. | If generated YOG starts failing after an engine update, check the grammar first. |
| 6 | Wildcard counter `Parser._wild` is class-level state shared across parses. | Harmless for Studio; noted. |
| 7 | ANY comparison (even `==`) between an integer and a name raises an uncaught `TypeError` inside `Engine.solve` because it evaluates all six operators eagerly. Found when a probe supplied `arg(t, currency, 0)` to a policy that compares `C == usd`. | `PythonPrototypeAdapter.check` catches it and returns DENY (fail closed) with an explanatory reason. A regression test covers it. |
| 8 | The engine repo README is out of date (describes an older plan). | Studio's docs describe the code, not the README. | 
| 9 | No tool prints the C parser's tree, so the explorer cannot show the C parser next to the reference. A `parsedump` like the existing `lexdump` would let it. | Explorer compares tokens only (C lexer vs reference). |
| 10 | Documented lexer differences between C and the reference (64-bit integers, indent depth 63, ASCII identifiers, tabs rejected, columns tracked). | Listed in `KNOWN_DIFFERENCES` and not reported as mismatches; anything else is. |

## C engine at `main` 200e481 (found while wiring `yogc` into Studio, Nov 2026)

Studio runs `yogc` as a subprocess (`backend/app/engine/c_engine.py`); the vendored sources are `engine/c_front/`. A branch `feature/compiler-backend` (12f1b2e, "0.1.0 alpha") adds `yogc validate`/`explain`, evaluation limits and security/fuzz tests; Studio is pinned to `main` and has not been tested against the alpha. #9 and #10 above are partly answered: the C pipeline now exists, but there is still no parse-tree dump, and the lexer differences stand.

| # | Issue | Studio workaround |
|---|---|---|
| 11 | **`;` splitting (security).** `compile_context` (`src/api/yog.c`) replaces EVERY `;` in the request context with a newline, including inside quoted strings. `arg(t,p,"x; fact role(agent, admin)")` therefore adds a second fact: an authority fact chosen by whoever controls an argument value. The alpha's SECURITY.md says context "must be trusted". | The adapter parses each context item with the reference parser (exactly one ground fact), re-serialises it canonically and refuses values containing `"` `\` `;` `|` or control characters (DENY, "failing closed"). Regression tests: `tests/test_c_engine.py`. Upstream fix wanted: escape or reject `;` inside strings, or take facts as a list. |
| 12 | **`yogc batch` line protocol.** Splits on `|` and whitespace and reads lines with a 4096-byte buffer: a longer line becomes two requests and every later answer shifts. | Values with whitespace, `|`, `--` prefix or over 3500 bytes go through argv `yogc check`; response count is checked and any mismatch is DENY for the whole batch. |
| 13 | No shared-library target (static libs only), so ctypes is not possible. | Subprocess (docs/decisions.md #46). |
| 14 | The C API has no AST, predicate table, explain or plain-query call (the alpha adds `validate`/`explain` to the CLI only). | C decides; the Python reference parser supplies structure; `explain()` refuses to show a proof if the two engines disagree. |
| 15 | Diagnostics wording differs from the reference engine (`Expected ':' after clause head, found NEWLINE`, ``variable Z is not bound before `not` ``, `facts must be ground (no variables): role/2`, `wildcard is not allowed in the head of rule r/1`, a `Lexical error:` prefix) and carries a column. | `app/engine/diagnostics.py` maps both wordings to the same stable codes; `Diagnostic.column` is optional. |
| 16 | Integer literals over 64 bits are a lexical error in C (the reference accepts any size). A context value like `99999999999999999999` is a DENY on C and may be an ALLOW on Python. | Documented difference; C fails closed (`test_evaluation_error_and_huge_integer_fail_closed`). |
| 17 | Evaluation depth limit of 256: a chain of ~200+ derived rules compiles but every decision is an `ERROR`. The reference rejects chains of ~1000+ rules at compile time (Python recursion) and decides shorter ones. | C error is mapped to DENY "engine error, failing closed". |
| 18 | `yog/build/` in a Windows checkout holds a stale `yogc.exe`; the build directory is not ignored in some checkouts. | Studio never uses it; it builds from `engine/c_front/` with `cc`. |
| 19 | Comparing an integer with a name is a runtime error in both engines (Python TypeError, #7; C "cannot compare a string with an integer") with different text; both end as DENY in Studio. | Fail closed in the adapters. |

Agreement checked (Nov 2026): the 94 gold policies / 298 scenarios, 82 shipped policies (validity), the context-fact edge cases (a context fact for a rule predicate, an unused undefined context predicate, resource `"42"` vs fact `x(42)`, unknown action, empty context, quoted vs bare names, negative integers, long strings) and the engine repo's own `diff_vs_python.py` give identical decision AND reason on both engines. Only #15, #16, #17 and #19 differ.
