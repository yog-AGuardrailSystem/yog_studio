import os
from functools import lru_cache
from pathlib import Path

from dotenv import load_dotenv

from app.core.config import DATA_DIR, REPO_ROOT
from app.llm.composite import CompositeProvider
from app.llm.fake import FakeProvider
from app.llm.provider import LLMError, LLMProvider

DEFAULT_GEMINI_MODEL = "gemini-3.6-flash"          # stable; gemini-3.5-flash-lite is the cheaper choice
DEFAULT_GEMINI_EMBED = "gemini-embedding-2"        # text-embedding-004 and gemini-2.0-flash are retired
DEFAULT_CLAUDE_MODEL = "claude-opus-5-5"


def _load_env() -> None:
    """Read backend/.env (never overriding real environment variables). Tests set YOG_NO_DOTENV so a developer's
    local keys can never leak into them."""
    if not os.getenv("YOG_NO_DOTENV"):
        load_dotenv(REPO_ROOT / "backend" / ".env")


def _flag(name: str, default: bool) -> bool:
    raw = os.getenv(name)
    return default if raw is None else raw.strip().lower() in ("1", "true", "yes", "on")


def _float(name: str, default: float) -> float:
    try:
        return float(os.getenv(name, default))
    except ValueError:
        raise LLMError(f"{name} must be a number") from None


def _gemini() -> LLMProvider:
    from app.llm.gemini import GeminiProvider
    return GeminiProvider(
        os.getenv("GEMINI_API_KEY", ""),
        os.getenv("GEMINI_MODEL", DEFAULT_GEMINI_MODEL),
        os.getenv("GEMINI_EMBED_MODEL", DEFAULT_GEMINI_EMBED),
        timeout=_float("GEMINI_TIMEOUT", 60.0),
        rpm=_float("GEMINI_RPM", 10.0),
        max_output_tokens=int(_float("GEMINI_MAX_OUTPUT_TOKENS", 8192)),
        embed_dims=int(_float("GEMINI_EMBED_DIMS", 768)),
    )


def _claude() -> LLMProvider:
    from app.llm.claude import ClaudeProvider
    return ClaudeProvider(
        os.getenv("ANTHROPIC_API_KEY", ""),
        os.getenv("CLAUDE_MODEL", DEFAULT_CLAUDE_MODEL),
        effort=os.getenv("CLAUDE_EFFORT", "medium"),
        max_tokens=int(_float("CLAUDE_MAX_TOKENS", 16000)),
        fallback_model=os.getenv("CLAUDE_FALLBACK_MODEL") or None,
    )


def _build(which: str, role: str) -> LLMProvider:
    if which == "fake":
        return FakeProvider()
    if which == "gemini":
        return _gemini()
    if which == "claude":
        if role == "embed":
            raise LLMError("EMBED_PROVIDER cannot be 'claude' (Claude has no embeddings endpoint; use gemini)")
        return _claude()
    raise LLMError(f"unknown {'LLM' if role == 'generate' else 'EMBED'}_PROVIDER {which!r}")


def _assemble(gen_name: str, emb_name: str) -> LLMProvider:
    generator = _build(gen_name, "generate")
    provider: LLMProvider = generator if emb_name == gen_name else CompositeProvider(generator, _build(emb_name, "embed"))
    if gen_name != "fake" or emb_name != "fake":
        from app.llm.cache import CachingProvider, KVCache
        path = Path(os.getenv("LLM_CACHE_PATH", str(DATA_DIR / "llm_cache.sqlite")))
        provider = CachingProvider(provider, KVCache(path), cache_generate=_flag("LLM_CACHE_GENERATE", False),
                                   cache_embed=_flag("LLM_CACHE_EMBED", True))
    return provider


@lru_cache(maxsize=1)
def get_provider() -> LLMProvider:
    """The ONE place that picks the default LLM.

    LLM_PROVIDER    fake (default, offline) | gemini | claude         -> who writes the policy
    EMBED_PROVIDER  defaults to the same provider, or gemini if LLM_PROVIDER=claude  -> who embeds for retrieval
    LLM_CACHE_EMBED (default on for real providers) / LLM_CACHE_GENERATE (default off; benchmarks turn it on)
    """
    _load_env()
    gen_name = os.getenv("LLM_PROVIDER", "fake").lower()
    emb_name = os.getenv("EMBED_PROVIDER", "gemini" if gen_name == "claude" else gen_name).lower()
    if gen_name not in ("fake", "gemini", "claude"):
        raise LLMError(f"unknown LLM_PROVIDER {gen_name!r}")
    return _assemble(gen_name, emb_name)


# ---------------------------------------------------------------- the Real LLM / Offline switch (per request)

def real_names() -> tuple[str, str] | None:
    """(generator, embedder) for the Real mode, or None when this server has no key to run one.

    A server whose LLM_PROVIDER is gemini/claude uses that. Otherwise Real means Gemini when GEMINI_API_KEY is set,
    else Claude (with Gemini embeddings, so it also needs the Gemini key) -- the key is the operator's opt-in."""
    _load_env()
    gemini, claude = bool(os.getenv("GEMINI_API_KEY")), bool(os.getenv("ANTHROPIC_API_KEY"))
    configured = os.getenv("LLM_PROVIDER", "fake").lower()
    if configured in ("gemini", "claude"):
        gen = configured
    elif gemini:
        gen = "gemini"
    elif claude:
        gen = "claude"
    else:
        return None
    if gen == "gemini" and not gemini:
        return None
    if gen == "claude" and not (claude and gemini):
        return None                                       # Claude has no embeddings endpoint: retrieval needs the Gemini key
    emb = os.getenv("EMBED_PROVIDER", "gemini").lower() if gen == "claude" else os.getenv("EMBED_PROVIDER", gen).lower()
    return gen, emb


def live_allowed() -> bool:
    """The operator can switch live AI off for a deployment with ALLOW_LIVE_LLM=0."""
    return _flag("ALLOW_LIVE_LLM", True)


def live_status() -> dict:
    names = real_names()
    allowed = live_allowed()
    if names is None:
        reason = "no API key is configured on this server"
    elif not allowed:
        reason = "live AI is switched off on this server"
    else:
        reason = None
    return {"live_available": names is not None, "live_allowed": allowed, "live_ready": names is not None and allowed,
            "live_reason": reason, "live_provider": names[0] if names else None}


@lru_cache(maxsize=1)
def real_provider() -> LLMProvider:
    names = real_names()
    if names is None:
        raise LLMError("Real LLM mode is unavailable: no API key is configured on this server")
    return _assemble(*names)


@lru_cache(maxsize=1)
def offline_provider() -> LLMProvider:
    return FakeProvider()


def get_provider_for(mode: str | None) -> LLMProvider:
    """mode None = the server default (get_provider); 'offline' = the local fake; 'real' = the configured live LLM."""
    if mode is None:
        return get_provider()
    if mode == "offline":
        return offline_provider()
    if mode == "real":
        if not live_allowed():
            raise LLMError("Real LLM mode is switched off on this server")
        return real_provider()
    raise LLMError(f"unknown mode {mode!r} (use 'real' or 'offline')")
