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
| C03 | Every decision carries its reason (the clause that matched, or the default deny) and a trace of the facts it checked | backed | backend/app/api/compile.py, e2e/workbench.mjs |
| C04 | Team example groups A to R run in the explorer | backed | backend/tests/test_team_examples.py, e2e/landing.mjs |
| C05 | Lexer: 100% line coverage, 22/22 injected bugs (mutants) caught, 6,023 differential comparisons, 0 mismatches | aspirational | Quoted from the engine repo's lexer report (yog/docs/weekly/lexer_week4.md, lexer unchanged since e70af31); Studio has not re-run coverage, mutation testing or the 6,023-comparison fuzz. The test and check counts of the same report ARE re-measured: see C16 |
| C06 | Compare any program against the real C lexer, and see the clause table the C compiler builds, in the explorer | backed | backend/app/engine/c_lexer.py, backend/app/engine/c_ir.py, e2e/workbench.mjs, Dockerfile |
| C07 | The pipeline is: lexer, parser, semantic analysis, IR (a clause table, no bytecode), a backtracking VM, an authorization layer (deny > allow > default deny), a C API, and Studio calling `yogc` | backed | engine/c_front/docs/COMPILER.md, engine/c_front/src/ir/ir.h, engine/c_front/src/vm/engine.c, backend/app/engine/c_engine.py |
| C08 | A Python reference defines the behaviour; the C compiler is the production implementation, tested with its own semantic tests and with differential tests against the reference | backed | engine/c_front/docs/COMPILER.md, backend/tests/test_engine_conformance.py, scripts/c_engine_report.py |
| C09 | Plain-English readback is built from the parsed program, never from a model | backed | backend/app/explain/explainer.py |
| C10 | Describe a rule in English: examples retrieved, model drafts, compiler checks, you approve | backed | backend/app/translate/translator.py, backend/tests/test_translator_gate.py (live model quality unmeasured: see benchmark) |
| C11 | Upload an agent, find its tools, get a minimal diff that adds the guard | backed | backend/app/modify/modifier.py, e2e/ui.mjs |
| C12 | The 3D scene applies the same rules as the policy | backed | frontend/tests/yogMirror.test.ts |
| C13 | Studio quality of drafts with a real model | aspirational | benchmark/results/ is empty until a Gemini or Claude key is used: run `python -m app.benchmark.evaluation` |
| C14 | 298 / 298 gold scenarios get the same decision and reason from the C engine and the Python reference; 95 gold policies compiled by both | backed | backend/tests/test_engine_conformance.py (also asserts the landing page numbers match the corpus) |
| C15 | The C engine makes the decisions in the deployed Studio | backed | Dockerfile (YOG_ENGINE=c), scripts/check_c_lexer.py (checks /info and a decision on the production image) |
| C16 | The C compiler's own test programs: 66 tests, 30,886 checks, all pass, built with every warning an error and run under AddressSanitizer and UBSan; its differential script matches 25 of 25 queries of the team's example file | backed | scripts/c_engine_report.py (re-run it on a yog_engine checkout; measured at 200e481 on 2026-11-14), backend/tests/test_engine_conformance.py (keeps the page's commit equal to the vendored one) |
| C17 | Download yogc: a Windows installer (per-user, adds it to PATH), a Windows zip and a static Linux build, with SHA-256 checksums, from the engine version Studio runs | backed | scripts/build_downloads.sh, packaging/windows/yog.nsi, backend/app/api/downloads.py, backend/tests/test_downloads.py, scripts/check_c_lexer.py (prod image: files listed and served byte-for-byte), Dockerfile |
