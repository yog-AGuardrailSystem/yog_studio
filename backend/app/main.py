import os

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from app.core import guard

from app.api import analyze, benchmark, check, compile, device, evaluate, examples, modify, policies, retrieve, samples, translate

app = FastAPI(title="YOG Studio")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173", "http://127.0.0.1:5173"],
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.middleware("http")
async def protect(request: Request, call_next):
    """Refuse oversized bodies and rate-limit every write request per client (see app/core/guard.py)."""
    if request.method in ("POST", "PUT", "PATCH", "DELETE"):
        length = request.headers.get("content-length", "")
        if length.isdigit() and int(length) > guard._num("MAX_BODY_BYTES", 1_500_000):
            return JSONResponse(status_code=413, content={"detail": "That request is too large."})
        ok, wait = guard.limiter.allow("write", guard.client_ip(request), guard._num("RATE_LIMIT_PER_MIN", 120))
        if not ok:
            return JSONResponse(status_code=429, headers={"Retry-After": str(max(1, round(wait)))},
                                content={"detail": f"Too many requests. Try again in {max(1, round(wait))} s."})
    return await call_next(request)


@app.get("/health")
def health() -> dict:
    return {"status": "ok"}


@app.get("/info")
def info() -> dict:
    """What this server is really running, so the UI can say so (e.g. an offline demo mode banner)."""
    from app.api.deps import get_adapter
    from app.engine.c_lexer import find_binary
    from app.llm.factory import get_provider, live_status
    from app.llm.provider import LLMError
    try:
        prov = get_provider()
        provider, model = prov.name, getattr(prov, "model", None)
    except LLMError as e:
        provider, model = "error", str(e)
    adapter = get_adapter()
    return {
        "provider": provider,
        "model": model,
        "offline_demo": provider == "fake",     # drafts are copied examples, not translated
        "default_mode": "offline" if provider in ("fake", "error") else "real",
        **live_status(),                         # live_available / live_allowed / live_ready / live_reason / live_provider
        "engine": "python-reference" if adapter.__class__.__name__ == "PythonPrototypeAdapter" else "c",
        "c_lexer": find_binary(build=False) is not None,
        "commit": os.environ.get("RENDER_GIT_COMMIT") or os.environ.get("GIT_COMMIT") or "unknown",
    }


@app.get("/version")
def version() -> dict:
    """Which commit is running. Render sets RENDER_GIT_COMMIT; CI's smoke test waits for it to match the merge."""
    return {"commit": os.environ.get("RENDER_GIT_COMMIT") or os.environ.get("GIT_COMMIT") or "unknown"}


app.include_router(check.router)
app.include_router(benchmark.router)
app.include_router(compile.router)
app.include_router(examples.router)
app.include_router(analyze.router)
app.include_router(samples.router)
app.include_router(retrieve.router)
app.include_router(translate.router)
app.include_router(policies.router)
app.include_router(evaluate.router)
app.include_router(modify.router)
app.include_router(device.router)
