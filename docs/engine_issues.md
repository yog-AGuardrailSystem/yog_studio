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
