# Test Report 3 — Weeks 10–12 and whole-system (integration) testing

Cumulative: `cd backend && uv run pytest -q` → **541 passed, 0 failed**. `npm run build` OK. `git diff main -- engine` is empty (vendored engine untouched).

## W10 – engine selection / C-engine readiness
| Test | Result |
|---|---|
| Conformance: all 64 retrieval golds + 30 benchmark golds (298 scenarios) through every available adapter | PASS on `python` |
| `YOG_ENGINE` default is python; `c` without the library raises (never a silent fallback); unknown name rejected | PASS |
| **C engine itself** | **NOT TESTED – not available.** `CEngineAdapter` is a placeholder; no ABI was invented. When the engine team ships a library, implement 3 methods in `app/engine/c_engine.py`; the conformance suite then runs automatically. |

## W11 – polish
Error boundary, backend-down banner, 3-step progress strip, "Use prepared demo policy" (labelled hand-written, never presented as LLM output), probe table capped at 14 rows per action. Verified by the browser run below.

## W12 – demo readiness
`docs/DEMO.md` (script + failure modes) and `docs/RUNNING.md`. **A recorded backup video was not produced** (cannot be done by the build tooling) — you must record it.

## Whole-system tests

### A. In-process pipeline (`tests/test_integration_pipeline.py`, 3 tests) — PASS
Follows the CLAUDE.md §12 demo through HTTP: analyze smart_home (MCP, 0.95, tools) → translate (scripted LLM, valid in 1 attempt) → explain → nothing live yet → evaluate (4/4 independent scenarios green) → approve (server-side evaluation stored) → modify (0 removed lines) → bundle zip → **the patched agent run in a subprocess: 3am → DENIED, 2pm → unlocked** → device at 3am: DENY, door stays locked, reason shown → device at 2pm: ALLOW. Plus: device and bundle refuse without an approved policy; a draft that never compiles (3 attempts) cannot be approved and cannot reach the device.

### B. Live servers through the Vite proxy (curl-style script) — PASS
Backend `:8000` + frontend `:5173`, all calls via `:5173/api/*`: health, analyze (mcp_server 0.95, 5 tools), retrieve (`sh-night-lock` 0.88 first), translate (fake: valid, 1 attempt), explain (11 clauses), evaluate, approve, 3am unlock → DENY/not executed, demo day `[ALLOW, ALLOW, DENY, DENY, DENY, DENY, ALLOW]`, modify (+6 / −0). A stale W1 server on port 8000 initially served 404s — a reminder to stop old servers (`Get-NetTCPConnection -LocalPort 8000`).

### C. Real browser (Playwright/Chromium, script in `e2e/ui.mjs`) — 15/15 PASS
Detect badge "MCP server, 0.95"; 5 tool rows; unknown file shows manual pick; retrieval cards; prepared-policy draft "compiles"; readback; valid badge; scenario report; Approve → "Approved and saved as p-…"; Patch summary "5 tool(s) guarded, +6 lines added, 0 removed"; Device demo day logs 7 rows; 3am unlock blocked in the log; red "BLOCKED BY YOG" banner; Check page DENY; no uncaught page errors.

## What these tests do NOT prove
1. **Real translation quality** — all runs used the offline fake provider (retrieval echo). Gemini was never called. Benchmark numbers are therefore not evidence (the harness labels them so).
2. **Human-authored data** — examples, benchmark rules and scenario expectations are Claude drafts and need team review.
3. **Patched agent with the real `mcp` package** — tested with a stub `FastMCP` and the real runtime. Manual test M3 below.
4. **C engine** — absent.
5. Visual quality (layout, colors, responsiveness) — only functional assertions were automated; one screenshot was taken but not judged.
6. Windows quirk: `uv run uvicorn` is blocked by Application Control; use `python -m uvicorn` (already in `dev.ps1`).

## Manual tests for you (W10–W12 + system)
M1. Fresh clone sanity: follow `docs/RUNNING.md` from scratch on a second machine/folder; `.\scripts\dev.ps1` opens both servers; no red banner.
M2. Walk the whole `docs/DEMO.md` script twice, timing it; try each "things that can go wrong" item (stop the backend → red banner appears within ~5 s and disappears when restarted).
M3. `pip install mcp`; unzip a downloaded bundle; run the patched `smart_home_mcp.py` as an MCP server (`mcp dev smart_home_mcp.py`); confirm tools list with their parameters, `YOG_NOW="3,mon"` → `unlock_door` returns an error, `YOG_NOW="14,mon"` → works.
M4. Gemini end-to-end: set `LLM_PROVIDER=gemini`, `GEMINI_API_KEY`; check model names in `.env.example` are current; run both demo rules through Generate → Review → Run scenarios; record attempts and whether independent scenarios are green; then run the benchmark and save the numbers.
M5. Review all `examples/policies/*.yaml` and `benchmark/rules.yaml` for intent (and write replacement human benchmark rules).
M6. Judge the visuals: screen-share at 1080p, check readability of the Review and Device pages; dark rooms/projectors; browser zoom 110%.
M7. Ask the engine team for the C library ABI; tell them about issue #7 and the eager-comparison problem in `docs/engine_issues.md`.
M8. Record the backup video of the full demo.
M9. Decide whether to merge branches: they are stacked (`feature/w1-scaffold` → … → `feature/w12-demo-integration`); merging the last one into `main` brings everything. Nothing was pushed.
