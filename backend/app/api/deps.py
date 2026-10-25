from functools import lru_cache

from app.engine.adapter import EngineAdapter
from app.engine.python_prototype import PythonPrototypeAdapter


@lru_cache(maxsize=1)
def get_adapter() -> EngineAdapter:
    """The ONE place that chooses the engine. Swap for CEngineAdapter here later."""
    return PythonPrototypeAdapter()
