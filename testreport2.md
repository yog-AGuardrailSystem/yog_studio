# Test Report 2 — Weeks 6–9

Environment as in testreport1 (LLM provider `fake`, offline). `cd backend && uv run pytest -q` → **531 passed** (all weeks cumulative). Frontend `npm run build` OK.

## Automated results

| File | Tests | Covers |
|---|---|---|
| test_evaluator.py | 99 | value normalisation (bool/float/"USD"/"Front Door"/None) and "normalised facts are always accepted by the engine"; characterization probes are **unconfirmed and never counted**; boundary-hour/arg probes; no-context ALLOW warning; LLM scenarios graded independently; wrong policy shows red; **generator never sees the YOG**; one bad row never fails a run; garbage LLM reply → warning; all 64 gold scenarios green as user scenarios; `/evaluate`; **server-side evaluation stored at approval, client value ignored** |
| test_modifier.py | 21 | all 5 samples: **0 removed lines**, +1 import +1 decorator per tool, patched file parses and re-analyses to the same tools; decorator innermost; import after docstring and `from __future__`; shebang; CRLF preserved; no trailing newline; class methods; idempotent; subset; renamed tools; missing implementation reported; unknown file refused; **runtime standalone (no `app` import)**; runtime normalisation == Studio's; real subprocess run of guarded sync + async functions (signature/docstring preserved, ALLOW at 14:00, DENY at 03:00, fail-closed with no policy, unknown tool denied); `/modify`, `/modify/bundle` (404 without approved policy, zip contents) |
| test_device.py | 23 | refuses to run without an approved policy (409); **3am unlock → DENY and door stays locked**; afternoon unlock executes; boundaries 22/23/0/5/6; float temperature normalisation; valve cap; unmapped tool default-denied; guard-off shows the unsafe outcome; demo day (7 commands, 4 DENY); latest vs explicit policy; bad commands 422 and change nothing; clock validation; reset |
| test_benchmark.py | 36 | 30 rules, ids/text/gold disjoint from retrieval set; every gold compiles and its scenarios hold; **leakage check** (max cosine 0.478 < 0.9); semantic compare is behavioural not textual; fake run is labelled; scripted provider shows retry loop 0% → 100% |

## Bug found and fixed during W6
- Engine crash: **any comparison between an int and a name raises `TypeError` inside `yog.py`** (it evaluates all six operators eagerly). The adapter now fails closed (DENY with reason); regression test added; logged as issue #7 in `docs/engine_issues.md` for the engine team.

## Benchmark run (fake provider) — NOT evidence
`uv run python -m app.benchmark.runner` → syntax-valid 100%, semantically correct **0%** (the offline provider copies the nearest example, which is a different rule), avg attempts 1.0 vs 2.73. This only proves the harness works. **Real numbers need a Gemini key and team-written rules.**

## Known limits
- The 30 benchmark rules and all scenario expectations were drafted by Claude, not humans (CLAUDE.md §11 requires human-written benchmark rules).
- LLM scenario generation, translation and Gemini embeddings are untested live.
- Patched agents were tested with the real runtime in a subprocess, **not** with the real `mcp` package installed (see manual test M3).
- No browser automation; UI checks below are manual.

## Manual tests for you (W6–W9)
**W6 – Evaluation (Review page)**
1. Generate a draft, open Review, click *Run scenarios*. Expect a grey "unconfirmed" table (probes), the line "No independent scenarios…", and a warning if the policy allows with no time/argument info.
2. Click *confirm* on a probe → score becomes `1/1` green; *flip* a correct probe → score turns red (shows a disagreement with the policy).
3. With a Gemini key: run again; you should see independent scenarios (green/red) generated from your English only. Check that they match what *you* meant.
4. Edit the policy so it is wrong (e.g. change `H >= 23` to `H >= 25`) and confirm a red row appears for 23:00.

**W7 – Patch page**
5. Upload `smart_home_mcp.py`, open *Patch*: side-by-side diff shows only added lines (+6), summary "5 tools guarded, +6 added, 0 removed".
6. Without an approved policy the Download button is disabled; approve one, download the zip, unzip: `smart_home_mcp.py`, `yog_runtime.py`, `yog.py`, `policy.yog`, `README.txt`.
7. **M3 (important):** `pip install mcp`, run the patched server in that folder with `YOG_NOW="3,mon"`; call `unlock_door` from an MCP client (e.g. `mcp dev`). Confirm the tool still lists its `door_id`/`pin` parameters (FastMCP reads the signature through the wrapper) and returns an error at 3am but works with `YOG_NOW="14,mon"`.
8. Upload `not_an_agent.py` → Patch page shows an error, not a diff.

**W8 – Device**
9. With no approved policy, Device page shows the amber notice and commands fail with "approve a policy first".
10. Approve a policy that covers `unlock_door`/`set_thermostat`/`open_valve` (the demo-script rules). Set hour to 3, click *Unlock front door* → red banner "BLOCKED BY YOG", door stays 🔒 locked, log row red with reason.
11. Set hour 14 → unlock succeeds, door shows UNLOCKED.
12. *Run agent demo day* → 7 rows, 4 red; toggle *YOG guard OFF* and run again → everything executes (amber) — the contrast for the demo.
13. Thermostat 35 → blocked; 22 → applied. Tap 30% allowed, water main 100% blocked (if your policy has the 50% cap).
14. Reset restores the initial state.

**W9 – Benchmark**
15. `cd backend; uv run python -m app.benchmark.runner` prints the table and writes `benchmark/results/*.md|json` (labelled "OFFLINE FAKE" with the fake provider).
16. With a Gemini key (`LLM_PROVIDER=gemini` in `backend/.env`): run again; record syntax-valid %, semantic %, with/without retry. Review `benchmark/rules.yaml` and replace/extend it with team-written rules (aim ≥30 human rules).
