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

Tests: `cd backend ; uv run pytest -q`
Frontend type-check/build: `cd frontend ; npm run build`
LLM: defaults to the offline `fake` provider. Copy `.env.example` to `backend/.env` and set `LLM_PROVIDER=gemini` + `GEMINI_API_KEY` to use Gemini.
