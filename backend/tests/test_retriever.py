import numpy as np
import pytest
from fastapi.testclient import TestClient

from app.llm.fake import FakeProvider
from app.llm.gemini import GeminiProvider
from app.llm.provider import LLMError, load_prompt
from app.main import app
from app.rag.examples import load_examples
from app.rag.retriever import Retriever

EXAMPLES = load_examples()


@pytest.fixture()
def retriever(tmp_path):
    return Retriever(FakeProvider(), EXAMPLES, tmp_path / "index.npz")


def test_exact_english_ranks_itself_first(retriever):
    misses = [e.id for e in EXAMPLES if retriever.search(e.english, k=1)[0].id != e.id]
    assert len(misses) <= 2, misses             # near-duplicate rules may swap; almost all must match


def test_every_example_found_in_top3_by_its_own_text(retriever):
    for e in EXAMPLES:
        assert e.id in [r.id for r in retriever.search(e.english, k=3)], e.id


@pytest.mark.parametrize("query,expected", [
    ("The agent must never open the door during the night", "sh-night-lock"),
    ("keep the thermostat between 16 and 28 degrees", "sh-thermostat-range"),
    ("nobody can delete any table in prod", "db-drop-not-production"),
    ("transfers over 10000 must be approved by a human", "fin-large-needs-approval"),
    ("agents cannot email people outside the company", "net-email-internal-only"),
])
def test_paraphrases_land_in_top3(retriever, query, expected):
    assert expected in [r.id for r in retriever.search(query, k=3)]


def test_k_and_scores_and_order(retriever):
    r = retriever.search("unlock the door at night", k=5)
    assert len(r) == 5
    assert [x.score for x in r] == sorted((x.score for x in r), reverse=True)
    assert all(-1.0 <= x.score <= 1.0001 for x in r)
    assert r[0].gold_yog.strip()


def test_empty_query_returns_nothing(retriever):
    assert retriever.search("   ") == []


def test_index_saved_reused_and_rebuild_idempotent(tmp_path):
    p = tmp_path / "i.npz"
    r1 = Retriever(FakeProvider(), EXAMPLES, p)
    r1.build_index()
    first = np.load(p)["vectors"].copy()
    r1.build_index()
    assert np.array_equal(first, np.load(p)["vectors"])

    class Counting(FakeProvider):
        calls = 0
        def embed(self, texts):
            Counting.calls += len(texts)
            return super().embed(texts)

    r2 = Retriever(Counting(), EXAMPLES, p)          # different provider name? same name "fake" -> index reused
    r2.search("anything about doors", k=1)
    assert Counting.calls == 1                       # only the query was embedded


def test_stale_index_is_rebuilt_when_examples_change(tmp_path):
    p = tmp_path / "i.npz"
    Retriever(FakeProvider(), EXAMPLES, p).build_index()
    fewer = EXAMPLES[:10]
    r = Retriever(FakeProvider(), fewer, p)
    res = r.search("door", k=3)
    assert all(x.id in {e.id for e in fewer} for x in res)


def test_corrupt_index_is_rebuilt(tmp_path):
    p = tmp_path / "i.npz"
    p.write_bytes(b"garbage")
    assert Retriever(FakeProvider(), EXAMPLES, p).search("door", k=1)


def test_api_retrieve(monkeypatch, tmp_path):
    from app.api import retrieve as mod
    monkeypatch.setattr(mod, "get_retriever", lambda: Retriever(FakeProvider(), EXAMPLES, tmp_path / "i.npz"))
    app.dependency_overrides[mod.get_retriever] = lambda: Retriever(FakeProvider(), EXAMPLES, tmp_path / "i.npz")
    try:
        c = TestClient(app)
        r = c.post("/retrieve", json={"english": "never unlock the door between 11pm and 6am", "k": 3})
        assert r.status_code == 200
        ids = [x["id"] for x in r.json()["results"]]
        assert len(ids) == 3 and "sh-night-lock" in ids
        assert c.post("/retrieve", json={"english": "x", "k": 0}).status_code == 422
        assert len(c.get("/examples").json()) >= 60
    finally:
        app.dependency_overrides.clear()


def test_gemini_requires_key():
    with pytest.raises(LLMError):
        GeminiProvider("", "m", "e")


def test_fake_generate_scripted_and_default():
    p = FakeProvider(["one", "two"])
    assert (p.generate("a"), p.generate("b")) == ("one", "two")
    assert p.prompts == ["a", "b"]
    with pytest.raises(AssertionError):
        p.generate("c")
    echo = FakeProvider().generate("x\n```yog\nfact a(b)\n```\n")
    assert "fact a(b)" in echo and "OFFLINE FAKE" in echo


def test_load_prompt_missing_raises():
    with pytest.raises(FileNotFoundError):
        load_prompt("does_not_exist")
