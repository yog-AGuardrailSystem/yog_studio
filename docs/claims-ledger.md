# Claims ledger (internal)

Every statement the public landing page makes, mapped to what backs it. Not rendered on the site.
The site is written in the voice of a finished product (decision: see docs/decisions.md), so some statements describe
things that must be true by the final demo. `scripts/claims_check.py` lists those and verifies that every `backed`
row still points at a file that exists.

Status: `backed` = a file in this repo (code, test or committed result) demonstrates it today.
`aspirational` = stated on the site, not demonstrable from this repo yet. Fix these before the demo or reword the site.

| id | claim on the site | status | evidence |
|---|---|---|---|
| C01 | The explorer's tokens, tree, checks and decisions come from the engine as you type | backed | backend/app/api/compile.py, e2e/landing.mjs |
| C02 | DENY beats ALLOW; anything not allowed is denied | backed | engine/yog.py, backend/tests/test_compile_api.py |
| C03 | Every decision carries the clause that produced it and the facts used | backed | backend/app/api/compile.py, e2e/workbench.mjs |
| C04 | Team example groups A to R run in the explorer | backed | backend/tests/test_team_examples.py, e2e/landing.mjs |
| C05 | Lexer: 29 tests under ASan+UBSan, ~30,700 checks, 100% line coverage, 22/22 mutants caught, 6,023 differential comparisons, 0 mismatches | aspirational | Quoted from the engine repo's lexer report at commit e70af31; re-confirm with the engine team before the demo, and re-verify at the commit that ships |
| C06 | Compare any program against the real C lexer in the explorer | backed | backend/app/engine/c_lexer.py, Dockerfile (needs the deployed image; not runnable on the dev machine) |
| C07 | The pipeline has semantic analysis, IR, bytecode, a VM, a C ABI and a Python wrapper | aspirational | Engine team roadmap; only lexer, parser and the Python reference exist in this repo's view |
| C08 | The C implementation follows the same stages and is checked against the reference | aspirational | Only the lexer is differentially checked (scripts/check_c_lexer.py) |
| C09 | Plain-English readback is built from the parsed program, never from a model | backed | backend/app/explain/explainer.py |
| C10 | Describe a rule in English: examples retrieved, model drafts, compiler checks, you approve | backed | backend/app/translate/translator.py, backend/tests/test_translator_gate.py (live model quality unmeasured: see benchmark) |
| C11 | Upload an agent, find its tools, get a minimal diff that adds the guard | backed | backend/app/modify/modifier.py, e2e/ui.mjs |
| C12 | The 3D scene applies the same rules as the policy | backed | frontend/tests/yogMirror.test.ts |
| C13 | Studio quality of drafts with a real model | aspirational | benchmark/results/ is empty until a Gemini or Claude key is used: run `python -m app.benchmark.evaluation` |
