# Demo script (CLAUDE.md section 12) and backup plan

A recorded backup video cannot be produced by the build tooling: **record one yourself** (OBS / Win+G) following this script.
Rehearse twice; the offline path below needs no API key and no internet.

## Before you start
1. `.\scripts\dev.ps1` (or see docs/RUNNING.md). Open http://localhost:5173. Top strip should show no red banner.
2. Optional live LLM: put `LLM_PROVIDER=gemini` and `GEMINI_API_KEY=...` in `backend/.env`, restart the backend.
3. Delete `backend/data/policies/*` for a clean "nothing is live yet" start.

## Script (about 4 minutes)
1. **Upload & Tools** -> click `smart_home_mcp.py`. Say: "Studio never runs this file, it only reads it." Point at the badge *MCP server, 0.95* and the yellow evidence lines; tools `unlock_door`, `set_thermostat`, `open_valve` appear with side-effect chips.
2. **Rules** -> type: *The agent may never unlock the door between 11pm and 6am.* then *Thermostat must stay between 16 and 28 degrees.* -> **Find similar examples** (the retrieval step: show the cards and similarity scores) -> **Generate YOG draft**.
   - With Gemini this is the real translation; show attempts used (n/3).
   - Offline (fake provider) the draft is only the nearest example copied: use **Use prepared demo policy** instead and say plainly that it is hand-written.
3. **Review** -> left: YOG; right: plain-English readback. Say: "The AI drafted, the compiler verified, now a human decides." Click **Run scenarios**: show the independent results (live LLM) or the unconfirmed probes (offline) and *confirm* two of them. Click **Approve**.
4. **Patch** -> side-by-side diff: only added lines (`@yog_guard(...)` + one import). Click **Download patched bundle**.
5. **Device** -> set hour 14, *Unlock front door*: allowed, door unlocks. Set hour **3**, click *Unlock front door*: big red **BLOCKED BY YOG**, door stays locked, log shows the reason (headline moment). Toggle the guard OFF and repeat to show what would have happened. Finish with **Run agent demo day**.

## Things that can go wrong on stage
- Red "Cannot reach the backend" banner: backend not running.
- Device page says "no approved policy": you skipped Approve.
- Gemini quota/network error: Rules page shows the error; fall back to *Use prepared demo policy*.
- Browser state odd: error screen has "Reset the app state and reload".
