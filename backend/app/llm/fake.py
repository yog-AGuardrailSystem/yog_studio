"""Offline, deterministic provider. Used for tests and for running the demo with no API key.

embed():    hashed bag-of-words (stemmed, stop-words removed) -> L2-normalised vector. Real similarity, no network.
generate(): scripted replies if given (tests); otherwise echoes the first ```yog block found in the prompt,
            i.e. the nearest retrieved example, labelled as such. That is NOT a translation -- it only lets the
            UI flow (retrieve -> validate -> review -> approve) be exercised without an LLM.
"""
import math
import re
import zlib
from collections.abc import Callable, Sequence

from app.llm.provider import LLMProvider

DIM = 512
STOP = {"a", "an", "the", "to", "of", "and", "or", "is", "are", "be", "may", "can", "must", "should", "that",
        "it", "in", "on", "for", "with", "by", "at", "as", "any", "only", "not", "than", "their", "its", "this",
        "until", "has", "have", "from", "all", "who", "which", "will", "when", "while", "if", "so", "do", "does"}
# Canonical forms (applied after stemming + trailing-e strip) so close paraphrases share tokens.
SYNONYMS = {"remov": "delet", "eras": "delet", "drop": "delet", "wip": "delet", "destroy": "delet",
            "prod": "production", "mail": "email", "evening": "night", "overnight": "night",
            "outsid": "extern", "extern": "extern", "intern": "internal", "company": "internal",
            "human": "approv", "approval": "approv", "approved": "approv",
            "open": "unlock", "unlock": "unlock"}


def _stem(w: str) -> str:
    for suf in ("ing", "ed", "es", "s"):
        if w.endswith(suf) and len(w) - len(suf) >= 3:
            w = w[: -len(suf)]
            break
    if w.endswith("e") and len(w) > 3:
        w = w[:-1]
    return w


def tokens(text: str) -> list[str]:
    words = re.findall(r"[a-z0-9]+", text.lower().replace("_", " "))
    out = [SYNONYMS.get(_stem(w), _stem(w)) for w in words if w not in STOP]
    return out + [f"{a}_{b}" for a, b in zip(out, out[1:])]          # bigrams add a little word-order signal


def hash_embed(text: str) -> list[float]:
    vec = [0.0] * DIM
    for t in tokens(text):
        vec[zlib.crc32(t.encode()) % DIM] += 1.0
    norm = math.sqrt(sum(x * x for x in vec)) or 1.0
    return [x / norm for x in vec]


class FakeProvider(LLMProvider):
    name = "fake"

    def __init__(self, replies: Sequence[str] | Callable[[str], str] | None = None) -> None:
        self._replies = list(replies) if isinstance(replies, Sequence) else None
        self._fn = replies if callable(replies) else None
        self.prompts: list[str] = []            # every prompt received, for assertions in tests

    def embed(self, texts: list[str]) -> list[list[float]]:
        return [hash_embed(t) for t in texts]

    def generate(self, prompt: str, system: str | None = None) -> str:
        self.prompts.append(prompt)
        if self._fn is not None:
            return self._fn(prompt)
        if self._replies is not None:
            if not self._replies:
                raise AssertionError("FakeProvider ran out of scripted replies")
            return self._replies.pop(0)
        m = re.search(r"```yog\n(.*?)```", prompt, re.S)
        body = m.group(1) if m else ""
        return "```yog\n# OFFLINE FAKE PROVIDER: copied from the nearest example, not translated.\n" + body + "```"
