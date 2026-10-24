"""The ONE interface every LLM call goes through (CLAUDE.md principle 6). Prompts live in llm/prompts/*.md."""
from abc import ABC, abstractmethod
from pathlib import Path

PROMPTS_DIR = Path(__file__).resolve().parent / "prompts"


class LLMError(Exception):
    """Provider call failed (network, auth, quota, bad response)."""


class LLMProvider(ABC):
    name: str = "abstract"

    @abstractmethod
    def generate(self, prompt: str, system: str | None = None) -> str:
        """Return the model's text reply."""

    @abstractmethod
    def embed(self, texts: list[str]) -> list[list[float]]:
        """Return one embedding vector per input text."""


def load_prompt(name: str) -> str:
    """Prompts are files, not inline strings."""
    return (PROMPTS_DIR / f"{name}.md").read_text(encoding="utf-8")
