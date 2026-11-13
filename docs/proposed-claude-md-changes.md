# Proposed changes to CLAUDE.md (NOT applied: for the owner to approve)

CLAUDE.md says Studio is the product and the engine is a component. The project has since been re-framed:
the compiler is the story, Studio is the tool column that helps write YOG. These edits make CLAUDE.md match.
Apply them by hand (or ask for them to be applied) once you agree.

```diff
 ## 2. What Studio is (one sentence)
-> Upload a Python AI agent or MCP server → Studio finds its tools → you write rules in plain English → ...
+> Studio is the workbench around the YOG compiler: a YOG editor with live compile feedback, tests with
+> "why was this decided", and an English→YOG assistant (retrieval + LLM draft + compiler check + human approval).
+> Its agent tools (upload a Python agent or MCP server → find tools → patch with guards) are one tab of that.
```

```diff
 ### The 5 demoable components (only claim a component once it works)
-| 1 | **Compiler/engine** (engine team) | Policy compiles; tokens / AST / decisions visible |
+| 1 | **Compiler/engine** (engine team) | The main story. Tokens / AST / decisions visible live in the explorer; Python reference + real C lexer side by side |
```

```diff
 ## 3. Non-negotiable principles
+8. **Never claim what the repo cannot show.** Public copy states no invented numbers; measured figures come only from
+   committed results (`benchmark/results/`, never `results/fake/`). Statements that need work from others are tracked in
+   `docs/claims-ledger.md` (`scripts/claims_check.py`).
+9. **Drafted data is labelled.** Rules/examples written by Claude carry `source: claude-draft` until a teammate reviews
+   them (`python -m app.benchmark.review`). Final benchmark numbers need human-written holdout rules.
```

```diff
 ## 8. Repo layout
+├── e2e/                            # Playwright browser tests (run in CI)
+├── docs/                           # decisions, engine_issues, claims-ledger, motion-inventory
```

```diff
 ## 10. Milestones
-(W1-W12 table)
+Replaced by: compiler API → real LLM/RAG with semantic gate → evaluation + dataset review → workbench → landing →
+measured motion → quality gate (see docs/decisions.md #11-#19).
```

## Added with the C engine (Nov 2026) - proposed, not applied

```diff
 ## 4. Architecture
-                 └ CEngineAdapter (later, via ctypes)
+                 └ CEngineAdapter (yogc subprocess, `yogc batch`; decisions only - structure/explain come from the reference parser)
```

```diff
 ## 5. Tech stack
-- **Engine:** `yog.py` from `yog_engine` vendored under `engine/` ... Wrapped by `PythonPrototypeAdapter`.
+- **Engine:** `yog.py` and the C compiler (`engine/c_front/`, pinned in its VERSION) from `yog_engine`, vendored. Wrapped by `PythonPrototypeAdapter` and `CEngineAdapter`. Docker/CI default to C (`YOG_ENGINE=c`).
```

```diff
 ## 7. YOG language reference
-- Prototype **forbids recursion** (rule cycles are a compile error).
+- Prototype **forbids recursion** (rule cycles are a compile error). The grammar is now frozen in the engine repo's docs/COMPILER.md.
+- C engine limits: integers are 64-bit, tabs are rejected, evaluation depth is 256 (docs/engine_issues.md #15-#17).
```
