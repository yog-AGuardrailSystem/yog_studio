"""Tests must never reach a real LLM, whatever backend/.env says."""
import os

os.environ["YOG_NO_WARMUP"] = "1"          # no background index build in tests
os.environ["YOG_NO_DOTENV"] = "1"          # never read backend/.env in tests
os.environ["LLM_PROVIDER"] = "fake"          # set before app modules read config; dotenv does not override it
for _k in ("GEMINI_API_KEY", "ANTHROPIC_API_KEY"):
    os.environ[_k] = ""                      # a key in backend/.env must never make a test reach a live LLM

import pytest  # noqa: E402


@pytest.fixture(autouse=True)
def _isolate_llm_and_caches(tmp_path_factory, monkeypatch):
    from app.core import config
    monkeypatch.setattr(config, "DATA_DIR", tmp_path_factory.mktemp("data"))      # sessions never touch backend/data
    from app.api.deps import get_adapter
    from app.api.device import get_sim
    from app.api.retrieve import get_retriever, retriever_for
    from app.core import guard
    from app.llm.factory import get_provider, offline_provider, real_provider
    fns = (get_provider, get_retriever, retriever_for, get_adapter, get_sim, offline_provider, real_provider)
    for fn in fns:
        fn.cache_clear()
    guard.limiter._buckets.clear()
    from app.core import metrics
    metrics.reset()
    guard.budget._used = 0
    yield
    for fn in fns:
        fn.cache_clear()
