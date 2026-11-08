# Running YOG Studio

One-time setup:
```
uv python install 3.12
cd backend ; uv sync --extra dev
cd ../frontend ; npm install
```
Run both (Windows): `.\scripts\dev.ps1`  -> backend http://localhost:8000/docs, frontend http://localhost:5173

Or separately:
```
cd backend  ; uv run python -m uvicorn app.main:app --reload --port 8000
cd frontend ; npm run dev
```
(`uv run uvicorn` can be blocked by Windows Application Control; `python -m uvicorn` is not.)

Tests: `cd backend ; uv run pytest -q` (offline; forces the fake LLM). Frontend: `cd frontend ; npm run build`.
Browser walkthrough: `e2e/README.md`. Benchmark: `cd backend ; uv run python -m app.benchmark.runner`.

## Configuration (`backend/.env`, see `.env.example`)
- `LLM_PROVIDER=fake` (default, offline) or `gemini` with `GEMINI_API_KEY`.
- `YOG_ENGINE=python` (default) or `c` (not yet available, see app/engine/c_engine.py).

## Data
Approved policies are saved to `backend/data/policies/` (git-ignored). The retrieval index is `backend/data/index.npz`.

## Deploying to Render (free)
See the "Deploy" section in docs/DEPLOY.md.

## Pages (frontend routes)
| Route | What it is |
|---|---|
| `/` | Landing page with a live 3D scene (an agent action flies at the YOG gate; pick an action and watch ALLOW/DENY) |
| `/how-it-works` | Scroll-driven walkthrough with an interactive device demo (runs in the browser, mirrors YOG rules in `frontend/src/lib/yogMirror.ts`; step 7 drives the same 3D scene) |
| `/studio` | Step 1: upload an agent |
| `/rules`, `/review`, `/modify`, `/device` | Steps 2-5 |
| `/check` | Sandbox: try a policy on one action |

Frontend unit test for the browser-side evaluator: `cd frontend ; npm run test:mirror` (Node 22+).
Any unknown URL redirects to `/`. The single-process deploy serves every route from `index.html`, so refreshing on `/how-it-works` works.

### 3D scene notes
- three.js is lazy-loaded: it only downloads on `/` and `/how-it-works`, never in Studio (`frontend/src/components/three/`).
- No WebGL, a render error, or `?fx=off` in the URL falls back to a plain 2D card. `prefers-reduced-motion` shows one still frame.
- Studio uses a dark theme (`.studio-dark` in `index.css` flips the colour palette) and a custom Monaco theme (`components/monacoTheme.ts`) chosen for WCAG contrast.
