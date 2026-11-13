# Running YOG Studio

One-time setup:
```
uv python install 3.12
cd backend ; uv sync --extra dev
cd ../frontend ; npm install
```
Run both (Windows): `.\scripts\dev.ps1`  -> backend http://localhost:8000/docs, frontend http://localhost:5173
Linux/macOS: run the two commands below in two terminals (`uv run python -m uvicorn …` and `npm run dev`).

Or separately:
```
cd backend  ; uv run python -m uvicorn app.main:app --reload --port 8000
cd frontend ; npm run dev
```
(`uv run uvicorn` can be blocked by Windows Application Control; `python -m uvicorn` is not.)

Tests: `cd backend ; uv run pytest -q` (offline; forces the fake LLM). Frontend: `cd frontend ; npm run build`.
Benchmark (needs a real key for numbers that mean anything): `cd backend ; uv run python -m app.benchmark.evaluation --split dev --robustness` (add `--engine c` to have the C engine decide; the default is `$YOG_ENGINE`, and the engine is recorded in the results), retrieval: `uv run python -m app.benchmark.retrieval_eval`, one-off key check: `uv run python ../scripts/llm_smoke.py`.
Team review of drafted examples: `uv run python -m app.benchmark.review pack --reviewers A,B,C`, then `... review apply review/A.md ...`.
Claims the site makes that are not yet demonstrable: `python scripts/claims_check.py`.

## Configuration (`backend/.env`, see `.env.example`)
- `LLM_PROVIDER=fake` (default, offline), `gemini` with `GEMINI_API_KEY`, or `claude` with `ANTHROPIC_API_KEY`; `EMBED_PROVIDER` for embeddings. Every setting is documented in `.env.example`.
- `YOG_ENGINE=python` (default locally) or `c` (default in the Docker image). `c` runs the engine team's `yogc` (vendored in `engine/c_front/`, pinned commit in its VERSION): Studio builds it on first use with `cc`/`gcc`/`clang` into `backend/data/c_front/`, or use `YOG_YOGC=/path/to/yogc`. A missing `yogc` is an error, never a silent fallback. `YOG_REQUIRE_C=1` makes the tests fail instead of skip when C is unavailable (CI sets it).
- The workbench's **C IR** tab shows the clause table `yogc ir` builds (works whichever engine decides). The shipped runtime guard decides with `yog.py` unless `YOG_YOGC` is set in the agent's environment.
- **Downloads (`/download` page):** the Docker image builds `yogc` for users from `engine/c_front` with `scripts/build_downloads.sh` (stage `dist`): a Windows installer (NSIS, per-user, adds yogc to PATH, uninstalls cleanly), a Windows zip, a static Linux tarball, `SHA256SUMS.txt` and `manifest.json`. The backend serves only the files named in that manifest (`/downloads`). Locally, build them into `backend/data/downloads` (git-ignored) with the Docker one-liner at the top of the script; without them the page says how. The Windows files are not code-signed (SmartScreen warns; Smart App Control blocks them), and the page says so.
- Run the suite on the C engine: `cd backend && YOG_ENGINE=c YOG_REQUIRE_C=1 uv run pytest`. Re-vendoring: replace `engine/c_front/` from `yog_engine` and update both VERSION files (a changed VERSION triggers a rebuild).

## Data
Approved policies are saved to `backend/data/policies/` (git-ignored). The retrieval index is `backend/data/index.npz`.

## Deploying to Render (free)
See the "Deploy" section in docs/DEPLOY.md.

## Pages (frontend routes)
| Route | What it is |
|---|---|
| `/` | Landing page: live compiler explorer, four compiler scenes, pipeline conveyor, example cards A to R, 3D decision gate |
| `/how-it-works` | Scroll-driven walkthrough of the agent tools flow, with an interactive device demo |
| `/studio` | The tool hub: every Studio tool, how it works, what it does not do |
| `/studio/why`, `/studio/map`, `/studio/gaps`, `/studio/red-team`, `/studio/strength`, `/studio/templates`, `/studio/history`, `/studio/audit`, `/studio/replay`, `/studio/sdk`, `/studio/export`, `/studio/scorecard` | The Studio tools (each page explains how it works); API under `/studio/*` |
| `/studio/workbench` | The YOG workbench: editor, live compile, tests with "why", tokens/AST/readback, C lexer, Assist, evidence |
| `/agent`, `/rules`, `/review`, `/modify`, `/device` | Agent tools: upload an agent, rules, review and approve, patch, device |
| `/check` | Sandbox: try a policy on one action |

Browser tests (need backend with `LLM_PROVIDER=fake` on :8000 and the frontend on :5173): `cd e2e ; npm ci ; node workbench.mjs ; node landing.mjs ; node motion.mjs ; node axe.mjs ; node ui.mjs`.
CI runs all five. Set `CHROME_PATH` if Chrome is not in a standard location.

Frontend unit test for the browser-side evaluator: `cd frontend ; npm run test:mirror` (Node 22+).
Any unknown URL redirects to `/`. The single-process deploy serves every route from `index.html`, so refreshing on `/how-it-works` works.

### 3D scene notes
- three.js is lazy-loaded: it only downloads on `/` and `/how-it-works`, never in Studio (`frontend/src/components/three/`).
- No WebGL, a render error, or `?fx=off` in the URL falls back to a plain 2D card. `prefers-reduced-motion` shows one still frame.
- Studio uses a dark theme (`.studio-dark` in `index.css` flips the colour palette) and a custom Monaco theme (`components/monacoTheme.ts`) chosen for WCAG contrast.
