"""Production entrypoint: ONE process serves the API (under /api) and the built React UI.

Local dev is unchanged (Vite proxy + app.main:app). On Render: uvicorn app.asgi:app
"""
import os
from pathlib import Path

from fastapi import FastAPI
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from app.core.config import REPO_ROOT
from app.main import app as api_app

STATIC_DIR = Path(os.environ.get("YOG_STATIC_DIR", REPO_ROOT / "frontend" / "dist"))

app = FastAPI(title="YOG Studio (production)")
app.mount("/api", api_app)           # same routes the Vite proxy exposes as /api/*

if STATIC_DIR.is_dir():
    index = STATIC_DIR / "index.html"
    app.mount("/assets", StaticFiles(directory=STATIC_DIR / "assets"), name="assets")

    @app.get("/{path:path}", include_in_schema=False)
    def spa(path: str) -> FileResponse:
        """Real files (favicon etc.) are served as-is; any other path is a client-side route -> index.html."""
        target = (STATIC_DIR / path).resolve()
        if path and STATIC_DIR.resolve() in target.parents and target.is_file():
            return FileResponse(target)
        return FileResponse(index)
