from functools import lru_cache

from app.engine.adapter import EngineAdapter
from app.engine.python_prototype import PythonPrototypeAdapter


def get_llm():
    """Dependency wrapper so tests (and later callers) can override the LLM provider."""
    from app.llm.factory import get_provider
    return get_provider()


@lru_cache(maxsize=1)
def get_adapter() -> EngineAdapter:
    """The ONE place that chooses the engine. Swap for CEngineAdapter here later."""
    return PythonPrototypeAdapter()
