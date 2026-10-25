"""Embed-once, cosine-with-numpy retriever over the example pairs. No vector DB (CLAUDE.md section 5)."""
import hashlib
import json
from pathlib import Path

import numpy as np
from pydantic import BaseModel

from app.core.config import DATA_DIR
from app.llm.provider import LLMProvider
from app.rag.examples import PolicyExample, load_examples

INDEX_PATH = DATA_DIR / "index.npz"


class Retrieved(BaseModel):
    id: str
    english: str
    tools_context: list[str]
    gold_yog: str
    score: float


def example_text(ex: PolicyExample) -> str:
    """What gets embedded: the English rule plus the tool names it talks about."""
    tools = " ".join(t.split("(")[0] for t in ex.tools_context)
    return f"{ex.english} {tools}"


def query_text(english: str, tools: list[str] | None) -> str:
    return f"{english} {' '.join(tools or [])}"


def _fingerprint(provider: LLMProvider, examples: list[PolicyExample]) -> str:
    h = hashlib.sha256(provider.name.encode())
    for e in examples:
        h.update(e.id.encode())
        h.update(example_text(e).encode())
    return h.hexdigest()


class Retriever:
    def __init__(self, provider: LLMProvider, examples: list[PolicyExample] | None = None,
                 index_path: Path = INDEX_PATH) -> None:
        self.provider = provider
        self.examples = examples if examples is not None else load_examples()
        self.index_path = index_path
        self._matrix: np.ndarray | None = None

    # -- index ----------------------------------------------------------
    def build_index(self) -> int:
        vecs = np.array(self.provider.embed([example_text(e) for e in self.examples]), dtype=np.float32)
        vecs = vecs / np.maximum(np.linalg.norm(vecs, axis=1, keepdims=True), 1e-9)
        self.index_path.parent.mkdir(parents=True, exist_ok=True)
        np.savez(self.index_path, vectors=vecs, meta=json.dumps(
            {"fingerprint": _fingerprint(self.provider, self.examples), "ids": [e.id for e in self.examples]}))
        self._matrix = vecs
        return len(self.examples)

    def _load(self) -> np.ndarray:
        if self._matrix is not None:
            return self._matrix
        want = _fingerprint(self.provider, self.examples)
        if self.index_path.exists():
            try:
                with np.load(self.index_path, allow_pickle=False) as z:
                    meta = json.loads(str(z["meta"]))
                    if meta.get("fingerprint") == want:
                        self._matrix = z["vectors"]
                        return self._matrix
            except (OSError, ValueError, KeyError):
                pass                                        # corrupt / unreadable -> rebuild below
        self.build_index()                                  # missing or stale (examples/provider changed)
        assert self._matrix is not None
        return self._matrix

    # -- query ----------------------------------------------------------
    def search(self, english: str, tools: list[str] | None = None, k: int = 3) -> list[Retrieved]:
        if not english.strip():
            return []
        matrix = self._load()
        q = np.array(self.provider.embed([query_text(english, tools)])[0], dtype=np.float32)
        q = q / max(float(np.linalg.norm(q)), 1e-9)
        scores = matrix @ q
        order = np.argsort(-scores, kind="stable")[: max(0, k)]
        return [Retrieved(id=self.examples[i].id, english=self.examples[i].english,
                          tools_context=self.examples[i].tools_context, gold_yog=self.examples[i].gold_yog,
                          score=round(float(scores[i]), 4)) for i in order]


if __name__ == "__main__":                                   # python -m app.rag.retriever  -> rebuild index
    from app.llm.factory import get_provider
    n = Retriever(get_provider()).build_index()
    print(f"indexed {n} examples -> {INDEX_PATH}")
