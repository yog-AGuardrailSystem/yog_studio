# Design decisions (and where they depart from CLAUDE.md)

Made while building W1–W12 unattended. Each was argued for/against before choosing; the losing option is noted.

| # | Decision | Why | Rejected alternative |
|---|---|---|---|
| 1 | **Explainer is deterministic** (AST → English), not LLM. *Departs from CLAUDE.md §4 "Explainer — LLM".* | The readback is the human's last check before Approve; it must be faithful to every clause and cannot invent behaviour. Tests prove every clause of 64 policies is covered. | LLM readback: more fluent, but can silently misdescribe the policy. An optional LLM "polish" can be added later on top. |
| 2 | **Scenarios are split into independent vs characterization.** Independent = from the user or an LLM that sees only the English rules (never the YOG). Characterization probes (boundaries, no-context) are shown as *unconfirmed* and **excluded from the pass %**. | Expected values copied from the engine always "pass"; counting them would be circular and falsely green. | One merged score (simpler, but misleading). |
| 3 | **Modifier inserts a `@yog_guard("tool")` decorator** + one import, instead of rewriting call sites. | Zero removed lines (tested), survives async/sync/methods, keeps signatures so FastMCP still sees parameters. Runtime ships as a standalone file next to `yog.py` and `policy.yog`. | Wrapping each call site (touches many lines, brittle). |
| 4 | **One fact-normalisation path** (`app/core/facts.py`, mirrored in `yog_runtime.py`, equality tested). | Raw values crash or mis-lex in the engine (floats, `True`, `"USD"` lexes as a variable). | Normalising separately in runtime, simulator and evaluator (drift). |
| 5 | **Engine `TypeError` ⇒ fail closed (DENY).** Logged as engine issue #7. | A guardrail must never turn an engine crash into a 500 or an ALLOW. | Letting it propagate. |
| 6 | **C engine = placeholder with no invented ABI**; selecting `YOG_ENGINE=c` without a library is an error. | The C engine has no published interface; guessing one would be fake work. Conformance suite is ready for it. | A fake C adapter that delegates to Python (misleading). |
| 7 | **Prepared demo policy is hand-written and labelled as such** in the UI. | Offline (fake LLM) the translator only echoes the nearest example; the demo must not pass that off as translation. | Presenting the echo as a generated policy. |
| 8 | **Approval gate is server-side and evidence-based**: `/policies/approve` re-validates, runs its own evaluation (client-supplied evaluation ignored), and the UI keeps Approve disabled until scenarios were run for the *current* text. | CLAUDE.md §3.1: results before the Approve click; never trust the client. | Trusting a client "valid" flag. |
| 9 | Devices and bundles use **only approved policies** (`store.latest()` / explicit id); guard-off mode exists for the demo contrast and is labelled UNGUARDED. | A draft must never govern a device. | Using the current draft. |
| 10 | Tests force the fake LLM (`conftest.py`), the LLM is a FastAPI dependency. | A `.env` with a real key must never make the suite call (and bill) Gemini. | Reading the provider from the environment in tests. |
