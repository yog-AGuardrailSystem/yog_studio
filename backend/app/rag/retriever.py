"""Strict retriever over the example pairs. No vector DB (CLAUDE.md section 5): a numpy matrix is exact and instant for ~100 vectors.

Pipeline for one query:
  1. dense   cosine similarity between the query embedding and every example embedding (the provider's embedding model)
  2. lexical BM25 over stemmed words (same normaliser as the offline provider), catches exact terms embeddings blur
  3. fusion  reciprocal-rank fusion of the two rankings, weighted (default keyword weight 0: measured to help neither
             embedder, see default_lex_weight) + a small boost when the example is about the same tool names as the
             uploaded agent
  4. floor   an example is `relevant` only if its dense cosine clears a per-provider floor calibrated on held-out
             paraphrases and off-topic queries (benchmark/retrieval_floors.json). Nothing relevant => the caller must
             treat the draft as ungrounded instead of presenting weak matches as "similar solved examples".

One index file per provider+embedding model, so switching between Offline and a real LLM never rebuilds.
"""
import hashlib
import json
import math
import os
import re
from collections import Counter
from pathlib import Path

import numpy as np
from pydantic import BaseModel

from app.core.config import DATA_DIR, REPO_ROOT
from app.llm.fake import tokens as lex_tokens
from app.llm.provider import LLMProvider, embed_texts
from app.rag.examples import PolicyExample, load_examples

FLOORS_PATH = REPO_ROOT / "benchmark" / "retrieval_floors.json"
PROVISIONAL_FLOOR = 0.55          # used only when a provider has no calibrated floor yet (reported as uncalibrated)
RRF_K = 60
TOOL_BOOST = 0.008                # about half of one rank-1 contribution: a nudge, never an override


class Retrieved(BaseModel):
    id: str
    english: str
    tools_context: list[str]
    gold_yog: str
    score: float                  # dense cosine similarity (what the floor is calibrated on)
    source: str = "unknown"
    lexical: float = 0.0          # BM25, scaled to 0..1 within this query
    fused: float = 0.0            # rank-fusion score that decides the order
    relevant: bool = True         # dense score clears the provider's floor
    rerank: float | None = None   # 0..10 from the optional LLM reranker


def example_text(ex: PolicyExample) -> str:
    """What gets embedded: the English rule, same as the query side. Tool names are kept out on BOTH sides (they are
    matched separately by TOOL_BOOST), so a query and an example are compared on what the rule means."""
    return ex.english


def query_text(english: str, tools: list[str] | None = None) -> str:
    """The query is the rule alone. Tool names are NOT mixed in: they would make any rule that mentions a tool look
    similar to every example about that tool, and relevance must reflect what the rule means. Tools only nudge the
    ranking afterwards (TOOL_BOOST)."""
    return english


def _slug(s: str | None) -> str:
    return re.sub(r"[^a-z0-9]+", "-", (s or "default").lower()).strip("-") or "default"


def index_path_for(provider: LLMProvider, directory: Path | None = None) -> Path:
    return (directory or DATA_DIR) / f"index-{_slug(provider.name)}-{_slug(provider.embed_model)}.npz"


def _fingerprint(provider: LLMProvider, examples: list[PolicyExample]) -> str:
    h = hashlib.sha256(f"{provider.name}|{provider.embed_model}|{provider.supports_embed_task}".encode())
    for e in examples:
        h.update(e.id.encode())
        h.update(example_text(e).encode())
    return h.hexdigest()


def floor_key(provider: LLMProvider) -> str:
    return f"{provider.name}:{provider.embed_model or ''}"


def load_floors(path: Path = FLOORS_PATH) -> dict:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}


def floor_for(provider: LLMProvider, path: Path = FLOORS_PATH) -> tuple[float, bool]:
    """(floor, calibrated). RETRIEVAL_FLOOR overrides; otherwise the committed calibration; otherwise provisional."""
    env = os.getenv("RETRIEVAL_FLOOR")
    if env:
        try:
            return float(env), True
        except ValueError:
            pass
    entry = load_floors(path).get(floor_key(provider))
    if isinstance(entry, dict) and isinstance(entry.get("floor"), (int, float)):
        return float(entry["floor"]), True
    return PROVISIONAL_FLOOR, False


def default_lex_weight(provider: LLMProvider) -> float:
    """How much the keyword ranking counts next to the embedding ranking (1.0 = equally; RETRIEVAL_LEX_WEIGHT overrides).

    MEASURED (benchmark/paraphrases.yaml, 109 reworded rules, tools not given): fusing BM25 with the embedding rank
    made retrieval worse for BOTH embedders, and more so the more weight it got (Gemini recall@1 99.1% at 0, 93.6% at
    0.5, 83.5% at 1.0; offline 85.3% at 0, 80.7% at 1.0). Reworded rules share few words with their example, so the
    keyword ranking mostly adds noise. The default is therefore 0: the embedding decides, keywords are only reported."""
    try:
        return float(os.environ["RETRIEVAL_LEX_WEIGHT"])
    except (KeyError, ValueError):
        return 0.0


class _Lexical:
    """Okapi BM25 over the examples' words (k1=1.5, b=0.75)."""

    def __init__(self, docs: list[list[str]]) -> None:
        self.tf = [Counter(d) for d in docs]
        self.len = np.array([len(d) for d in docs], dtype=np.float32)
        self.avg = float(self.len.mean()) if len(docs) else 1.0
        n = len(docs)
        df = Counter(t for d in docs for t in set(d))
        self.idf = {t: math.log(1 + (n - c + 0.5) / (c + 0.5)) for t, c in df.items()}

    def scores(self, query: list[str]) -> np.ndarray:
        out = np.zeros(len(self.tf), dtype=np.float32)
        for t in set(query):
            idf = self.idf.get(t)
            if idf is None:
                continue
            for i, tf in enumerate(self.tf):
                f = tf.get(t, 0)
                if f:
                    out[i] += idf * f * 2.5 / (f + 1.5 * (0.25 + 0.75 * self.len[i] / max(self.avg, 1e-9)))
        peak = float(out.max()) if out.size else 0.0
        return out / peak if peak > 0 else out


class Retriever:
    def __init__(self, provider: LLMProvider, examples: list[PolicyExample] | None = None,
                 index_path: Path | None = None, *, hybrid: bool = True, lex_weight: float | None = None) -> None:
        self.provider = provider
        self.hybrid = hybrid                                # False = dense only (used to measure the embedding alone)
        self.lex_weight = lex_weight if lex_weight is not None else default_lex_weight(provider)
        self.examples = examples if examples is not None else load_examples()
        self.index_path = index_path if index_path is not None else index_path_for(provider)
        self._matrix: np.ndarray | None = None
        self._lex = _Lexical([lex_tokens(example_text(e)) for e in self.examples])
        self._tool_names = [{t.split("(")[0] for t in e.tools_context} for e in self.examples]

    # -- calibration ------------------------------------------------------
    def floor_info(self) -> dict:
        floor, calibrated = floor_for(self.provider)
        return {"floor": floor, "calibrated": calibrated, "provider": self.provider.name,
                "embed_model": self.provider.embed_model}

    # -- index ----------------------------------------------------------
    def build_index(self) -> int:
        vecs = np.array(embed_texts(self.provider, [example_text(e) for e in self.examples], task="document"), dtype=np.float32)
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
        q = np.array(embed_texts(self.provider, [query_text(english, tools)], task="query")[0], dtype=np.float32)
        q = q / max(float(np.linalg.norm(q)), 1e-9)
        dense = matrix @ q
        lexical = self._lex.scores(lex_tokens(query_text(english, tools)))

        n = len(self.examples)
        dense_rank = np.empty(n, dtype=np.int64)
        dense_rank[np.argsort(-dense, kind="stable")] = np.arange(n)
        lex_rank = np.empty(n, dtype=np.int64)
        lex_rank[np.argsort(-lexical, kind="stable")] = np.arange(n)
        fused = 1.0 / (RRF_K + dense_rank + 1)
        if self.hybrid:
            fused = fused + self.lex_weight * np.where(lexical > 0, 1.0 / (RRF_K + lex_rank + 1), 0.0)
        wanted = {t for t in (tools or []) if t}
        if self.hybrid and wanted:
            fused = fused + TOOL_BOOST * np.array([len(wanted & names) / len(wanted) for names in self._tool_names])

        floor, _ = floor_for(self.provider)
        order = np.argsort(-fused, kind="stable")[: max(0, k)]
        return [Retrieved(id=self.examples[i].id, english=self.examples[i].english,
                          tools_context=self.examples[i].tools_context, gold_yog=self.examples[i].gold_yog,
                          score=round(float(dense[i]), 4), source=self.examples[i].source,
                          lexical=round(float(lexical[i]), 4), fused=round(float(fused[i]), 5),
                          relevant=bool(dense[i] >= floor)) for i in order]


if __name__ == "__main__":                                   # python -m app.rag.retriever  -> rebuild index
    from app.llm.factory import get_provider
    r = Retriever(get_provider())
    print(f"indexed {r.build_index()} examples -> {r.index_path}")
