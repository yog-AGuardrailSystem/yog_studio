The YOG policy you drafted was rejected by the compiler / checker. Fix it.

## Rules it must implement
{{rules}}

## Tools available (decision predicate in brackets)
{{tools}}

## Your previous draft
```yog
{{previous}}
```

## Problems found
{{errors}}

Fix every problem and keep the intent of the rules. Remember: decision predicates are `can_<tool>(Actor, Resource)` with exactly two
arguments, every predicate used must be defined by a fact or rule, variables are Uppercase, constants lowercase, integers only,
and per-request predicates (`hour`, `day`, `arg`, ...) need a placeholder base fact.

Reply with ONE complete corrected policy in a single fenced block tagged `yog`, nothing else:
```yog
...
```
