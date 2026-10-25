import os
from functools import lru_cache

from dotenv import load_dotenv

from app.core.config import REPO_ROOT
from app.llm.fake import FakeProvider
from app.llm.provider import LLMError, LLMProvider


@lru_cache(maxsize=1)
def get_provider() -> LLMProvider:
    """The ONE place that picks the LLM. LLM_PROVIDER=fake (default) | gemini."""
    load_dotenv(REPO_ROOT / "backend" / ".env")
    which = os.getenv("LLM_PROVIDER", "fake").lower()
    if which == "fake":
        return FakeProvider()
    if which == "gemini":
        from app.llm.gemini import GeminiProvider
        return GeminiProvider(os.getenv("GEMINI_API_KEY", ""),
                              os.getenv("GEMINI_MODEL", "gemini-2.0-flash"),
                              os.getenv("GEMINI_EMBED_MODEL", "text-embedding-004"))
    raise LLMError(f"unknown LLM_PROVIDER {which!r}")
