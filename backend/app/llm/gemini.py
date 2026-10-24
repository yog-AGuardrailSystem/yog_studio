"""Gemini via plain REST (no SDK). Key comes from the environment, is sent as a header, never logged."""
import httpx

from app.llm.provider import LLMError, LLMProvider

BASE = "https://generativelanguage.googleapis.com/v1beta"


class GeminiProvider(LLMProvider):
    name = "gemini"

    def __init__(self, api_key: str, model: str, embed_model: str, timeout: float = 60.0) -> None:
        if not api_key:
            raise LLMError("GEMINI_API_KEY is not set")
        self.model, self.embed_model = model, embed_model
        self._client = httpx.Client(base_url=BASE, headers={"x-goog-api-key": api_key}, timeout=timeout)

    def _post(self, path: str, body: dict) -> dict:
        try:
            r = self._client.post(path, json=body)
        except httpx.HTTPError as e:
            raise LLMError(f"Gemini request failed: {type(e).__name__}") from e
        if r.status_code != 200:
            raise LLMError(f"Gemini returned HTTP {r.status_code}: {r.text[:200]}")
        return r.json()

    def generate(self, prompt: str, system: str | None = None) -> str:
        body: dict = {"contents": [{"role": "user", "parts": [{"text": prompt}]}],
                      "generationConfig": {"temperature": 0.1}}
        if system:
            body["systemInstruction"] = {"parts": [{"text": system}]}
        data = self._post(f"/models/{self.model}:generateContent", body)
        try:
            return "".join(p["text"] for p in data["candidates"][0]["content"]["parts"])
        except (KeyError, IndexError, TypeError) as e:
            raise LLMError("Gemini response had no text (blocked or empty)") from e

    def embed(self, texts: list[str]) -> list[list[float]]:
        out: list[list[float]] = []
        for i in range(0, len(texts), 100):                 # API batch limit
            chunk = texts[i:i + 100]
            body = {"requests": [{"model": f"models/{self.embed_model}", "content": {"parts": [{"text": t}]}}
                                 for t in chunk]}
            data = self._post(f"/models/{self.embed_model}:batchEmbedContents", body)
            try:
                out += [e["values"] for e in data["embeddings"]]
            except (KeyError, TypeError) as e:
                raise LLMError("Gemini embedding response malformed") from e
        return out
