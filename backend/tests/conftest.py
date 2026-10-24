"""Tests must never reach a real LLM, whatever backend/.env says."""
import os

os.environ["LLM_PROVIDER"] = "fake"          # set before app modules read config; dotenv does not override it

import pytest  # noqa: E402


@pytest.fixture(autouse=True)
def _isolate_llm_and_caches():
    from app.api.deps import get_adapter
    from app.api.device import get_sim
    from app.api.retrieve import get_retriever
    from app.llm.factory import get_provider
    for fn in (get_provider, get_retriever, get_adapter, get_sim):
        fn.cache_clear()
    yield
    for fn in (get_provider, get_retriever, get_adapter, get_sim):
        fn.cache_clear()
