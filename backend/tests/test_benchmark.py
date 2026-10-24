import pytest

from app.benchmark.runner import (BENCH_FILE, LEAK_THRESHOLD, leakage, load_benchmark, run, semantic_match,
                                  to_markdown, tools_from_context)
from app.engine.python_prototype import PythonPrototypeAdapter
from app.llm.fake import FakeProvider
from app.rag.examples import load_examples

adapter = PythonPrototypeAdapter()
BENCH = load_benchmark()
EXAMPLES = load_examples()


def test_at_least_30_unique_rules_disjoint_from_retrieval_set():
    assert len(BENCH) >= 30
    ids = {b.id for b in BENCH}
    assert len(ids) == len(BENCH) and not ids & {e.id for e in EXAMPLES}
    assert not {b.english.strip().lower() for b in BENCH} & {e.english.strip().lower() for e in EXAMPLES}
    assert not {b.gold_yog.strip() for b in BENCH} & {e.gold_yog.strip() for e in EXAMPLES}


@pytest.mark.parametrize("b", BENCH, ids=lambda b: b.id)
def test_gold_valid_and_scenarios_hold(b):
    assert adapter.validate(b.gold_yog) == []
    assert {s.expected for s in b.scenarios} == {"ALLOW", "DENY"} or b.id in {"bm-02"}, "scenarios should cover both outcomes"
    for s in b.scenarios:
        assert adapter.check(b.gold_yog, s.actor, s.action, s.resource, s.context).decision == s.expected, (b.id, s)


def test_no_benchmark_rule_leaks_from_retrieval_examples():
    over = [(a, b, s) for a, b, s in leakage(FakeProvider(), BENCH, EXAMPLES) if s > LEAK_THRESHOLD]
    assert over == []


def test_tools_from_context_parses():
    t = tools_from_context(["set_oven(temperature)", "open_garage()", "x(a, b)"])
    assert [x.name for x in t] == ["set_oven", "open_garage", "x"] and [p.name for p in t[2].params] == ["a", "b"]


def test_semantic_match_compares_decisions_not_text():
    b = BENCH[0]
    reformatted = b.gold_yog.replace("H < 5", "H <  5")                   # different text, same behaviour
    assert semantic_match(adapter, b, reformatted)
    assert not semantic_match(adapter, b, b.gold_yog.replace("H < 5", "H < 3"))
    assert not semantic_match(adapter, b, "fact role(agent, assistant)\nallow can_unlock_door(A, D):\n    role(A, assistant)\n")


def test_run_with_fake_provider_is_labelled_and_consistent():
    res = run(adapter, FakeProvider(), limit=6)
    assert res["provider"] == "fake" and "NOT translation" in res["interpretation"]
    for cfg in ("with_retry", "without_retry"):
        assert res[cfg]["n"] == 6 and 0 <= res[cfg]["semantic_correct_pct"] <= res[cfg]["syntax_valid_pct"] <= 100
    assert res["with_retry"]["max_attempts"] == 3 and res["without_retry"]["max_attempts"] == 1
    assert res["leakage"]["over_threshold"] == []
    assert "without retry" in to_markdown(res)


def test_retry_loop_helps_with_a_scripted_provider():
    """First reply of every rule is broken, second is the gold policy: retry=100% correct, no-retry=0%."""
    sub = BENCH[:4]
    replies = {}
    for b in sub:
        replies[b.english] = b.gold_yog

    class Scripted(FakeProvider):
        def __init__(self):
            super().__init__()
            self.seen = {}

        def generate(self, prompt, system=None):
            self.prompts.append(prompt)
            key = next(k for k in replies if k in prompt)
            self.seen[key] = self.seen.get(key, 0) + 1
            if self.seen[key] % 2 == 1 and "Problems found" not in prompt:
                return "```yog\nallow broken(:\n```"
            return "```yog\n" + replies[key] + "\n```"

    import app.benchmark.runner as r
    orig = r.load_benchmark
    r.load_benchmark = lambda path=BENCH_FILE: sub
    try:
        res = run(adapter, Scripted())
    finally:
        r.load_benchmark = orig
    assert res["with_retry"]["semantic_correct_pct"] == 100.0 and res["with_retry"]["avg_attempts"] == 2.0
    assert res["without_retry"]["semantic_correct_pct"] == 0.0 and res["without_retry"]["failure_categories"] == {"syntax": 4}
