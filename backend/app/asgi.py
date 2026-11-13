"""Production entrypoint: ONE process serves the API (under /api) and the built React UI.

Local dev is unchanged (Vite proxy + app.main:app). On Render: uvicorn app.asgi:app
"""
import os
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from app.core.config import REPO_ROOT
from app.main import app as api_app

STATIC_DIR = Path(os.environ.get("YOG_STATIC_DIR", REPO_ROOT / "frontend" / "dist"))

@asynccontextmanager
async def lifespan(_: FastAPI):
    if not os.environ.get("YOG_NO_WARMUP"):
        from app.core import warmup
        warmup.start()                 # the mounted API app does not run its own startup events
    yield


app = FastAPI(title="YOG Studio (production)", lifespan=lifespan)

# What the built app really loads: its own files (Monaco is bundled, its worker is a same-origin file) and Google Fonts.
CSP = "; ".join([
    "default-src 'self'",
    "script-src 'self'",
    "style-src 'self' 'unsafe-inline' https://fonts.googleapis.com",
    "font-src 'self' data: https://fonts.gstatic.com",
    "img-src 'self' data: blob:",
    "worker-src 'self' blob:",
    "connect-src 'self'",
    "object-src 'none'",
    "base-uri 'self'",
    "form-action 'self'",
    "frame-ancestors 'none'",
])
STATIC_HEADERS = {
    "X-Content-Type-Options": "nosniff",
    "X-Frame-Options": "DENY",
    "Referrer-Policy": "strict-origin-when-cross-origin",
    "Permissions-Policy": "camera=(), microphone=(), geolocation=(), payment=(), usb=()",
    "Cross-Origin-Opener-Policy": "same-origin",
}


@app.middleware("http")
async def security_headers(request: Request, call_next):
    """CSP_MODE=enforce (default) | report-only (if a browser blocks something it should not) | off."""
    response = await call_next(request)
    for k, v in STATIC_HEADERS.items():
        response.headers.setdefault(k, v)
    mode = os.environ.get("CSP_MODE", "enforce").lower()
    if mode != "off":
        response.headers.setdefault("Content-Security-Policy-Report-Only" if mode == "report-only" else "Content-Security-Policy", CSP)
    if request.url.scheme == "https" or request.headers.get("x-forwarded-proto") == "https":
        response.headers.setdefault("Strict-Transport-Security", "max-age=15552000")
    if request.url.path.startswith("/api"):
        response.headers["Cache-Control"] = "no-store"        # responses can hold a visitor's own policies
    return response


# The auto-generated API pages list every route and parameter; the public site has no use for them.
_HIDDEN = {"/docs", "/redoc", "/openapi.json", "/docs/oauth2-redirect"}
api_app.router.routes[:] = [r for r in api_app.router.routes if getattr(r, "path", None) not in _HIDDEN]
api_app.openapi_url = None

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
