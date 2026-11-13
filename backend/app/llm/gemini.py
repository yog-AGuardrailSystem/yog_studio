"""Gemini via plain REST (no SDK). The key comes from the environment, is sent as a header and is never logged.

Hardened for real use: retries with backoff + jitter (honouring Retry-After / retryDelay), a client-side rate limiter,
usage accounting, clear errors for blocked/truncated replies, JSON output with a schema, and retrieval-style embeddings.

Model notes (checked against the Gemini docs in November 2026; ids change, so every one is an env setting):
  * generation   GEMINI_MODEL        default gemini-3.6-flash (stable). gemini-3.5-flash-lite is the cheap option.
                                     gemini-2.0-flash and 2.5-flash are retired/deprecated: do not use them.
  * embeddings   GEMINI_EMBED_MODEL  default gemini-embedding-2. It has no task_type field: the task is written into the
                                     text ("task: search result | query: ..." / "title: none | text: ..."). The older
                                     gemini-embedding-001 takes a taskType field instead; both are supported here.
Structured output: the docs we could read describe the newer Interactions API, not generateContent, so the exact
generateContent field is unconfirmed. We send responseMimeType + responseJsonSchema, and if the API rejects it (HTTP 400)
we fall back to JSON-by-prompt for the rest of the process. Either way the caller validates the JSON itself.
"""
import json
import time
from collections.abc import Callable

import httpx

from app.llm.provider import LLMError, LLMProvider
from app.llm.retry import RETRYABLE_STATUS, RateLimiter, backoff_delay, retry_after_seconds

BASE = "https://generativelanguage.googleapis.com/v1beta"
EMBED_BATCH = 100


class GeminiHTTPError(LLMError):
    def __init__(self, status: int, message: str) -> None:
        super().__init__(message)
        self.status = status


def _friendly(status: int, body: str, model: str) -> str:
    """Fixed wording only. The upstream body is never relayed: it can echo request text, key fragments or project ids."""
    if status == 429:
        return ("Gemini rate limit or quota exceeded even after retrying (free-tier requests-per-minute or daily "
                "quota). Lower GEMINI_RPM or wait.")
    if status in (401, 403):
        return f"Gemini rejected the API key or the request is not permitted (HTTP {status})."
    if status == 404:
        return f"Gemini model not found: {model!r}. Model ids are retired over time; set GEMINI_MODEL / GEMINI_EMBED_MODEL."
    return f"Gemini returned HTTP {status}."


class GeminiProvider(LLMProvider):
    name = "gemini"
    supports_json_schema = True
    supports_embed_task = True

    def __init__(self, api_key: str, model: str, embed_model: str, *, timeout: float = 60.0, max_retries: int = 4,
                 rpm: float = 10.0, temperature: float = 0.0, max_output_tokens: int = 8192, embed_dims: int = 768,
                 base_url: str = BASE, transport: httpx.BaseTransport | None = None,
                 sleep: Callable[[float], None] = time.sleep, clock: Callable[[], float] = time.monotonic) -> None:
        if not api_key:
            raise LLMError("GEMINI_API_KEY is not set")
        self.model, self.embed_model = model, embed_model
        self.max_retries, self.temperature = max_retries, temperature
        self.max_output_tokens, self.embed_dims = max_output_tokens, embed_dims
        self._sleep = sleep
        self._limiter = RateLimiter(rpm, clock=clock, sleep=sleep)
        self._schema_mode = "native"                       # becomes "prompt" if the API rejects the schema field
        self._client = httpx.Client(base_url=base_url, headers={"x-goog-api-key": api_key}, timeout=timeout,
                                    transport=transport)

    # ------------------------------------------------------------------ transport with retries
    def _post(self, path: str, body: dict, model: str) -> dict:
        last = "no attempt was made"
        for attempt in range(1, self.max_retries + 2):
            self.usage.add(waited_seconds=self._limiter.wait())
            hint = None
            try:
                r = self._client.post(path, json=body)
            except httpx.TimeoutException:
                last = "the request timed out"
            except httpx.HTTPError as e:
                last = f"network error ({type(e).__name__})"
            else:
                if r.status_code == 200:
                    return r.json()
                if r.status_code not in RETRYABLE_STATUS:
                    raise GeminiHTTPError(r.status_code, _friendly(r.status_code, r.text, model))
                hint = retry_after_seconds(dict(r.headers), r.text)
                last = _friendly(r.status_code, r.text, model)
                if attempt > self.max_retries:
                    raise GeminiHTTPError(r.status_code, last)
            if attempt > self.max_retries:
                raise LLMError(f"Gemini request failed after {attempt} attempts: {last}")
            delay = backoff_delay(attempt, hint)
            self.usage.add(retries=1, waited_seconds=delay)
            self._sleep(delay)
        raise LLMError(f"Gemini request failed: {last}")             # pragma: no cover

    # ------------------------------------------------------------------ generation
    def generate(self, prompt: str, system: str | None = None, *, json_schema: dict | None = None) -> str:
        cfg: dict = {"temperature": self.temperature, "maxOutputTokens": self.max_output_tokens}
        text = prompt
        if json_schema is not None:
            cfg["responseMimeType"] = "application/json"
            if self._schema_mode == "native":
                cfg["responseJsonSchema"] = json_schema
            else:
                text = f"{prompt}\n\nReply with JSON only, matching this JSON Schema:\n{json.dumps(json_schema)}"
        body: dict = {"contents": [{"role": "user", "parts": [{"text": text}]}], "generationConfig": cfg}
        if system:
            body["systemInstruction"] = {"parts": [{"text": system}]}
        path = f"/models/{self.model}:generateContent"
        try:
            data = self._post(path, body, self.model)
        except GeminiHTTPError as e:
            if json_schema is not None and self._schema_mode == "native" and e.status == 400:
                self._schema_mode = "prompt"                 # the schema field is not accepted here: remember, retry once
                return self.generate(prompt, system, json_schema=json_schema)
            raise
        self.usage.add(calls=1)
        return self._text(data)

    def _text(self, data: dict) -> str:
        usage = data.get("usageMetadata") or {}
        self.usage.add(prompt_tokens=int(usage.get("promptTokenCount") or 0),
                       output_tokens=int(usage.get("candidatesTokenCount") or 0) + int(usage.get("thoughtsTokenCount") or 0))
        block = (data.get("promptFeedback") or {}).get("blockReason")
        if block:
            raise LLMError(f"Gemini blocked the prompt ({block})")
        try:
            cand = data["candidates"][0]
        except (KeyError, IndexError, TypeError) as e:
            raise LLMError("Gemini returned no candidates") from e
        reason = cand.get("finishReason")
        parts = (cand.get("content") or {}).get("parts") or []
        text = "".join(p.get("text", "") for p in parts if isinstance(p, dict))
        if reason == "MAX_TOKENS":
            raise LLMError("Gemini's reply was cut off at the output token limit; raise GEMINI_MAX_OUTPUT_TOKENS")
        if not text.strip():
            raise LLMError(f"Gemini returned no text ({reason or 'blocked or empty'})")
        return text

    # ------------------------------------------------------------------ embeddings
    def _embed_input(self, text: str, task: str | None) -> tuple[str, str | None]:
        """(text to send, taskType field or None). gemini-embedding-2 takes the task inside the text."""
        if "embedding-001" in self.embed_model or "text-embedding" in self.embed_model:
            return text, {"document": "RETRIEVAL_DOCUMENT", "query": "RETRIEVAL_QUERY"}.get(task or "")
        if task == "query":
            return f"task: search result | query: {text}", None
        if task == "document":
            return f"title: none | text: {text}", None
        return text, None

    def embed(self, texts: list[str], task: str | None = None) -> list[list[float]]:
        out: list[list[float]] = []
        for i in range(0, len(texts), EMBED_BATCH):
            requests = []
            for t in texts[i:i + EMBED_BATCH]:
                content, task_type = self._embed_input(t, task)
                req: dict = {"model": f"models/{self.embed_model}", "content": {"parts": [{"text": content}]}}
                if task_type:
                    req["taskType"] = task_type
                if self.embed_dims:
                    req["outputDimensionality"] = self.embed_dims
                requests.append(req)
            data = self._post(f"/models/{self.embed_model}:batchEmbedContents", {"requests": requests}, self.embed_model)
            try:
                vectors = [e["values"] for e in data["embeddings"]]
            except (KeyError, TypeError) as e:
                raise LLMError("Gemini embedding response malformed") from e
            if len(vectors) != len(requests):
                raise LLMError(f"Gemini returned {len(vectors)} embeddings for {len(requests)} texts")
            out += vectors
            self.usage.add(embed_calls=1)
        return out
