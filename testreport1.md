# Test Report 1 — Weeks 1–5

Generated automatically during the build. Environment: Windows 11, Python 3.12.13 (uv), Node 22, LLM provider = `fake` (offline).

## Automated results

`cd backend && uv run pytest -q` → **351 passed, 0 failed** (also passes with `LLM_PROVIDER=gemini` set in the environment: tests force the fake provider).
`cd frontend && npm run build` → TypeScript strict build OK.

| File | Tests | Covers |
|---|---|---|
| test_python_adapter.py | 12 | ALLOW, default DENY, **DENY beats ALLOW**, unknown action, context facts (no leakage), syntax/semantic errors, validate, program_info |
| test_api_check.py | 5 | `/health`, `/check` 200 ALLOW, DENY>ALLOW, 422 bad policy, 422 missing field |
| test_analyze.py | 16 | all 5 sample agents (kind, confidence, exact tools, params, hints), unknown file, decorator rename, client-vs-server, syntax error, **uploaded code never executed**, upload endpoint |
| test_samples.py | 2 | sample listing, 404 / path traversal |
| test_examples_dataset.py | 196 | 64 English↔YOG pairs: ≥60, unique ids, each gold policy compiles, every scenario matches the engine, each has both ALLOW and DENY |
| test_retriever.py | 16 | self-retrieval, paraphrases land in top 3, ordering/k, index reuse/rebuild/stale/corrupt, API, Gemini needs key, fake provider |
| test_translator.py | 29 | first-try valid, repair on 2nd attempt (error fed back), never-valid → 3 attempts + errors, wrong-tool rejection, LLM failure reported, fence extraction, prompts are files, 15 gold rules through lint, API contract |
| test_review_approve.py | 75 | readback covers every clause of all 64 policies, content checks, `/explain`, approve persists exact text, invalid/empty cannot be approved, reject stores nothing, edit→re-validate→approve, 404/traversal |

Manual-style checks run: live uvicorn on :8000, `curl POST /check` → ALLOW then DENY; same call through the Vite proxy (`:5173/api/check`) → DENY (W1).

## Known limits (honest)
- With the fake provider, "translation" is retrieval echo (copies the nearest example). Real translation quality is **untested** until a Gemini key is used.
- Gemini code path (`llm/gemini.py`) is written but never called live. Check the model names in `.env.example` are current.
- The 64 example pairs are Claude-drafted (`source: claude-draft`) and need team review. Scenarios were verified against the engine, which only proves they are self-consistent, not that they match what a human intends.
- No browser automation was run; UI is verified by type-check/build only. Do the manual list below.

## Manual tests for you (W1–W5)
Start: `.\scripts\dev.ps1`, open http://localhost:5173.

**W1 – Check page**
1. `/check`: default sample, actor `bob`, action `can_delete`, resource `db1` → red DENY, reason mentions deny clause, trace expands.
2. Change resource to `db2` → green ALLOW. Actor `alice` + `db1` → ALLOW.
3. Break the policy (delete a colon) → amber "Policy error" with a readable message, no crash.
4. Context box: add `hour(now, 3)` on a policy that uses it; confirm result changes.

**W2 – Upload & Tools**
5. Click each sample button: smart_home / file_ops / db_admin / finance → "MCP server, 0.95"; openai_tools_agent → "Function-calling agent, 1.00"; not_an_agent → amber "Unknown", checkboxes shown.
6. Evidence lines are highlighted yellow in the code view; click a tool row → editor scrolls to it.
7. Drag-drop your own `.py` file; upload a `.txt`/binary and a file with a syntax error → red error, app still usable.
8. On `not_an_agent`, tick two functions → "Continue with 2 tools".
9. Refresh the browser → analysis is still shown.

**W3 – Rules / retrieval**
10. Rules page: type "The agent may never unlock the door between 11pm and 6am" → Find similar examples → 3–6 cards, `sh-night-lock` first, "Show YOG" expands.
11. Try your own wording of several rules; note any irrelevant results (report to me).
12. Review `examples/policies/*.yaml` for correctness against your intent (team review is required by CLAUDE.md §11).

**W4 – Generate**
13. With smart_home tools loaded, Generate YOG draft → "compiles", attempts 1/3, example ids listed (offline mode copies the nearest example, with a `# OFFLINE FAKE PROVIDER` comment).
14. With a Gemini key (`backend/.env`: `LLM_PROVIDER=gemini`, `GEMINI_API_KEY=...`): generate for both demo-script rules; record attempts used and whether the YOG is semantically right.

**W5 – Review & Approve**
15. Review page: left YOG, right plain-English readback; every YOG line has a readback card.
16. Click Edit, break the syntax → badge "does NOT compile", Approve disabled; fix it → enabled.
17. Change `H >= 23` to `H >= 22` → readback updates.
18. Approve → "Approved and saved as p-…"; file appears in `backend/data/policies/` (.yog + .json).
19. Reject → "nothing was saved"; no new file.
