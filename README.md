# YOG Studio

Turn plain-English rules into verified YOG policies for AI agents and MCP servers.

Upload a Python agent or MCP server → Studio finds its tools → you write rules in plain English → an LLM drafts a YOG
policy → the YOG engine checks it → you approve → Studio tests it on scenarios and gives you the policy plus a patched
copy of your agent that asks YOG before every tool call.

**The LLM drafts, the engine verifies, a human approves.** Nothing goes live without an explicit Approve.

## Engines

Studio runs the engine team's [yog_engine](https://github.com/yog-AGuardrailSystem/yog_engine) in two forms:

| | What | Where |
|---|---|---|
| **C compiler** (`yogc`) | Lexer, parser, semantic analysis, clause table, VM. **Makes the decisions** in the Docker image and CI. | `engine/c_front/` (pinned commit in its `VERSION`), `backend/app/engine/c_engine.py` |
| **Python reference** (`yog.py`) | The behavioural reference. Default for local development; supplies the parse tree and explanations. | `engine/yog.py`, `backend/app/engine/python_prototype.py` |

Every gold scenario gets the same decision and reason from both (`backend/tests/test_engine_conformance.py`). Choose with
`YOG_ENGINE=python|c`. Studio builds `yogc` itself with `cc`/`gcc`/`clang`, or uses `YOG_YOGC=/path/to/yogc`. Asking for
`c` when it is unavailable is an error, never a silent fallback.

## Run it

```
cd backend  && uv sync --extra dev && uv run python -m uvicorn app.main:app --reload --port 8000
cd frontend && npm ci && npm run dev          # http://localhost:5173
```
Windows: `.\scripts\dev.ps1`. Tests: `cd backend && uv run pytest -q` (add `YOG_ENGINE=c YOG_REQUIRE_C=1` for the C engine),
`cd frontend && npm run test:mirror && npm run build`. Docker: `docker build -t yog-studio . && docker run -p 10000:10000 yog-studio`.

## Docs

- [docs/RUNNING.md](docs/RUNNING.md): setup, configuration, benchmarks
- [docs/DEMO.md](docs/DEMO.md): the demo script
- [docs/decisions.md](docs/decisions.md): design decisions and where they depart from CLAUDE.md
- [docs/engine_issues.md](docs/engine_issues.md): engine behaviour Studio works around (for the engine team)
- [docs/claims-ledger.md](docs/claims-ledger.md): every claim on the landing page and what backs it
- [CLAUDE.md](CLAUDE.md): project brief and working rules
