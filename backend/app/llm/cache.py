"""On-disk cache for LLM calls, as a wrapper around any provider.

Embeddings are deterministic, so caching them is always safe (and saves quota on every index rebuild). Generation is
cached only when asked (benchmarks): the key is the exact prompt + model + schema, so a rerun of the same benchmark is
free and reproducible, and changing a prompt or model never returns a stale answer. One small sqlite file, no server.
"""
import hashlib
import json
import sqlite3
import threading
from pathlib import Path

from app.llm.provider import LLMProvider, Usage


class KVCache:
    def __init__(self, path: Path) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        self._db = sqlite3.connect(str(path), check_same_thread=False)
        self._lock = threading.Lock()
        with self._lock:
            self._db.execute("CREATE TABLE IF NOT EXISTS kv (key TEXT PRIMARY KEY, value TEXT NOT NULL)")
            self._db.commit()

    def get(self, key: str) -> str | None:
        with self._lock:
            row = self._db.execute("SELECT value FROM kv WHERE key = ?", (key,)).fetchone()
        return row[0] if row else None

    def set_many(self, items: dict[str, str]) -> None:
        with self._lock:
            self._db.executemany("INSERT OR REPLACE INTO kv (key, value) VALUES (?, ?)", list(items.items()))
            self._db.commit()

    def close(self) -> None:
        with self._lock:
            self._db.close()


def _key(*parts) -> str:
    return hashlib.sha256(json.dumps(parts, sort_keys=True, ensure_ascii=False).encode("utf-8")).hexdigest()


class CachingProvider(LLMProvider):
    """Same interface and capabilities as `base`; identical calls are answered from disk."""

    def __init__(self, base: LLMProvider, cache: KVCache, *, cache_generate: bool = False, cache_embed: bool = True) -> None:
        self.base, self.cache = base, cache
        self.cache_generate, self.cache_embed = cache_generate, cache_embed
        self.name, self.model, self.embed_model = base.name, base.model, base.embed_model
        self.supports_json_schema, self.supports_embed_task = base.supports_json_schema, base.supports_embed_task

    @property
    def usage(self) -> Usage:
        return self.base.usage

    def generate(self, prompt: str, system: str | None = None, *, json_schema: dict | None = None) -> str:
        call = (lambda: self.base.generate(prompt, system, json_schema=json_schema)) if json_schema is not None \
            else (lambda: self.base.generate(prompt, system))
        if not self.cache_generate:
            return call()
        key = _key("gen", self.base.name, self.base.model, system, prompt, json_schema)
        hit = self.cache.get(key)
        if hit is not None:
            self.usage.add(cache_hits=1)
            return hit
        text = call()
        self.cache.set_many({key: text})
        return text

    def embed(self, texts: list[str], task: str | None = None) -> list[list[float]]:
        def run(batch: list[str]) -> list[list[float]]:
            return self.base.embed(batch, task=task) if (task is not None and self.base.supports_embed_task) \
                else self.base.embed(batch)
        if not self.cache_embed:
            return run(texts)
        keys = [_key("emb", self.base.name, self.base.embed_model, task, t) for t in texts]
        found = {k: self.cache.get(k) for k in set(keys)}
        missing = [(i, t) for i, (k, t) in enumerate(zip(keys, texts)) if found[k] is None]
        if missing:
            vectors = run([t for _, t in missing])
            self.cache.set_many({keys[i]: json.dumps(v) for (i, _), v in zip(missing, vectors)})
            for (i, _), v in zip(missing, vectors):
                found[keys[i]] = json.dumps(v)
        self.usage.add(cache_hits=len(texts) - len(missing))
        return [json.loads(found[k]) for k in keys]  # type: ignore[arg-type]
