"""ClaudeProvider (stand-in SDK client), the on-disk cache, the composite provider and the provider factory."""
from types import SimpleNamespace as NS

import anthropic
import httpx2
import pytest

from app.llm.cache import CachingProvider, KVCache
from app.llm.claude import FALLBACK_BETA, ClaudeProvider
from app.llm.composite import CompositeProvider
from app.llm.fake import FakeProvider
from app.llm.factory import get_provider
from app.llm.provider import LLMError, LLMProvider, embed_texts, generate_text


# ------------------------------------------------------------------ Claude, with a stand-in for the SDK client
def msg(text="done", stop="end_turn", blocks=None, **kw):
    content = blocks if blocks is not None else [NS(type="text", text=text)]
    return NS(content=content, stop_reason=stop, usage=NS(input_tokens=20, output_tokens=7), **kw)


class FakeAnthropic:
    def __init__(self, response=None, error=None):
        self.calls, self.response, self.error = [], response or msg(), error
        self.messages = NS(create=self._create)
        self.beta = NS(messages=NS(create=self._beta_create))

    def _create(self, **kw):
        self.calls.append(("messages", kw))
        if self.error:
            raise self.error
        return self.response

    def _beta_create(self, **kw):
        self.calls.append(("beta", kw))
        return self.response


def claude(client, **kw):
    return ClaudeProvider(model=kw.pop("model", "claude-opus-5-5"), client=client, **kw)


def test_claude_request_shape_follows_the_current_api_rules():
    c = FakeAnthropic()
    out = claude(c).generate("translate this", system="you are precise")
    assert out == "done"
    kind, kw = c.calls[0]
    assert kind == "messages" and kw["model"] == "claude-opus-5-5"
    assert kw["messages"] == [{"role": "user", "content": "translate this"}] and kw["system"] == "you are precise"
    assert kw["output_config"] == {"effort": "medium"} and kw["max_tokens"] == 16000
    for removed in ("temperature", "top_p", "top_k", "thinking"):
        assert removed not in kw, f"{removed} is rejected or unnecessary on Claude Opus 5.5"


def test_claude_json_schema_uses_output_config_format():
    c = FakeAnthropic()
    schema = {"type": "object", "properties": {"a": {"type": "string"}}, "required": ["a"]}
    claude(c).generate("x", json_schema=schema)
    assert c.calls[0][1]["output_config"] == {"effort": "medium", "format": {"type": "json_schema", "schema": schema}}


def test_claude_ignores_thinking_blocks_and_joins_text_blocks():
    blocks = [NS(type="thinking", thinking="hmm"), NS(type="text", text="a"), NS(type="text", text="b")]
    assert claude(FakeAnthropic(msg(blocks=blocks))).generate("x") == "ab"


def test_claude_usage_is_recorded():
    p = claude(FakeAnthropic())
    p.generate("x")
    u = p.usage.snapshot()
    assert (u["calls"], u["prompt_tokens"], u["output_tokens"]) == (1, 20, 7)


@pytest.mark.parametrize("resp, needle", [
    (msg(stop="refusal", stop_details=NS(category="cyber")), "declined this request \\(cyber\\)"),
    (msg(stop="refusal"), "declined this request"),
    (msg(stop="max_tokens"), "cut off"),
    (msg(blocks=[]), "no text"),
])
def test_claude_refusals_truncation_and_empty_replies_are_errors(resp, needle):
    with pytest.raises(LLMError, match=needle):
        claude(FakeAnthropic(resp)).generate("x")


def _status(cls, code):
    req = httpx2.Request("POST", "https://api.anthropic.com/v1/messages")
    return cls("boom", response=httpx2.Response(code, request=req), body=None)


@pytest.mark.parametrize("make_err, needle", [
    (lambda: _status(anthropic.AuthenticationError, 401), "API key"),
    (lambda: _status(anthropic.PermissionDeniedError, 403), "permission"),
    (lambda: _status(anthropic.NotFoundError, 404), "CLAUDE_MODEL"),
    (lambda: _status(anthropic.RateLimitError, 429), "rate limit"),
    (lambda: _status(anthropic.BadRequestError, 400), "rejected the request"),
    (lambda: _status(anthropic.InternalServerError, 500), "HTTP 500"),
    (lambda: anthropic.APITimeoutError(request=httpx2.Request("POST", "https://x")), "timed out"),
    (lambda: anthropic.APIConnectionError(request=httpx2.Request("POST", "https://x")), "network"),
])
def test_every_sdk_failure_becomes_an_llm_error(make_err, needle):
    with pytest.raises(LLMError, match=needle):
        claude(FakeAnthropic(error=make_err())).generate("x")


def test_claude_fallback_is_opt_in_and_uses_the_documented_beta():
    plain, with_fb = FakeAnthropic(), FakeAnthropic()
    claude(plain).generate("x")
    claude(with_fb, fallback_model="claude-opus-4-8").generate("x")
    assert plain.calls[0][0] == "messages"
    kind, kw = with_fb.calls[0]
    assert kind == "beta" and kw["betas"] == [FALLBACK_BETA] and kw["fallbacks"] == [{"model": "claude-opus-4-8"}]


def test_claude_has_no_embeddings_and_needs_a_key():
    with pytest.raises(LLMError, match="no embeddings"):
        claude(FakeAnthropic()).embed(["x"])
    with pytest.raises(LLMError, match="ANTHROPIC_API_KEY"):
        ClaudeProvider("")
    assert ClaudeProvider("sk-ant-test").model == "claude-opus-5-5"          # builds the real SDK client offline


# ------------------------------------------------------------------ cache
class Counting(LLMProvider):
    name, model, embed_model = "count", "m1", "e1"
    supports_json_schema = supports_embed_task = True

    def __init__(self):
        self.gen, self.emb = [], []

    def generate(self, prompt, system=None, *, json_schema=None):
        self.gen.append((prompt, system, json_schema))
        return f"reply-{len(self.gen)}"

    def embed(self, texts, task=None):
        self.emb.append((tuple(texts), task))
        return [[float(len(t)), 1.0] for t in texts]


@pytest.fixture
def cache(tmp_path):
    c = KVCache(tmp_path / "c.sqlite")
    yield c
    c.close()


def test_embeddings_are_cached_per_text_and_per_task(cache):
    base = Counting()
    p = CachingProvider(base, cache)
    a = p.embed(["aa", "b"], task="document")
    assert p.embed(["aa", "b"], task="document") == a and len(base.emb) == 1
    p.embed(["aa", "ccc"], task="document")                       # only the new text goes to the provider
    assert base.emb[-1] == (("ccc",), "document")
    p.embed(["aa"], task="query")                                 # a different task is a different vector
    assert base.emb[-1] == (("aa",), "query")
    assert p.usage.snapshot()["cache_hits"] == 2 + 1


def test_embedding_cache_survives_a_new_process(tmp_path):
    base1, base2 = Counting(), Counting()
    c1 = KVCache(tmp_path / "x.sqlite")
    CachingProvider(base1, c1).embed(["hello"], task="query")
    c1.close()
    c2 = KVCache(tmp_path / "x.sqlite")
    CachingProvider(base2, c2).embed(["hello"], task="query")
    c2.close()
    assert base1.emb and not base2.emb


def test_generation_is_not_cached_unless_asked(cache):
    base = Counting()
    p = CachingProvider(base, cache)
    assert (p.generate("q"), p.generate("q")) == ("reply-1", "reply-2")


def test_cached_generation_is_keyed_on_prompt_system_schema_and_model(cache):
    base = Counting()
    p = CachingProvider(base, cache, cache_generate=True)
    first = p.generate("q", "sys")
    assert p.generate("q", "sys") == first and len(base.gen) == 1
    assert p.generate("q2", "sys") != first and p.generate("q", "other") != first
    p.generate("q", "sys", json_schema={"type": "array"})
    assert len(base.gen) == 4
    base.model = "m2"                                            # a different model never reads the old answer
    p.generate("q", "sys")
    assert len(base.gen) == 5


def test_caching_provider_mirrors_the_base_capabilities(cache):
    p = CachingProvider(Counting(), cache)
    assert p.name == "count" and p.model == "m1" and p.supports_json_schema and p.supports_embed_task
    q = CachingProvider(FakeProvider(), cache)
    assert not q.supports_json_schema and q.embed(["a"]) == FakeProvider().embed(["a"])


# ------------------------------------------------------------------ composite + helper functions
def test_composite_generates_with_one_and_embeds_with_the_other():
    gen, emb = Counting(), Counting()
    gen.name, emb.name = "gen", "emb"
    comp = CompositeProvider(gen, emb)
    comp.generate("p", json_schema={"type": "array"})
    comp.embed(["x"], task="query")
    assert gen.gen and not gen.emb and emb.emb and not emb.gen
    assert comp.name == "gen" and comp.embed_model == "e1" and comp.supports_embed_task
    gen.usage.add(calls=2)
    emb.usage.add(embed_calls=3)
    snap = comp.usage.snapshot()
    assert snap["calls"] == 2 and snap["embed_calls"] == 3


def test_helpers_pass_optional_arguments_only_to_providers_that_declare_them():
    class Plain(LLMProvider):
        def generate(self, prompt, system=None):
            return "g"

        def embed(self, texts):
            return [[1.0]]
    p = Plain()
    assert generate_text(p, "x", None, json_schema={"type": "array"}) == "g"      # schema silently not passed
    assert embed_texts(p, ["a"], task="query") == [[1.0]]                           # task silently not passed
    c = Counting()
    generate_text(c, "x", None, json_schema={"type": "array"})
    embed_texts(c, ["a"], task="query")
    assert c.gen[0][2] == {"type": "array"} and c.emb[0][1] == "query"


# ------------------------------------------------------------------ factory
@pytest.fixture
def env(monkeypatch, tmp_path):
    for k in ("LLM_PROVIDER", "EMBED_PROVIDER", "GEMINI_API_KEY", "ANTHROPIC_API_KEY", "CLAUDE_MODEL",
              "GEMINI_MODEL", "GEMINI_EMBED_MODEL", "LLM_CACHE_GENERATE", "LLM_CACHE_EMBED", "CLAUDE_FALLBACK_MODEL"):
        monkeypatch.delenv(k, raising=False)
    monkeypatch.setenv("LLM_CACHE_PATH", str(tmp_path / "cache.sqlite"))
    get_provider.cache_clear()
    yield monkeypatch
    get_provider.cache_clear()


def test_default_is_the_offline_fake_with_no_cache(env):
    p = get_provider()
    assert isinstance(p, FakeProvider)


def test_gemini_needs_a_key_and_uses_current_default_models(env):
    env.setenv("LLM_PROVIDER", "gemini")
    with pytest.raises(LLMError, match="GEMINI_API_KEY"):
        get_provider()
    get_provider.cache_clear()
    env.setenv("GEMINI_API_KEY", "k")
    p = get_provider()
    assert isinstance(p, CachingProvider) and p.name == "gemini"
    assert p.model == "gemini-3.6-flash" and p.embed_model == "gemini-embedding-2"
    assert p.cache_embed and not p.cache_generate


def test_claude_generates_and_gemini_embeds_by_default(env):
    env.setenv("LLM_PROVIDER", "claude")
    env.setenv("ANTHROPIC_API_KEY", "sk-ant-x")
    with pytest.raises(LLMError, match="GEMINI_API_KEY"):
        get_provider()                                           # embeddings need Gemini: say so
    get_provider.cache_clear()
    env.setenv("GEMINI_API_KEY", "k")
    p = get_provider()
    assert p.name == "claude" and p.model == "claude-opus-5-5" and p.embed_model == "gemini-embedding-2"
    assert p.base.embed_provider_name == "gemini"


def test_claude_without_a_key_and_bad_settings_are_refused(env):
    env.setenv("LLM_PROVIDER", "claude")
    env.setenv("GEMINI_API_KEY", "k")
    with pytest.raises(LLMError, match="ANTHROPIC_API_KEY"):
        get_provider()
    get_provider.cache_clear()
    env.setenv("LLM_PROVIDER", "nonsense")
    with pytest.raises(LLMError, match="unknown LLM_PROVIDER"):
        get_provider()
    get_provider.cache_clear()
    env.setenv("LLM_PROVIDER", "gemini")
    env.setenv("EMBED_PROVIDER", "claude")
    with pytest.raises(LLMError, match="no embeddings endpoint"):
        get_provider()


def test_generation_cache_is_opt_in_by_environment(env):
    env.setenv("LLM_PROVIDER", "gemini")
    env.setenv("GEMINI_API_KEY", "k")
    env.setenv("LLM_CACHE_GENERATE", "1")
    assert get_provider().cache_generate is True
