import os
import time
import uuid

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from app.core import guard, log, metrics, session

from app.api import analyze, benchmark, check, compile, device, evaluate, examples, modify, policies, retrieve, samples, studio, translate

app = FastAPI(title="YOG Studio")
log.setup()


@app.exception_handler(RequestValidationError)
async def invalid_request(request: Request, exc: RequestValidationError) -> JSONResponse:
    """422 without echoing the request body back (FastAPI's default does, and fails on non-UTF-8 bytes)."""
    errors = [{"loc": list(e.get("loc", [])), "msg": e.get("msg", ""), "type": e.get("type", "")} for e in exc.errors()]
    return JSONResponse(status_code=422, content={"detail": errors})


@app.exception_handler(Exception)
async def unexpected(request: Request, exc: Exception) -> JSONResponse:
    """Anything unforeseen: a generic message and an id to find it in the logs; no internals leave the server."""
    rid = getattr(request.state, "rid", None) or uuid.uuid4().hex[:12]
    log.error_line(rid, request.method, request.url.path)
    metrics.inc("errors_5xx")
    return JSONResponse(status_code=500, headers={"X-Request-Id": rid},
                        content={"detail": "Something went wrong on the server.", "request_id": rid})

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173", "http://127.0.0.1:5173"],
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.middleware("http")
async def visitor_session(request: Request, call_next):
    """Give every browser its own anonymous id (HttpOnly cookie) so visitors never share policies or devices."""
    sid = request.cookies.get(session.COOKIE)
    fresh = not session.acceptable_cookie(sid)
    if fresh:
        sid = session.new_sid()
        session.maybe_cleanup()
    request.state.sid = sid
    request.state.fresh = fresh            # a session minted by this very request (no cookie, or a malformed one)
    response = await call_next(request)
    if fresh:
        https = request.url.scheme == "https" or request.headers.get("x-forwarded-proto") == "https"
        response.set_cookie(session.COOKIE, sid, max_age=session.MAX_AGE, httponly=True, samesite="lax", secure=https, path="/")
    return response


@app.middleware("http")
async def protect(request: Request, call_next):
    """Refuse oversized bodies and rate-limit every write request per client (see app/core/guard.py)."""
    if request.method in ("POST", "PUT", "PATCH", "DELETE"):
        if request.headers.get("transfer-encoding"):
            # A chunked body has no Content-Length, so the cap below could not see it and the whole stream would be
            # buffered in memory. Browsers and the supplied clients always send a length; refuse the rest.
            return JSONResponse(status_code=411, content={"detail": "Send a Content-Length header; chunked uploads are not accepted."})
        length = request.headers.get("content-length", "")
        if length and not length.isdigit():
            return JSONResponse(status_code=400, content={"detail": "Bad Content-Length header."})
        if length.isdigit() and int(length) > guard._num("MAX_BODY_BYTES", 1_500_000):
            return JSONResponse(status_code=413, content={"detail": "That request is too large."})
        ok, wait = guard.limiter.allow("write", guard.client_ip(request), guard._num("RATE_LIMIT_PER_MIN", 120))
        if not ok:
            metrics.inc("rate_limited")
            return JSONResponse(status_code=429, headers={"Retry-After": str(max(1, round(wait)))},
                                content={"detail": f"Too many requests. Try again in {max(1, round(wait))} s."})
    return await call_next(request)


@app.middleware("http")
async def access_log(request: Request, call_next):
    rid = uuid.uuid4().hex[:12]
    request.state.rid = rid
    started = time.perf_counter()
    response = await call_next(request)
    response.headers["X-Request-Id"] = rid
    metrics.inc("requests")
    metrics.inc(f"status_{response.status_code // 100}xx")
    log.request_line(rid, request.method, request.url.path, response.status_code, started)
    return response


@app.on_event("startup")
def _warm_up() -> None:
    if not os.environ.get("YOG_NO_WARMUP"):
        from app.core import warmup
        warmup.start()


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


@app.get("/status")
def status() -> dict:
    """Operational snapshot for whoever runs the site: is every part usable, and how busy is it. No secrets, no user data."""
    from app.api.deps import get_adapter
    from app.engine.c_lexer import find_binary
    from app.llm.factory import get_provider, live_status
    from app.llm.provider import LLMError
    adapter = get_adapter()
    try:
        engine_ok = bool(adapter.compile_info("fact a(b)\n").ok)
    except Exception:                                      # noqa: BLE001
        engine_ok = False
    try:
        provider = get_provider().name
    except LLMError:
        provider = "error"
    cap = int(guard._num("LIVE_LLM_DAILY_CAP", 300))
    return {"status": "ok" if engine_ok else "degraded", "engine_ok": engine_ok, "c_lexer": find_binary(build=False) is not None,
            "provider": provider, **live_status(), "live_budget": guard.budget.snapshot(cap), "counters": metrics.snapshot()}


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
app.include_router(studio.router)
