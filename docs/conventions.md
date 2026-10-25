# YOG policy conventions used by Studio

The engine's decision predicates always take exactly `(Actor, Resource)`. Everything else about a request
(time, tool arguments, approvals) reaches the policy as **per-request context facts**.

| Thing | Convention | Example |
|---|---|---|
| Decision predicate | `can_<tool_name>(Actor, Resource)` | `can_unlock_door(Actor, Door)` |
| Actor | the agent is `agent` unless the user says otherwise | `fact role(agent, assistant)` |
| Resource | the thing acted on (door id, file path id, account id) | `front_door` |
| Hour of day (0-23) | context fact `hour(now, H)` | `hour(now, 3)` |
| Day of week | context fact `day(now, D)` with `mon..sun` | `day(now, sat)` |
| Tool argument | context fact `arg(<tool>, <param>, V)` | `arg(set_thermostat, temperature, 30)` |
| Other situational facts | context facts named by meaning | `approved(txn, yes)`, `occupied(home, yes)` |

## Rules of thumb
- **Numbers are integers** (the lexer has no decimals). Pass `22`, not `22.5`.
- **Constants are lowercase / `snake_case`** (`front_door`); variables start uppercase (`Door`).
- **Declare context predicates.** Engine check C4 rejects a clause that uses a predicate no `fact`/`rule`
  defines. Policies that read context facts declare a harmless placeholder base fact:
  `fact hour(placeholder, 0)`, `fact day(placeholder, none)`, `fact arg(placeholder, placeholder, 0)`.
- **Missing context fails open for `deny` clauses** (a deny that needs `hour(now, H)` simply doesn't match
  if no hour is supplied) and **fails closed for `allow` clauses** (default DENY). For safety-critical
  rules prefer an `allow` that *requires* the context, or make sure the caller always supplies it.
- **DENY > ALLOW > default DENY.** Write a broad `allow`, then narrow it with `deny` clauses.
- "OR" = several clauses with the same head. "AND" = several lines in one body.
- No recursion (rule cycles are a compile error).
