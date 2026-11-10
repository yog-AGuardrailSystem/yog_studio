"""Strict RAG: relevance floor, per-provider index, hybrid ranking, grounded flag, citations, optional reranker."""
import json

import pytest

from app.benchmark.retrieval_eval import calibrate_floor, load_negatives
from app.core.models import Tool
from app.engine.python_prototype import PythonPrototypeAdapter
from app.llm.fake import FakeProvider
from app.rag.examples import load_retrieval_examples
from app.rag.rerank import parse_scores, rerank
from app.rag.retriever import PROVISIONAL_FLOOR, Retriever, floor_for, index_path_for
from app.translate.translator import extract_yog, parse_citations, translate

EXAMPLES = load_retrieval_examples()
ADAPTER = PythonPrototypeAdapter()
NIGHT = next(e for e in EXAMPLES if e.id == "sh-night-lock")
TOOLS = [Tool(name="unlock_door", source_line=1)]
OFF_TOPIC = "What is the capital of France?"


class Scripted(FakeProvider):
    """Stands in for a real LLM (name is not 'fake', so the reranker and live behaviour are exercised)."""
    name = "scripted"


@pytest.fixture()
def retriever(tmp_path):
    return Retriever(FakeProvider(), EXAMPLES, tmp_path / "i.npz")


# ------------------------------------------------------------------ floor
def test_on_topic_query_clears_the_floor(retriever):
    top = retriever.search(NIGHT.english, ["unlock_door"], 3)[0]
    assert top.id == "sh-night-lock" and top.relevant


@pytest.mark.parametrize("query", [n["query"] for n in load_negatives()])
def test_off_topic_queries_never_clear_the_floor(retriever, query):
    assert not any(r.relevant for r in retriever.search(query, [], 3)), query


def test_floor_is_calibrated_for_the_offline_provider():
    floor, calibrated = floor_for(FakeProvider())
    assert calibrated and 0.1 < floor < 0.9


def test_unknown_provider_gets_a_provisional_uncalibrated_floor():
    class Other(FakeProvider):
        name = "someone-else"
    assert floor_for(Other()) == (PROVISIONAL_FLOOR, False)


def test_env_override_wins(monkeypatch):
    monkeypatch.setenv("RETRIEVAL_FLOOR", "0.9")
    assert floor_for(FakeProvider()) == (0.9, True)
    monkeypatch.setenv("RETRIEVAL_FLOOR", "not-a-number")
    assert floor_for(FakeProvider())[1] is True              # falls back to the committed calibration


def test_calibration_is_strict_no_off_topic_query_passes():
    """The offline bag-of-words embedder cannot bridge heavily reworded rules, so its distributions overlap; the floor
    then sits just above the best off-topic score and the cost (positives kept) is reported, not hidden."""
    cal = calibrate_floor(FakeProvider())
    assert cal["negatives_rejected"] == 1.0 and cal["floor"] > cal["negative_max"]
    assert cal["positives_kept"] >= 0.5
    assert cal["separable"] == (cal["negative_max"] < cal["positive_p10"])


def test_committed_floor_matches_a_fresh_calibration():
    """benchmark/retrieval_floors.json must be regenerated (retrieval_eval --calibrate) when embeddings or examples change."""
    committed, _ = floor_for(FakeProvider())
    assert committed == pytest.approx(calibrate_floor(FakeProvider())["floor"], abs=0.002)


def test_calibration_reports_overlap_instead_of_hiding_it():
    class Constant(FakeProvider):                           # every example looks identical: nothing separates
        def embed(self, texts):
            return [[1.0] + [0.0] * 7 for _ in texts]
    cal = calibrate_floor(Constant(), paraphrases=[{"id": NIGHT.id, "paraphrase": "never unlock at night"}])
    assert not cal["separable"] and cal["floor"] > cal["negative_max"]


# ------------------------------------------------------------------ index files
def test_each_provider_and_model_gets_its_own_index_file(tmp_path):
    class A(FakeProvider):
        name, embed_model = "gemini", "gemini-embedding-2"

    class B(FakeProvider):
        name, embed_model = "gemini", "gemini-embedding-001"
    paths = {index_path_for(FakeProvider(), tmp_path), index_path_for(A(), tmp_path), index_path_for(B(), tmp_path)}
    assert len(paths) == 3 and all(p.parent == tmp_path for p in paths)


def test_switching_providers_does_not_overwrite_the_other_index(tmp_path, monkeypatch):
    import app.rag.retriever as mod
    monkeypatch.setattr(mod, "DATA_DIR", tmp_path)

    class Gem(FakeProvider):
        name, embed_model = "gemini", "gemini-embedding-2"
    small = EXAMPLES[:6]
    fake_path = Retriever(FakeProvider(), small).index_path
    Retriever(FakeProvider(), small).build_index()
    before = fake_path.read_bytes()
    Retriever(Gem(), small).build_index()
    assert fake_path.read_bytes() == before and (tmp_path / "index-gemini-gemini-embedding-2.npz").exists()


# ------------------------------------------------------------------ hybrid ranking
def test_tool_names_nudge_the_ranking(retriever):
    everything = len(EXAMPLES)
    plain = {r.id: r.fused for r in retriever.search("restrict this action", [], everything)}
    boosted = {r.id: r.fused for r in retriever.search("restrict this action", ["unlock_door"], everything)}
    assert boosted["sh-night-lock"] > plain["sh-night-lock"]
    other = next(e.id for e in EXAMPLES if not any(t.startswith("unlock_door") for t in e.tools_context))
    assert boosted[other] == pytest.approx(plain[other])


def test_results_are_ordered_by_fused_score_and_expose_both_signals(retriever):
    r = retriever.search("only admins may drop a table in the database", [], 5)
    assert [x.fused for x in r] == sorted((x.fused for x in r), reverse=True)
    assert all(0.0 <= x.lexical <= 1.0 for x in r) and r[0].lexical > 0


def test_dense_only_mode_ignores_keywords_and_tools(tmp_path):
    r = Retriever(FakeProvider(), EXAMPLES, tmp_path / "i.npz", hybrid=False)
    plain, boosted = r.search("restrict this action", [], 5), r.search("restrict this action", ["unlock_door"], 5)
    assert [x.id for x in plain] == [x.id for x in boosted]


# ------------------------------------------------------------------ citations
def test_parse_citations():
    allowed = {"a", "b"}
    assert parse_citations("```yog\nx\n```\nUSED_EXAMPLES: a, b", allowed) == (["a", "b"], [], False)
    assert parse_citations("x\nused_examples: none", allowed) == ([], [], True)
    ids, problems, _ = parse_citations("x\nUSED_EXAMPLES: a, made-up", allowed)
    assert ids == ["a"] and "made-up" in problems[0]
    assert parse_citations("x", allowed)[1] == ["the model did not say which examples it used"]
    assert parse_citations("x", set())[1] == []              # nothing was offered, nothing to cite


def test_citation_line_never_leaks_into_the_policy():
    assert extract_yog("fact a(b)\nUSED_EXAMPLES: none") == "fact a(b)\n"
    assert extract_yog("```yog\nfact a(b)\n```\nUSED_EXAMPLES: x") == "fact a(b)\n"


def _reply(body: str, cite: str | None) -> str:
    return f"```yog\n{body}```" + (f"\nUSED_EXAMPLES: {cite}" if cite is not None else "")


def _run(retriever, provider, rules, **kw):
    return translate(rules, TOOLS, provider, retriever, ADAPTER, **kw)


def test_grounded_draft_keeps_only_valid_citations(retriever):
    prov = Scripted(lambda p: _reply(NIGHT.gold_yog, "sh-night-lock, invented-id"))
    d = _run(retriever, prov, [NIGHT.english])
    assert d.valid and d.grounded
    assert d.cited_examples == ["sh-night-lock"]
    assert any("invented-id" in p for p in d.citation_problems)


def test_missing_citation_is_reported(retriever):
    d = _run(retriever, Scripted(lambda p: _reply(NIGHT.gold_yog, None)), [NIGHT.english])
    assert d.valid and d.cited_examples == [] and d.citation_problems


def test_only_relevant_examples_reach_the_prompt(retriever):
    seen = []
    prov = Scripted(lambda p: seen.append(p) or _reply(NIGHT.gold_yog, "none"))
    d = _run(retriever, prov, [NIGHT.english])
    shown_relevant = {r.id for r in d.retrieved if r.relevant}
    in_prompt = {i for i in (e.id for e in EXAMPLES) if f"Example [{i}]" in seen[0]}
    assert in_prompt == shown_relevant and in_prompt


def test_off_topic_rule_is_ungrounded_and_prompt_says_so(retriever):
    seen = []
    prov = Scripted(lambda p: seen.append(p) or _reply(NIGHT.gold_yog, "sh-night-lock"))
    d = _run(retriever, prov, [OFF_TOPIC])
    assert d.grounded is False and d.retrieved                  # weak matches are still shown to the user...
    assert not any(r.relevant for r in d.retrieved)
    assert "Example [" not in seen[0] and "no stored example is close enough" in seen[0]   # ...but never given to the model
    assert d.cited_examples == [] and d.citation_problems       # a citation of something never offered is a problem
    assert d.floor is not None and d.floor_calibrated is True


def test_offline_provider_cannot_draft_an_ungrounded_rule(retriever):
    d = _run(retriever, FakeProvider(), [OFF_TOPIC])
    assert d.grounded is False and not d.valid and d.errors


def test_events_report_grounding_and_floor(retriever):
    events = []
    _run(retriever, FakeProvider(), [NIGHT.english], on_event=events.append)
    ev = next(e for e in events if e["phase"] == "retrieved")
    assert ev["grounded"] is True and ev["floor"] and ev["calibrated"] is True


# ------------------------------------------------------------------ reranker
def test_parse_scores_is_forgiving_but_strict_about_ids():
    ids = {"a", "b"}
    assert parse_scores('noise [{"id":"a","score":9},{"id":"b","score":42},{"id":"zzz","score":3}] tail', ids) == {"a": 9.0, "b": 10.0}
    assert parse_scores("not json", ids) == {}
    assert parse_scores('[{"id":"a","score":"high"},{"id":"b","score":true}]', ids) == {}


def _cands(retriever, n=6):
    return retriever.search("only admins may drop a table in the database", [], n)


def test_rerank_reorders_and_flags_relevance(retriever):
    cands = _cands(retriever)
    last = cands[-1].id
    reply = json.dumps([{"id": c.id, "score": 9 if c.id == last else 2} for c in cands])
    out, problem = rerank(Scripted(lambda p: reply), ["rule"], cands, top=3)
    assert problem is None and out[0].id == last and out[0].rerank == 9 and out[0].relevant
    assert all(not c.relevant for c in out[1:])


@pytest.mark.parametrize("reply", ["garbage", "[]", '[{"id":"zzz","score":9}]'])
def test_rerank_failure_keeps_the_original_order(retriever, reply):
    cands = _cands(retriever)
    out, problem = rerank(Scripted(lambda p: reply), ["rule"], cands, top=3)
    assert problem and [c.id for c in out] == [c.id for c in cands[:3]]


def test_rerank_survives_a_failing_llm(retriever):
    from app.llm.provider import LLMError

    def boom(prompt):
        raise LLMError("quota")
    cands = _cands(retriever)
    out, problem = rerank(Scripted(boom), ["rule"], cands, top=3)
    assert "quota" in problem and [c.id for c in out] == [c.id for c in cands[:3]]


def test_translate_uses_the_reranker_only_when_asked_and_only_for_a_real_llm(retriever):
    calls = []

    def llm(prompt):
        calls.append("rerank" if "judge how useful" in prompt else "draft")
        if "judge how useful" in prompt:
            ids = [line.split(": ", 1)[1] for line in prompt.splitlines() if line.startswith("- id: ")]
            return json.dumps([{"id": i, "score": 10 if i == "sh-night-lock" else 0} for i in ids])
        return _reply(NIGHT.gold_yog, "sh-night-lock")

    d = _run(retriever, Scripted(llm), [NIGHT.english], rerank=True)
    assert d.reranked and calls[0] == "rerank" and d.retrieved[0].rerank == 10 and d.cited_examples == ["sh-night-lock"]

    calls.clear()
    assert not _run(retriever, Scripted(llm), [NIGHT.english]).reranked and "rerank" not in calls
    assert not _run(retriever, FakeProvider(), [NIGHT.english], rerank=True).reranked   # offline cannot judge


# ------------------------------------------------------------------ measured defaults
def test_keyword_fusion_is_off_by_default_and_overridable(monkeypatch):
    """Measured to hurt both embedders (docs/decisions.md #21); the knob stays for experiments."""
    from app.rag.retriever import default_lex_weight
    monkeypatch.delenv("RETRIEVAL_LEX_WEIGHT", raising=False)
    assert default_lex_weight(FakeProvider()) == 0.0
    monkeypatch.setenv("RETRIEVAL_LEX_WEIGHT", "0.5")
    assert default_lex_weight(FakeProvider()) == 0.5
    monkeypatch.setenv("RETRIEVAL_LEX_WEIGHT", "junk")
    assert default_lex_weight(FakeProvider()) == 0.0


def test_the_query_is_the_rule_alone_so_tool_names_cannot_inflate_relevance(retriever):
    everything = len(EXAMPLES)
    with_tools = retriever.search(OFF_TOPIC, ["unlock_door", "open_valve"], everything)
    without = retriever.search(OFF_TOPIC, [], everything)
    assert {r.id: r.score for r in with_tools} == {r.id: r.score for r in without}   # similarity ignores tools
    assert not any(r.relevant for r in with_tools)


def test_retrieval_eval_does_not_hand_out_the_answers_tool_names():
    from app.benchmark.retrieval_eval import evaluate_retrieval, load_paraphrases
    res = evaluate_retrieval(FakeProvider(), paraphrases=load_paraphrases()[:5])
    assert res["oracle_tools"] is False
