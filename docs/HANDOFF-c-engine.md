# HANDOFF — YOG Studio: plug in the real C engine (continue on Arch Linux)

Paste the "Start prompt" at the bottom into Claude Code on Arch. Everything else here is context.

## 1. Where things stand (13 Nov 2026)
- Repo: `yog-AGuardrailSystem/yog_studio` (owner: Vasanthan). Read its `CLAUDE.md` first; its rules apply (plan first, tests with every module, never commit to `main`, never edit `engine/`, no secrets, never execute uploaded code).
- Engine repo: `yog-AGuardrailSystem/yog_engine`. `main` is at **200e481**, which has the full C compiler: sema C0–C5, IR, VM, C API and the `yogc` CLI. The language contract is in its `docs/COMPILER.md`.
- Newer, unmerged: branch `feature/compiler-backend` (12f1b2e, "0.1.0 alpha") adds `yogc validate` and `yogc explain`, evaluation limits, security and fuzz tests. We pin to `main` (200e481), not the alpha.
- Studio today treats C as "lexer only":
  - `backend/app/engine/c_engine.py` is a stub (`_implemented = False`)
  - `engine/c_front/` has the old lexer (e70af31)
  - the conformance test silently skips C
  - `engine/yog.py` is byte-identical to the engine repo's, so the Python reference is unchanged

## 2. Branches (all LOCAL on the Windows machine, may not be pushed)
- `feature/studio-hub` → 17-tool hub, security fixes, polish (through 9925214)
- `feature/hub-3d` → 3D hub, black-and-gold theme, scramble labels (0ba7988). I gave the user the push commands.
- `feature/c-engine` → just created from `feature/hub-3d`, **empty**. This is the working branch for this task.
- **Before switching OS: push all three**, or the Arch checkout won't have the work:
  `git push -u origin feature/studio-hub feature/hub-3d feature/c-engine`
- Untracked `graphify-out/` is not part of the work. Don't commit it.

## 3. Why we're moving to Arch
Windows 11 **Smart App Control is enforced** (registry `VerifiedAndReputablePolicyState = 1`). It blocks every unsigned exe we build, including `yogc.exe`; gcc itself installed and compiled fine, and running the result was blocked. It also blocks the venv's `python.exe`. On Linux there is no such block, so we can finally run the C engine.

## 4. Decisions already made by the owner
- **Binding:** call `yogc` as a **subprocess**, not ctypes.
  - Upstream builds only static libs, so there is no shared library.
  - A crash in C must not take down the backend.
  - It matches the existing `lexdump` bridge in `backend/app/engine/c_lexer.py`.
  - Record the deviation from CLAUDE.md §4 ("via ctypes") in `docs/decisions.md`.
- **Default engine:** `YOG_ENGINE=c` in Docker/CI; local dev stays `python` unless set. Never a silent fallback (`backend/app/api/deps.py` already enforces this).
- **Engine bugs:** report in `docs/engine_issues.md`; never patch the engine's code.

## 5. Gaps found by reading the code (each becomes a test)
| # | Gap | Fix |
|---|---|---|
| G1 | `CEngineAdapter` is a stub | Implement over `yogc` |
| G2 | Vendored `engine/c_front/` is stale | Re-vendor `yog/src/**`, `yog/include/api/yog.h`, `yog/tools/{lexdump.c,yogc.c}`, LICENSE, a copy of `docs/COMPILER.md`; update `VERSION` files |
| G3 | **Security: context injection.** C's `compile_context` replaces every `;` with a newline, including inside quoted strings. `arg(t,p,"x; fact role(agent, admin)")` would add an authority fact. `yogc batch` also splits on `\|` and whitespace and cuts lines at 4096 bytes. The alpha branch does not fix this (its SECURITY.md says context "must be trusted"). | Parse each context item with the reference parser (exactly one ground fact, as the Python adapter already does), re-serialise canonically; reject `;`, `\|`, CR/LF, over-long lines → DENY. Odd actor/resource values go through argv `yogc check`. Regression tests. |
| G4 | `backend/app/engine/diagnostics.py` matches Python's wording only. C differs: `variable X is not bound before \`not\``, `facts must be ground (no variables): name/arity`, `wildcard is not allowed in the head…`, tabs, `integer literal out of range`, parser `expected …`, and a `file:line:col: error:` prefix | Add C patterns mapped to the same stable codes; add optional `column` to `Diagnostic` |
| G5 | C API has no AST/predicates/explain/ask | C **decides**; Python parser gives structure (`program_info`, `compile_info`, `queries`, `ask`). `explain()` runs Python and compares its decision with C's; on disagreement return `error=True` ("engines disagree") so the Why panel never explains a decision C didn't make. Show "decisions: C · structure: reference parser" in `/status` and the workbench |
| G6 | One process spawn per check is slow | Add `check_many()` to `EngineAdapter` (default loops `check`; C uses one `yogc batch`); switch the scenario loops (evaluator, scorecard, gaps, replay…) to it |
| G7 | Trace is one newline-joined string in C, a list in Python | Split lines. Reason strings already match |
| G8 | C evaluation errors (int-vs-text, step/depth limits) come back as `ERROR\|…` or exit 2 | Map to DENY "engine error, failing closed" (like Python issue #7) |
| G9 | Conformance silently skips C | `YOG_REQUIRE_C=1` in CI makes it fail instead; run `test_hostile_input` cases through C too |
| G10 | Grammar is now frozen in COMPILER.md | Check `backend/app/llm/prompts/*.md` and `examples/policies/*.yaml`: no tabs, no `foo()`, no wildcard in a rule head / `not` / comparison, comparison left side is a variable or literal |
| G11 | Edge cases to compare on both engines | Context fact for a predicate defined as a rule; context predicate with no placeholder (issue #4); resource `"42"` vs fact `x(42)`; unknown action; empty context. Divergences go to `engine_issues.md` |

## 6. Implementation steps
1. `c_build.py` (new): generic `find_tool(name, sources, env_var)`; builds `lexdump` and `yogc`:
   `cc -std=c11 -O2 -I src -I include src/lexer/lexer.c src/parser/*.c src/sema/*.c src/ir/*.c src/vm/*.c src/api/yog.c tools/yogc.c`
   Output in `backend/data/c_front/`, rebuilt when `VERSION` changes. Env overrides `YOG_LEXDUMP`, `YOG_YOGC`. `c_lexer.py` uses it; re-check `KNOWN_DIFFERENCES`.
2. Rewrite `c_engine.py`:
   - `available()` = a yogc is found or buildable
   - policy written once to a temp file, cached by SHA-256 (LRU-bounded)
   - `validate()` = `yogc batch policy < /dev/null`; parse `path:L:C: error: msg`
   - `check()`/`check_many()` = G3 guard, then `yogc batch --trace` lines `actor action resource | fact …`; parse `ALLOW|reason`, `> trace`, `--` blocks
   - validate the response count; any mismatch, timeout (5 s per batch) or crash → DENY
   - an uncompiled policy raises `EngineError`
   - replace `YOG_C_ENGINE_LIB` with `YOG_YOGC` and update `test_selecting_c_without_library…` in `backend/tests/test_engine_conformance.py`
3. Run the conformance suite (94 golds, ≥250 scenarios) on both adapters; diff **decision and reason**; investigate every disagreement (G11).
4. Diagnostics (G4), explain cross-check (G5), status, UI `L:C`.
5. Switch callers to `check_many` (grep `adapter.check(` inside loops).
6. `Dockerfile`: the cbuild stage also builds `/yogc` → `/app/bin/yogc`, `ENV YOG_ENGINE=c YOG_YOGC=/app/bin/yogc`. `.github/workflows/ci-cd.yml`: backend tests with `YOG_REQUIRE_C=1` and one e2e pass with `YOG_ENGINE=c`.
7. Docs: `docs/engine_issues.md` (close #8/#9/#10 as appropriate; add `;` splitting, no SHARED library target, no AST/introspection in the C API, 4096-byte batch line limit, diagnostic wording, any G11 divergence; mention the alpha branch), `docs/decisions.md`, `docs/RUNNING.md`. Propose (not apply) CLAUDE.md edits in `docs/proposed-claude-md-changes.md`.
8. Optional: an explorer "C IR" tab from `yogc ir`.

## 7. Verification
- `YOG_ENGINE=c YOG_REQUIRE_C=1`: the full backend suite passes, no new skips; new `test_c_engine.py` covers protocol parsing, timeout/crash → DENY, the G3 injection cases, argv path for spaced values, `check_many` count mismatch, and C diagnostics → stable codes.
- Differential: the Studio gold corpus plus the engine repo's `all_examples.yog` through both adapters.
- Engine repo's own checks: `cmake -S yog -B yog/build -DYOG_SANITIZE=ON && cmake --build yog/build && ctest --test-dir yog/build`, then `python yog/tests/differential/diff_vs_python.py --yogc yog/build/yogc`.
- e2e with the backend on `YOG_ENGINE=c`: `tools.mjs`, `workbench.mjs`, `prod.mjs`.
- Timing: the evaluator on 12 scenarios under 1 s.

## 8. Windows-only workarounds that do NOT apply on Arch
- Running Python: on Windows I had to use uv's Python 3.14 with `PYTHONPATH` because the venv's `python.exe` was blocked. On Arch use the normal venv (`uv sync` or `python -m venv`).
- Playwright e2e ran on software GL (swiftshader) at 2–4 fps; on Arch, real GL is likely faster, but the hub tests use `force: true` clicks.
- ffmpeg came from the `imageio-ffmpeg` pip package; not needed.
- Packages for Arch: `sudo pacman -S base-devel cmake git python uv nodejs npm`.

## 9. Open questions for the owner
- Are the three branches pushed?
- Should the deployed default flip to `c` once all gold scenarios agree? (Chosen: C in Docker/CI, Python locally.)

## Start prompt (paste into Claude Code on Arch, from the repo root)
```
Read CLAUDE.md and this handoff (HANDOFF.md or the plan file). Check out feature/c-engine (cut from feature/hub-3d). Clone yog-AGuardrailSystem/yog_engine next to this repo, build yogc natively (cmake, then check it runs), and run the engine's own ctest and differential test. Then follow section 6 of the handoff: re-vendor engine/c_front at 200e481, implement CEngineAdapter over `yogc batch`, add the context-injection guard (G3), compare every gold scenario on both engines, and fix or report every gap. Plan first, then wait for my approval before editing.
```
