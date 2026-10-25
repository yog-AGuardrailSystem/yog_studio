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
