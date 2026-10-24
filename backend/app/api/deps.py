import os
from functools import lru_cache

from app.engine.adapter import EngineAdapter
from app.engine.python_prototype import PythonPrototypeAdapter


def get_llm():
    """Dependency wrapper so tests (and later callers) can override the LLM provider."""
    from app.llm.factory import get_provider
    return get_provider()


@lru_cache(maxsize=1)
def get_adapter() -> EngineAdapter:
    """The ONE place that chooses the engine. YOG_ENGINE=python (default) | c.

    Asking for `c` when it is unavailable is an error, never a silent fallback: a guardrail must not quietly
    run on a different engine than the operator asked for.
    """
    which = os.environ.get("YOG_ENGINE", "python").lower()
    if which == "python":
        return PythonPrototypeAdapter()
    if which == "c":
        from app.engine.c_engine import CEngineAdapter
        return CEngineAdapter()
    raise RuntimeError(f"unknown YOG_ENGINE {which!r} (use 'python' or 'c')")
