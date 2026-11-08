"""Claude via the official Anthropic SDK (generation only: Claude has no embeddings endpoint).

Follows the claude-api guidance for the current models:
  * default model `claude-opus-5-5` (CLAUDE_MODEL overrides it, e.g. `claude-sonnet-5-5` to spend less);
  * thinking is always on for Opus 5.5 and `temperature` is not accepted, so neither is sent. Depth is set with
    `output_config.effort` (CLAUDE_EFFORT, default `medium`);
  * structured output through `output_config.format` (JSON Schema), validated by the caller as well;
  * the SDK does the retrying (rate limits, 5xx, connection errors); we map every failure to LLMError;
  * a `refusal` stop reason and a truncated reply are errors, never silently returned.

Optional refusal fallback (CLAUDE_FALLBACK_MODEL): uses the documented server-side fallback beta. It is off by default
because it cannot be exercised without a live key here; the smoke script (scripts/llm_smoke.py) checks it.
"""
from typing import Any

import anthropic

from app.llm.provider import LLMError, LLMProvider

FALLBACK_BETA = "server-side-fallback-2026-06-01"


class ClaudeProvider(LLMProvider):
    name = "claude"
    supports_json_schema = True

    def __init__(self, api_key: str | None = None, model: str = "claude-opus-5-5", *, effort: str = "medium",
                 max_tokens: int = 16000, timeout: float = 120.0, max_retries: int = 4,
                 fallback_model: str | None = None, client: Any = None) -> None:
        self.model = model
        self.effort, self.max_tokens, self.fallback_model = effort, max_tokens, fallback_model
        if client is not None:                                   # tests inject a duck-typed client
            self._client = client
            return
        if not api_key:
            raise LLMError("ANTHROPIC_API_KEY is not set")
        self._client = anthropic.Anthropic(api_key=api_key, timeout=timeout, max_retries=max_retries)

    def generate(self, prompt: str, system: str | None = None, *, json_schema: dict | None = None) -> str:
        output_config: dict = {"effort": self.effort}
        if json_schema is not None:
            output_config["format"] = {"type": "json_schema", "schema": json_schema}
        kwargs: dict = {"model": self.model, "max_tokens": self.max_tokens,
                        "messages": [{"role": "user", "content": prompt}], "output_config": output_config}
        if system:
            kwargs["system"] = system
        try:
            if self.fallback_model:
                resp = self._client.beta.messages.create(betas=[FALLBACK_BETA],
                                                         fallbacks=[{"model": self.fallback_model}], **kwargs)
            else:
                resp = self._client.messages.create(**kwargs)
        except anthropic.AuthenticationError as e:
            raise LLMError("Claude rejected the API key (check ANTHROPIC_API_KEY)") from e
        except anthropic.PermissionDeniedError as e:
            raise LLMError("Claude API key lacks permission for this model") from e
        except anthropic.NotFoundError as e:
            raise LLMError(f"Claude model not found: {self.model!r} (set CLAUDE_MODEL)") from e
        except anthropic.RateLimitError as e:
            raise LLMError("Claude rate limit exceeded even after retrying; slow down or retry later") from e
        except anthropic.BadRequestError as e:
            raise LLMError(f"Claude rejected the request: {getattr(e, 'message', str(e))[:300]}") from e
        except anthropic.APITimeoutError as e:
            raise LLMError("Claude request timed out") from e
        except anthropic.APIConnectionError as e:
            raise LLMError("could not reach the Claude API (network)") from e
        except anthropic.APIStatusError as e:
            raise LLMError(f"Claude API error (HTTP {e.status_code})") from e
        return self._text(resp)

    def _text(self, resp: Any) -> str:
        usage = getattr(resp, "usage", None)
        if usage is not None:
            self.usage.add(calls=1, prompt_tokens=int(getattr(usage, "input_tokens", 0) or 0),
                           output_tokens=int(getattr(usage, "output_tokens", 0) or 0))
        stop = getattr(resp, "stop_reason", None)
        if stop == "refusal":
            details = getattr(resp, "stop_details", None)
            category = getattr(details, "category", None) if details else None
            raise LLMError(f"Claude declined this request{f' ({category})' if category else ''}")
        if stop == "max_tokens":
            raise LLMError("Claude's reply was cut off at max_tokens; raise CLAUDE_MAX_TOKENS")
        text = "".join(b.text for b in (resp.content or []) if getattr(b, "type", None) == "text")
        if not text.strip():
            raise LLMError("Claude returned no text")
        return text

    def embed(self, texts: list[str]) -> list[list[float]]:
        raise LLMError("Claude has no embeddings endpoint: set EMBED_PROVIDER=gemini for retrieval")
