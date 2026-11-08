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

A line that starts with `check:` comes from an independent test that a DIFFERENT model wrote from the plain-English rules only. Such tests can be wrong.
Change the policy for a `check:` line only if the English rules clearly support the expected result. If they do not, leave that behaviour as it is.

Fix every problem and keep the intent of the rules. Remember: decision predicates are `can_<tool>(Actor, Resource)` with exactly two
arguments, every predicate used must be defined by a fact or rule, variables are Uppercase, constants lowercase, integers only,
and per-request predicates (`hour`, `day`, `arg`, ...) need a placeholder base fact.

Reply with ONE complete corrected policy in a single fenced block tagged `yog`, nothing else:
```yog
...
```
