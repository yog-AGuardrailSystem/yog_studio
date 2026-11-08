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
