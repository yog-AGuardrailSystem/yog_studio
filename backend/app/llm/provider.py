"""The ONE interface every LLM call goes through (CLAUDE.md principle 6). Prompts live in llm/prompts/*.md."""
import threading
from abc import ABC, abstractmethod
from dataclasses import asdict, dataclass
from pathlib import Path

PROMPTS_DIR = Path(__file__).resolve().parent / "prompts"


class LLMError(Exception):
    """Provider call failed (network, auth, quota, bad response)."""


@dataclass
class Usage:
    """What a provider has spent since it was created (or since reset()). Thread-safe."""
    calls: int = 0
    embed_calls: int = 0
    prompt_tokens: int = 0
    output_tokens: int = 0
    retries: int = 0
    waited_seconds: float = 0.0
    cache_hits: int = 0

    def __post_init__(self) -> None:
        self._lock = threading.Lock()

    def add(self, **delta: int | float) -> None:
        with self._lock:
            for k, v in delta.items():
                setattr(self, k, getattr(self, k) + v)

    def reset(self) -> None:
        with self._lock:
            for k in asdict(self):
                setattr(self, k, 0 if k != "waited_seconds" else 0.0)

    def snapshot(self) -> dict:
        with self._lock:
            return {**asdict(self), "waited_seconds": round(self.waited_seconds, 2)}


class LLMProvider(ABC):
    name: str = "abstract"
    model: str | None = None
    embed_model: str | None = None
    # Capabilities are advertised, so callers never pass an argument a provider (or a test double) cannot take.
    supports_json_schema: bool = False
    supports_embed_task: bool = False

    @property
    def usage(self) -> Usage:
        u = self.__dict__.get("_usage")
        if u is None:
            u = self.__dict__["_usage"] = Usage()
        return u

    @abstractmethod
    def generate(self, prompt: str, system: str | None = None) -> str:
        """Return the model's text reply. Providers with supports_json_schema also accept `json_schema=`."""

    @abstractmethod
    def embed(self, texts: list[str]) -> list[list[float]]:
        """Return one embedding vector per input text. Providers with supports_embed_task also accept `task=`."""


def generate_text(provider: LLMProvider, prompt: str, system: str | None = None,
                  json_schema: dict | None = None) -> str:
    """generate(), passing json_schema only to providers that declare they can use it."""
    if json_schema is not None and provider.supports_json_schema:
        return provider.generate(prompt, system, json_schema=json_schema)  # type: ignore[call-arg]
    return provider.generate(prompt, system)


def embed_texts(provider: LLMProvider, texts: list[str], task: str | None = None) -> list[list[float]]:
    """embed(), passing the retrieval task ('document' | 'query') only to providers that can use it."""
    if task is not None and provider.supports_embed_task:
        return provider.embed(texts, task=task)  # type: ignore[call-arg]
    return provider.embed(texts)


def load_prompt(name: str) -> str:
    """Prompts are files, not inline strings."""
    return (PROMPTS_DIR / f"{name}.md").read_text(encoding="utf-8")
