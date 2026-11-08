"""One provider that generates with one backend and embeds with another (Claude has no embeddings endpoint)."""
from app.llm.provider import LLMProvider


class _CombinedUsage:
    def __init__(self, a, b) -> None:
        self._a, self._b = a, b

    def snapshot(self) -> dict:
        x, y = self._a.snapshot(), self._b.snapshot()
        return {k: round(x[k] + y[k], 2) if isinstance(x[k], float) else x[k] + y[k] for k in x}

    def reset(self) -> None:
        self._a.reset()
        self._b.reset()

    def add(self, **delta) -> None:                       # callers only add to the generating side
        self._a.add(**delta)


class CompositeProvider(LLMProvider):
    def __init__(self, generator: LLMProvider, embedder: LLMProvider) -> None:
        self.generator, self.embedder = generator, embedder
        self.name = generator.name
        self.model, self.embed_model = generator.model, embedder.embed_model
        self.supports_json_schema = generator.supports_json_schema
        self.supports_embed_task = embedder.supports_embed_task
        self.embed_provider_name = embedder.name

    @property
    def usage(self):                                       # type: ignore[override]
        return _CombinedUsage(self.generator.usage, self.embedder.usage)

    def generate(self, prompt: str, system: str | None = None, *, json_schema: dict | None = None) -> str:
        if json_schema is not None:
            return self.generator.generate(prompt, system, json_schema=json_schema)
        return self.generator.generate(prompt, system)

    def embed(self, texts: list[str], task: str | None = None) -> list[list[float]]:
        if task is not None and self.embedder.supports_embed_task:
            return self.embedder.embed(texts, task=task)
        return self.embedder.embed(texts)
