import os
from functools import lru_cache

from app.engine.adapter import EngineAdapter
from app.engine.python_prototype import PythonPrototypeAdapter


def get_llm():
    """Dependency wrapper so tests (and later callers) can override the LLM provider."""
    from app.llm.factory import get_provider
    return get_provider()


def enforce_live_default(provider, request) -> None:
    """The live-AI protections (ALLOW_LIVE_LLM kill switch, per-client rate limit, daily budget) must follow the provider
    that actually makes the call, not only the per-request `mode=real` flag. When the operator makes a live provider the
    server default (LLM_PROVIDER=gemini|claude), a request that simply omits `mode` would otherwise skip all three."""
    if getattr(provider, "name", "fake") == "fake":
        return
    from fastapi import HTTPException
    from app.core import guard
    from app.llm.factory import live_allowed
    if not live_allowed():
        raise HTTPException(status_code=409, detail="Live AI is switched off on this server. Use Offline mode.")
    guard.live_guard(request)


@lru_cache(maxsize=1)
def get_adapter() -> EngineAdapter:
    """The ONE place that chooses the engine. YOG_ENGINE=python (default) | c.

    Asking for `c` when it is unavailable is an error, never a silent fallback: a guardrail must not quietly
    run on a different engine than the operator asked for.
    """
    return make_adapter(os.environ.get("YOG_ENGINE", "python"))


def make_adapter(which: str) -> EngineAdapter:
    """An adapter by name ('python' | 'c'), for the server (above) and the command-line tools (benchmark --engine)."""
    which = which.lower()
    if which == "python":
        return PythonPrototypeAdapter()
    if which == "c":
        from app.engine.c_engine import CEngineAdapter
        return CEngineAdapter()
    raise RuntimeError(f"unknown YOG_ENGINE {which!r} (use 'python' or 'c')")
