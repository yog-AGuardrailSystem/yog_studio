"""Real LLM / Offline switch (per request) and the abuse + cost guards."""
import json

import pytest
from fastapi.testclient import TestClient

import app.llm.factory as factory
import app.rag.retriever as retriever_mod
from app.core.guard import LiveBudget, RateLimiter
from app.llm.fake import FakeProvider
from app.main import app
from app.rag.examples import load_retrieval_examples

NIGHT = next(e for e in load_retrieval_examples() if e.id == "sh-night-lock")
TOOLS = [{"name": "unlock_door", "source_line": 1}]
BODY = {"english_rules": [NIGHT.english], "tools": TOOLS}


class Live(FakeProvider):
    """A stand-in for the configured real LLM."""
    name = "scripted"

    def __init__(self):
        super().__init__(lambda p: "```yog\n" + NIGHT.gold_yog + "```\nUSED_EXAMPLES: sh-night-lock")


@pytest.fixture()
def client(tmp_path, monkeypatch):
    monkeypatch.setattr(retriever_mod, "DATA_DIR", tmp_path)              # indexes never touch the dev data dir
    for k in ("ALLOW_LIVE_LLM", "LIVE_LLM_DAILY_CAP", "LIVE_RATE_PER_MIN", "RATE_LIMIT_PER_MIN", "MAX_BODY_BYTES"):
        monkeypatch.delenv(k, raising=False)
    return TestClient(app)


@pytest.fixture()
def live(monkeypatch):
    prov = Live()
    monkeypatch.setattr(factory, "real_provider", lambda: prov)
    return prov


# ------------------------------------------------------------------ what the server offers
def test_info_says_live_is_unavailable_without_a_key(client):
    j = client.get("/info").json()
    assert j["live_available"] is False and j["live_ready"] is False and "no API key" in j["live_reason"]
    assert j["default_mode"] == "offline"


def test_info_reports_live_ready_when_a_key_exists(client, monkeypatch):
    monkeypatch.setenv("GEMINI_API_KEY", "k")
    j = client.get("/info").json()
    assert j["live_available"] and j["live_ready"] and j["live_provider"] == "gemini" and j["live_reason"] is None


def test_operator_can_switch_live_off(client, monkeypatch):
    monkeypatch.setenv("GEMINI_API_KEY", "k")
    monkeypatch.setenv("ALLOW_LIVE_LLM", "0")
    j = client.get("/info").json()
    assert j["live_available"] and not j["live_ready"] and "switched off" in j["live_reason"]


@pytest.mark.parametrize("env,expected", [
    ({}, None),
    ({"GEMINI_API_KEY": "k"}, ("gemini", "gemini")),
    ({"ANTHROPIC_API_KEY": "a"}, None),                                  # Claude cannot embed: needs the Gemini key too
    ({"ANTHROPIC_API_KEY": "a", "GEMINI_API_KEY": "k"}, ("gemini", "gemini")),      # Gemini first unless Claude is chosen
    ({"LLM_PROVIDER": "gemini"}, None),                                  # chosen but no key
    ({"LLM_PROVIDER": "claude", "ANTHROPIC_API_KEY": "a", "GEMINI_API_KEY": "k"}, ("claude", "gemini")),
])
def test_which_real_provider_is_used(monkeypatch, env, expected):
    for k in ("LLM_PROVIDER", "EMBED_PROVIDER", "GEMINI_API_KEY", "ANTHROPIC_API_KEY"):
        monkeypatch.delenv(k, raising=False)
    for k, v in env.items():
        monkeypatch.setenv(k, v)
    assert factory.real_names() == expected


# ------------------------------------------------------------------ switching per request
def test_offline_mode_works_without_a_key_and_stays_honest(client):
    r = client.post("/translate", json={**BODY, "mode": "offline"})
    assert r.status_code == 200 and "OFFLINE FAKE" in r.json()["yog_source"]


def test_real_mode_without_a_key_is_refused_with_a_reason(client):
    r = client.post("/translate", json={**BODY, "mode": "real"})
    assert r.status_code == 409 and "no API key" in r.json()["detail"]
    assert client.post("/retrieve", json={"english": NIGHT.english, "mode": "real"}).status_code == 409


def test_real_mode_uses_the_live_provider_and_gets_its_own_index(client, live, tmp_path):
    r = client.post("/translate", json={**BODY, "mode": "real"})
    j = r.json()
    assert r.status_code == 200 and "OFFLINE FAKE" not in j["yog_source"] and j["cited_examples"] == ["sh-night-lock"]
    assert j["verified"] is not False                                     # scenarios came from the same scripted model
    assert (tmp_path / "index-scripted-default.npz").exists()


def test_switching_back_and_forth_needs_no_restart(client, live):
    kinds = [("real", False), ("offline", True), ("real", False)]
    for mode, offline in kinds:
        j = client.post("/translate", json={**BODY, "mode": mode}).json()
        assert ("OFFLINE FAKE" in j["yog_source"]) is offline


def test_no_mode_keeps_the_server_default(client):
    assert "OFFLINE FAKE" in client.post("/translate", json=BODY).json()["yog_source"]


def test_unknown_mode_is_rejected(client):
    assert client.post("/translate", json={**BODY, "mode": "turbo"}).status_code == 422


def test_real_mode_off_on_this_server(client, live, monkeypatch):
    monkeypatch.setenv("ALLOW_LIVE_LLM", "0")
    r = client.post("/translate", json={**BODY, "mode": "real"})
    assert r.status_code == 409 and "switched off" in r.json()["detail"]
    assert client.post("/translate", json={**BODY, "mode": "offline"}).status_code == 200   # offline is never blocked


def test_retrieve_reports_floor_and_grounding(client):
    j = client.post("/retrieve", json={"english": NIGHT.english, "tools": ["unlock_door"], "mode": "offline"}).json()
    assert j["grounded"] is True and j["floor"] and j["floor_calibrated"] is True and j["provider"] == "fake"
    assert j["results"][0]["relevant"] is True
    off = client.post("/retrieve", json={"english": "What is the capital of France?", "mode": "offline"}).json()
    assert off["grounded"] is False and off["results"] and not any(x["relevant"] for x in off["results"])


def test_translate_start_accepts_mode_and_rerank(client, live):
    start = client.post("/translate/start", json={**BODY, "mode": "real", "rerank": True})
    assert start.status_code == 200
    job = client.get(f"/translate/{start.json()['job_id']}").json()
    assert job["status"] in ("running", "done")


# ------------------------------------------------------------------ guards
def test_live_calls_have_a_daily_budget(client, live, monkeypatch):
    monkeypatch.setenv("LIVE_LLM_DAILY_CAP", "2")
    monkeypatch.setenv("LIVE_RATE_PER_MIN", "0")                           # rate limit off: isolate the budget
    codes = [client.post("/translate", json={**BODY, "mode": "real"}).status_code for _ in range(3)]
    assert codes == [200, 200, 429]
    r = client.post("/translate", json={**BODY, "mode": "real"})
    assert "budget" in r.json()["detail"] and "Offline" in r.json()["detail"]
    assert client.post("/translate", json={**BODY, "mode": "offline"}).status_code == 200   # offline is free


def test_live_calls_are_rate_limited_per_client(client, live, monkeypatch):
    monkeypatch.setenv("LIVE_RATE_PER_MIN", "2")
    codes = [client.post("/translate", json={**BODY, "mode": "real"}).status_code for _ in range(3)]
    assert codes == [200, 200, 429]


def test_every_write_is_rate_limited(client, monkeypatch):
    monkeypatch.setenv("RATE_LIMIT_PER_MIN", "3")
    codes = [client.post("/compile", json={"source": "fact a(b)\n"}).status_code for _ in range(5)]
    assert codes[:3] == [200, 200, 200] and codes[3:] == [429, 429]
    r = client.post("/compile", json={"source": "fact a(b)\n"})
    assert r.status_code == 429 and int(r.headers["retry-after"]) >= 1 and "Too many" in r.json()["detail"]
    assert client.get("/health").status_code == 200                       # reads are never limited


def test_huge_bodies_are_refused_before_being_read(client, monkeypatch):
    monkeypatch.setenv("MAX_BODY_BYTES", "200")
    r = client.post("/compile", content=json.dumps({"source": "x" * 5000}), headers={"content-type": "application/json"})
    assert r.status_code == 413


def test_input_fields_are_bounded(client):
    assert client.post("/translate", json={"english_rules": ["r"] * 21}).status_code == 422
    assert client.post("/retrieve", json={"english": "x" * 2001}).status_code == 422
    assert client.post("/translate", json={"english_rules": ["r"], "tools": TOOLS * 101}).status_code == 422


# ------------------------------------------------------------------ .env loading
def test_dotenv_is_read_once_per_call_and_skipped_when_disabled(monkeypatch):
    """Regression: _load_env once called itself forever; tests never noticed because they disable it."""
    calls = []
    monkeypatch.setattr(factory, "load_dotenv", lambda path: calls.append(str(path)))
    monkeypatch.delenv("YOG_NO_DOTENV", raising=False)
    factory._load_env()
    assert len(calls) == 1 and calls[0].replace("\\", "/").endswith("backend/.env")
    monkeypatch.setenv("YOG_NO_DOTENV", "1")
    factory._load_env()
    assert len(calls) == 1


def test_get_provider_and_live_status_work_with_dotenv_enabled(monkeypatch):
    monkeypatch.setattr(factory, "load_dotenv", lambda path: None)
    monkeypatch.delenv("YOG_NO_DOTENV", raising=False)
    monkeypatch.setenv("LLM_PROVIDER", "fake")
    assert factory.get_provider().name == "fake"
    assert factory.live_status()["live_available"] is False


# ------------------------------------------------------------------ guard units
def test_token_bucket_refills_over_time():
    t = [0.0]
    rl = RateLimiter(clock=lambda: t[0])
    assert [rl.allow("g", "ip", 60)[0] for _ in range(61)].count(True) == 60      # burst = per_min
    ok, wait = rl.allow("g", "ip", 60)
    assert not ok and 0 < wait <= 1.0
    t[0] += 1.0                                                                    # 60/min = 1 token a second
    assert rl.allow("g", "ip", 60)[0] and not rl.allow("g", "ip", 60)[0]
    assert rl.allow("g", "other-ip", 60)[0]                                        # clients are independent
    assert rl.allow("other-group", "ip", 60)[0]
    assert rl.allow("g", "ip", 0)[0]                                               # 0 = unlimited


def test_budget_resets_on_a_new_day():
    day = ["2026-11-10"]
    b = LiveBudget(today=lambda: day[0])
    assert [b.spend(2) for _ in range(3)] == [True, True, False]
    day[0] = "2026-11-11"
    assert b.spend(2) and b.snapshot(2)["used"] == 1
    assert LiveBudget(today=lambda: "d").spend(0)                                  # cap 0 = unlimited


def test_forwarded_header_is_trusted_only_when_configured(monkeypatch):
    from starlette.requests import Request
    from app.core.guard import client_ip
    scope = {"type": "http", "headers": [(b"x-forwarded-for", b"9.9.9.9, 10.0.0.1")], "client": ("1.2.3.4", 1)}
    monkeypatch.delenv("RENDER", raising=False)
    monkeypatch.delenv("TRUST_PROXY", raising=False)
    assert client_ip(Request(scope)) == "1.2.3.4"                                  # a spoofable header is ignored by default
    monkeypatch.setenv("TRUST_PROXY", "1")
    assert client_ip(Request(scope)) == "9.9.9.9"


# ------------------------------------------------------------------ approving an ungrounded draft
def test_approving_an_ungrounded_draft_needs_explicit_confirmation(client, tmp_path, monkeypatch):
    from app.api.deps import get_adapter
    from app.api.policies import get_store
    from app.policies.store import PolicyStore
    app.dependency_overrides[get_store] = lambda: PolicyStore(tmp_path / "policies")
    try:
        body = {"yog_source": NIGHT.gold_yog, "english_rules": ["x"], "grounded": False}
        r = client.post("/policies/approve", json=body)
        assert r.status_code == 409 and "read it line by line" in r.json()["detail"]
        assert client.post("/policies/approve", json={**body, "ungrounded_confirmed": True}).status_code == 200
        assert client.post("/policies/approve", json={**body, "grounded": True}).status_code == 200   # grounded drafts are unchanged
    finally:
        app.dependency_overrides.clear()
