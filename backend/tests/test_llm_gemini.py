"""GeminiProvider against a mocked HTTP transport: request shapes, retries, errors, embeddings. No network, no key."""
import json

import httpx
import pytest

from app.llm.gemini import GeminiProvider
from app.llm.provider import LLMError
from app.llm.retry import RateLimiter, backoff_delay, retry_after_seconds

KEY = "AIza-secret-test-key-123"


def reply(text="ok", **extra):
    return {"candidates": [{"content": {"parts": [{"text": text}]}, "finishReason": "STOP"}],
            "usageMetadata": {"promptTokenCount": 11, "candidatesTokenCount": 5, "thoughtsTokenCount": 3}, **extra}


def make(handler, **kw):
    sleeps: list[float] = []
    kw.setdefault("rpm", 0)
    p = GeminiProvider(KEY, kw.pop("model", "gemini-3.6-flash"), kw.pop("embed_model", "gemini-embedding-2"),
                       transport=httpx.MockTransport(handler), sleep=sleeps.append, **kw)
    return p, sleeps


def ok(text="ok"):
    return lambda req: httpx.Response(200, json=reply(text))


# ------------------------------------------------------------------ generate: request shape + response handling
def test_generate_request_shape_and_usage():
    seen = {}

    def h(req):
        seen["url"], seen["key"], seen["body"] = str(req.url), req.headers.get("x-goog-api-key"), json.loads(req.content)
        return httpx.Response(200, json=reply("hello"))
    p, _ = make(h, temperature=0.0, max_output_tokens=777)
    assert p.generate("say hi", system="be brief") == "hello"
    assert seen["url"].endswith("/models/gemini-3.6-flash:generateContent") and seen["key"] == KEY
    b = seen["body"]
    assert b["contents"][0]["parts"][0]["text"] == "say hi" and b["systemInstruction"]["parts"][0]["text"] == "be brief"
    assert b["generationConfig"] == {"temperature": 0.0, "maxOutputTokens": 777}
    u = p.usage.snapshot()
    assert (u["calls"], u["prompt_tokens"], u["output_tokens"]) == (1, 11, 8)       # output counts thinking tokens too


def test_generate_with_json_schema_sets_mime_type_and_schema():
    seen = {}
    p, _ = make(lambda r: (seen.update(b=json.loads(r.content)), httpx.Response(200, json=reply("[]")))[1])
    schema = {"type": "array", "items": {"type": "object"}}
    assert p.generate("x", json_schema=schema) == "[]"
    cfg = seen["b"]["generationConfig"]
    assert cfg["responseMimeType"] == "application/json" and cfg["responseJsonSchema"] == schema


def test_schema_rejected_falls_back_to_json_by_prompt_and_remembers():
    bodies = []

    def h(req):
        b = json.loads(req.content)
        bodies.append(b)
        if "responseJsonSchema" in b["generationConfig"]:
            return httpx.Response(400, json={"error": {"message": "Unknown name responseJsonSchema"}})
        return httpx.Response(200, json=reply("[]"))
    p, _ = make(h)
    schema = {"type": "array"}
    assert p.generate("x", json_schema=schema) == "[]"
    assert "responseJsonSchema" in bodies[0]["generationConfig"] and "responseJsonSchema" not in bodies[1]["generationConfig"]
    assert bodies[1]["generationConfig"]["responseMimeType"] == "application/json"
    assert "JSON Schema" in bodies[1]["contents"][0]["parts"][0]["text"], "the schema is described in the prompt instead"
    p.generate("y", json_schema=schema)
    assert len(bodies) == 3 and "responseJsonSchema" not in bodies[2]["generationConfig"], "no second failing probe"


@pytest.mark.parametrize("payload, needle", [
    ({"promptFeedback": {"blockReason": "SAFETY"}}, "blocked the prompt"),
    ({"candidates": []}, "no candidates"),
    ({"candidates": [{"content": {"parts": [{"text": "cut"}]}, "finishReason": "MAX_TOKENS"}]}, "output token limit"),
    ({"candidates": [{"content": {"parts": []}, "finishReason": "SAFETY"}]}, "no text"),
])
def test_unusable_replies_are_errors_not_empty_strings(payload, needle):
    p, _ = make(lambda r: httpx.Response(200, json=payload))
    with pytest.raises(LLMError, match=needle):
        p.generate("x")


# ------------------------------------------------------------------ retries and errors
def test_429_retries_honouring_retry_after_then_succeeds():
    calls = []

    def h(req):
        calls.append(1)
        return httpx.Response(429, headers={"Retry-After": "7"}, text="slow down") if len(calls) == 1 \
            else httpx.Response(200, json=reply("fine"))
    p, sleeps = make(h)
    assert p.generate("x") == "fine"
    assert len(calls) == 2 and len(sleeps) == 1 and sleeps[0] >= 7
    assert p.usage.snapshot()["retries"] == 1


def test_429_with_google_retry_delay_in_the_body_is_honoured():
    calls = []

    def h(req):
        calls.append(1)
        body = {"error": {"details": [{"retryDelay": "12s"}]}}
        return httpx.Response(429, text=json.dumps(body)) if len(calls) == 1 else httpx.Response(200, json=reply())
    p, sleeps = make(h)
    p.generate("x")
    assert sleeps[0] >= 12


def test_retries_are_bounded_and_the_error_is_actionable():
    calls = []
    p, sleeps = make(lambda r: (calls.append(1), httpx.Response(429, text="quota"))[1], max_retries=2)
    with pytest.raises(LLMError, match="rate limit or quota"):
        p.generate("x")
    assert len(calls) == 3 and len(sleeps) == 2


@pytest.mark.parametrize("status", [500, 502, 503, 504])
def test_transient_server_errors_are_retried(status):
    calls = []
    p, _ = make(lambda r: (calls.append(1), httpx.Response(status if len(calls) < 3 else 200, json=reply()))[1])
    assert p.generate("x") == "ok" and len(calls) == 3


def test_timeouts_and_network_errors_are_retried():
    calls = []

    def h(req):
        calls.append(1)
        if len(calls) == 1:
            raise httpx.ReadTimeout("slow", request=req)
        if len(calls) == 2:
            raise httpx.ConnectError("down", request=req)
        return httpx.Response(200, json=reply("back"))
    p, sleeps = make(h)
    assert p.generate("x") == "back" and len(sleeps) == 2


def test_persistent_network_failure_gives_up_with_a_clear_error():
    def h(req):
        raise httpx.ConnectError("down", request=req)
    p, _ = make(h, max_retries=1)
    with pytest.raises(LLMError, match="after 2 attempts"):
        p.generate("x")


@pytest.mark.parametrize("status, needle", [(401, "API key"), (403, "API key"), (404, "GEMINI_MODEL"), (400, "HTTP 400")])
def test_client_errors_are_not_retried_and_are_explained(status, needle):
    calls = []
    p, sleeps = make(lambda r: (calls.append(1), httpx.Response(status, text="nope"))[1])
    with pytest.raises(LLMError, match=needle):
        p.generate("x")
    assert len(calls) == 1 and sleeps == []


def test_the_api_key_never_appears_in_an_error():
    for status in (400, 401, 404, 429, 500):
        p, _ = make(lambda r, s=status: httpx.Response(s, text="bad"), max_retries=0)
        with pytest.raises(LLMError) as e:
            p.generate("x")
        assert KEY not in str(e.value)


def test_a_missing_key_is_refused():
    with pytest.raises(LLMError, match="GEMINI_API_KEY"):
        GeminiProvider("", "m", "e")


# ------------------------------------------------------------------ embeddings
def embed_handler(sizes=None):
    def h(req):
        b = json.loads(req.content)
        if sizes is not None:
            sizes.append(len(b["requests"]))
        return httpx.Response(200, json={"embeddings": [{"values": [0.1, 0.2]} for _ in b["requests"]]})
    return h


def test_embeddings_are_batched_in_hundreds():
    sizes = []
    p, _ = make(embed_handler(sizes))
    out = p.embed([f"t{i}" for i in range(150)])
    assert sizes == [100, 50] and len(out) == 150 and p.usage.snapshot()["embed_calls"] == 2


def test_embedding_2_puts_the_task_in_the_text_and_sends_the_dimension():
    seen = {}
    p, _ = make(lambda r: (seen.update(b=json.loads(r.content)), embed_handler()(r))[1], embed_dims=768)
    p.embed(["delete db"], task="query")
    p.embed(["delete db"], task="document")
    p.embed(["delete db"])
    req = seen["b"]["requests"][0]
    assert "taskType" not in req and req["outputDimensionality"] == 768 and req["model"] == "models/gemini-embedding-2"
    texts = []
    p2, _ = make(lambda r: (texts.append(json.loads(r.content)["requests"][0]["content"]["parts"][0]["text"]), embed_handler()(r))[1])
    p2.embed(["delete db"], task="query"), p2.embed(["delete db"], task="document"), p2.embed(["delete db"])
    assert texts == ["task: search result | query: delete db", "title: none | text: delete db", "delete db"]


def test_embedding_001_uses_the_task_type_field_not_text_prefixes():
    seen = []
    p, _ = make(lambda r: (seen.append(json.loads(r.content)["requests"][0]), embed_handler()(r))[1],
                embed_model="gemini-embedding-001")
    p.embed(["x"], task="query"), p.embed(["x"], task="document")
    assert [s["taskType"] for s in seen] == ["RETRIEVAL_QUERY", "RETRIEVAL_DOCUMENT"]
    assert seen[0]["content"]["parts"][0]["text"] == "x"


def test_embedding_count_mismatch_and_malformed_bodies_are_errors():
    p, _ = make(lambda r: httpx.Response(200, json={"embeddings": [{"values": [1]}]}))
    with pytest.raises(LLMError, match="1 embeddings for 2 texts"):
        p.embed(["a", "b"])
    p2, _ = make(lambda r: httpx.Response(200, json={"nope": 1}))
    with pytest.raises(LLMError, match="malformed"):
        p2.embed(["a"])


def test_the_provider_advertises_its_capabilities():
    p, _ = make(ok())
    assert p.supports_json_schema and p.supports_embed_task and p.name == "gemini"


# ------------------------------------------------------------------ retry helpers
def test_rate_limiter_spaces_calls_and_can_be_disabled():
    now, slept = [0.0], []
    rl = RateLimiter(60, clock=lambda: now[0], sleep=slept.append)           # one call per second
    assert rl.wait() == 0.0                                                    # first call is free
    assert rl.wait() == pytest.approx(1.0) and slept == [pytest.approx(1.0)]   # second must wait a second
    now[0] = 10.0
    assert rl.wait() == 0.0                                                    # long idle: no wait
    assert RateLimiter(0).wait() == 0.0


def test_retry_after_parsing():
    assert retry_after_seconds({"Retry-After": "3"}) == 3.0
    assert retry_after_seconds({"retry-after": "x"}, '{"retryDelay": "2.5s"}') == 2.5
    assert retry_after_seconds({}, "no hint") is None


def test_backoff_grows_honours_the_hint_and_is_capped():
    flat = lambda: 0.0  # noqa: E731
    assert [backoff_delay(i, rng=flat) for i in (1, 2, 3)] == [1.0, 2.0, 4.0]
    assert backoff_delay(1, server_hint=9, rng=flat) == 9.0
    assert backoff_delay(20, rng=flat) == 60.0
