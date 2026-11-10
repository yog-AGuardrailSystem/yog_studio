"""The retrieval evaluation harness and the paraphrase set it uses; plus the small-sample statistics."""
import difflib
import re

import pytest

from app.benchmark.retrieval_eval import evaluate_retrieval, load_paraphrases, to_markdown
from app.benchmark.stats import fmt, percentile, proportion, wilson
from app.llm.fake import FakeProvider
from app.rag.examples import load_retrieval_examples

EXAMPLES = {e.id: e for e in load_retrieval_examples()}
PARAS = load_paraphrases()
STOP = {"the", "a", "an", "of", "to", "in", "and", "or", "for", "is", "are", "be", "may", "can", "only", "any", "not",
        "no", "never", "that", "it", "with", "on", "at", "by", "as", "their", "its", "than", "does", "do", "must"}


def words(text):
    return {w for w in re.findall(r"[a-z]+", text.lower()) if w not in STOP and len(w) > 2}


# ------------------------------------------------------------------ statistics
def test_wilson_interval_known_values_and_bounds():
    lo, hi = wilson(5, 8)
    assert (round(lo, 3), round(hi, 3)) == (0.306, 0.863)
    assert wilson(0, 10)[0] == 0.0 and wilson(10, 10)[1] == 1.0
    assert wilson(0, 0) == (0.0, 1.0)
    lo, hi = wilson(9, 10)
    assert 0 < lo < 0.9 < hi <= 1.0


def test_interval_narrows_as_n_grows():
    narrow = wilson(80, 100)
    wide = wilson(8, 10)
    assert (narrow[1] - narrow[0]) < (wide[1] - wide[0])


def test_proportion_and_formatting():
    p = proportion(5, 8)
    assert p == {"k": 5, "n": 8, "pct": 62.5, "ci_low": 30.6, "ci_high": 86.3}
    assert fmt(p) == "62.5% (5/8, 95% CI 30.6 to 86.3)"
    assert proportion(0, 0)["pct"] is None and "no items" in fmt(proportion(0, 0))


def test_percentile_nearest_rank():
    assert percentile([], 50) is None
    assert percentile([1, 2, 3, 4], 50) == 2 and percentile([1, 2, 3, 4], 95) == 4 and percentile([7], 95) == 7


# ------------------------------------------------------------------ the paraphrase set
def test_every_example_has_an_easy_paraphrase_and_hard_ones_target_real_examples():
    easy = {p["id"] for p in PARAS if p.get("tier", "easy") == "easy"}
    assert easy == set(EXAMPLES), "one easy paraphrase per retrievable example"
    hard = [p for p in PARAS if p.get("tier") == "hard"]
    assert len(hard) >= 30 and all(p["id"] in EXAMPLES for p in hard)


def test_paraphrases_are_rewordings_not_copies():
    for p in PARAS:
        ratio = difflib.SequenceMatcher(None, p["paraphrase"].lower(), EXAMPLES[p["id"]].english.lower()).ratio()
        assert p["paraphrase"].strip().lower() != EXAMPLES[p["id"]].english.strip().lower(), p["id"]
        assert ratio < 0.97, f"{p['id']} is nearly identical to its source ({ratio:.2f})"


def test_the_hard_tier_really_is_lexically_distant():
    """If hard paraphrases still share most content words with the source, the tier measures nothing."""
    def overlap(ps):
        vals = [len(words(p["paraphrase"]) & words(EXAMPLES[p["id"]].english)) / max(1, len(words(EXAMPLES[p["id"]].english)))
                for p in ps]
        return sum(vals) / len(vals)
    easy = overlap([p for p in PARAS if p.get("tier", "easy") == "easy"])
    hard = overlap([p for p in PARAS if p.get("tier") == "hard"])
    assert hard < easy - 0.12, f"hard tier overlaps {hard:.2f} vs easy {easy:.2f}: not harder"
    assert hard < 0.45


# ------------------------------------------------------------------ the evaluation itself
def test_evaluation_structure_and_the_offline_baseline_gap():
    r = evaluate_retrieval(FakeProvider())
    assert r["provider"] == "fake" and r["overall"]["n"] == len(PARAS)
    easy, hard = r["by_tier"]["easy"], r["by_tier"]["hard"]
    assert easy["n"] == len(EXAMPLES) and hard["n"] >= 30
    for m in (easy, hard):
        assert m["recall@1"]["pct"] <= m["recall@3"]["pct"] <= m["recall@5"]["pct"]
        assert 0 <= m["mrr"] <= 1
    assert easy["recall@1"]["pct"] > hard["recall@1"]["pct"], "the keyword baseline finds the hard tier harder"
    assert set(r["by_source"]) == {"claude-draft", "team"}
    assert all(row["rank"] is None or row["rank"] >= 1 for row in r["rows"])
    assert r["misses"] and all(not m["rank"] or m["rank"] > 1 for m in r["misses"])


def test_unknown_example_ids_are_an_error_not_silently_skipped():
    with pytest.raises(ValueError, match="unknown examples"):
        evaluate_retrieval(FakeProvider(), paraphrases=[{"id": "nope", "paraphrase": "x"}])


def test_a_provider_that_always_returns_the_same_vector_scores_near_chance():
    class Constant(FakeProvider):
        def embed(self, texts):
            return [[1.0] + [0.0] * 7 for _ in texts]
    r = evaluate_retrieval(Constant(), paraphrases=PARAS[:40], hybrid=False)
    assert r["overall"]["recall@1"]["pct"] < 15, "ties everywhere: the harness must not flatter a useless embedder"


def test_markdown_report_shows_tiers_and_sources():
    md = to_markdown(evaluate_retrieval(FakeProvider(), paraphrases=PARAS[:20]))
    assert "recall@1" in md and "easy paraphrases" in md and "claude-draft" in md
