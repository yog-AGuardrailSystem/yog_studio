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
| C05 | Lexer: 29 tests under ASan+UBSan, ~30,700 checks, 100% line coverage, 22/22 mutants caught, 6,023 differential comparisons, 0 mismatches | aspirational | Quoted from the engine repo's lexer report at commit e70af31. Studio now vendors 200e481; re-run the engine's ctest (cmake, ASan) at that commit and re-confirm with the engine team before the demo |
| C06 | Compare any program against the real C lexer, and see the clause table the C compiler builds, in the explorer | backed | backend/app/engine/c_lexer.py, backend/app/engine/c_ir.py, e2e/workbench.mjs, Dockerfile |
| C07 | The pipeline has a lexer, parser, semantic analysis, a clause table, a VM and a C API that Studio calls (`yogc check`) | backed | engine/c_front/VERSION (pinned 200e481; sources under engine/c_front/src: parser, sema, ir, vm, api), backend/app/engine/c_engine.py. No bytecode stage: the engine compiles to a clause table (src/ir/ir.h) |
| C08 | The C implementation follows the same stages and is checked against the reference | backed | backend/tests/test_engine_conformance.py (every gold scenario, decision and reason, both engines), backend/tests/test_c_engine.py |
| C09 | Plain-English readback is built from the parsed program, never from a model | backed | backend/app/explain/explainer.py |
| C10 | Describe a rule in English: examples retrieved, model drafts, compiler checks, you approve | backed | backend/app/translate/translator.py, backend/tests/test_translator_gate.py (live model quality unmeasured: see benchmark) |
| C11 | Upload an agent, find its tools, get a minimal diff that adds the guard | backed | backend/app/modify/modifier.py, e2e/ui.mjs |
| C12 | The 3D scene applies the same rules as the policy | backed | frontend/tests/yogMirror.test.ts |
| C13 | Studio quality of drafts with a real model | aspirational | benchmark/results/ is empty until a Gemini or Claude key is used: run `python -m app.benchmark.evaluation` |
| C14 | 298 / 298 gold scenarios get the same decision and reason from the C engine and the Python reference; 95 gold policies compiled by both | backed | backend/tests/test_engine_conformance.py (also asserts the landing page numbers match the corpus) |
| C15 | The C engine makes the decisions in the deployed Studio | backed | Dockerfile (YOG_ENGINE=c), scripts/check_c_lexer.py (checks /info and a decision on the production image) |
