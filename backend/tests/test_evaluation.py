"""The evaluation grid: split integrity, ablation retrievers, resume, provenance, and honest labelling of offline runs."""
import json

from app.benchmark import evaluation as ev
from app.benchmark.runner import load_benchmark
from app.engine.python_prototype import PythonPrototypeAdapter
from app.llm.fake import FakeProvider
from app.rag.examples import load_retrieval_examples

BENCH = load_benchmark()
ADAPTER = PythonPrototypeAdapter()


def test_split_is_deterministic_disjoint_and_frozen(tmp_path):
    p = tmp_path / "split.json"
    s1 = ev.get_split(BENCH, p)
    assert set(s1["dev"]).isdisjoint(s1["test"]) and set(s1["dev"]) | set(s1["test"]) == {e.id for e in BENCH}
    assert s1["test"], "a non-empty test set"
    assert ev.get_split(BENCH, p) == s1
    # a rule added later defaults to dev even if its hash would say test
    data = json.loads(p.read_text())
    data["test"] = data["test"][:-1]
    p.write_text(json.dumps(data))
    s2 = ev.get_split(BENCH, p)
    assert len(s2["test"]) == len(s1["test"]) - 1


def test_random_retriever_is_seeded_and_not_relevance_ranked():
    ex = load_retrieval_examples()
    r = ev.RandomRetriever(ex)
    a, b = r.search("deny night unlock", k=3), r.search("deny night unlock", k=3)
    assert [x.id for x in a] == [x.id for x in b] and len(a) == 3
    assert [x.id for x in r.search("something else entirely", k=3)] != [x.id for x in a]
    assert ev.NullRetriever().search("x") == []


def test_grid_on_fake_provider_has_all_configs_and_labels_itself(tmp_path):
    partial = tmp_path / "p.jsonl"
    res = ev.run(ADAPTER, FakeProvider(), split_name="dev", limit=3, partial=partial, split_path=tmp_path / "s.json")
    assert set(res["results"]) == set(ev.CONFIGS)
    assert any("OFFLINE FAKE" in n for n in res["interpretation"])
    assert "oracle" not in res
    for r in res["results"].values():
        assert r["summary"]["n"] == 3 and len(r["rows"]) == 3
    md = ev.to_markdown(res)
    assert "OFFLINE FAKE" in md and "Provenance" in md
    assert len(partial.read_text().strip().splitlines()) == 3 * len(ev.CONFIGS)


def test_resume_does_not_recompute_finished_rows(tmp_path, monkeypatch):
    partial = tmp_path / "p.jsonl"
    kw = dict(split_name="dev", limit=2, config_names=["no-rag"], partial=partial, split_path=tmp_path / "s.json")
    ev.run(ADAPTER, FakeProvider(), **kw)
    calls = []
    monkeypatch.setattr(ev, "run_rule", lambda *a, **k: calls.append(1))
    res = ev.run(ADAPTER, FakeProvider(), **kw)
    assert not calls and res["results"]["no-rag"]["summary"]["n"] == 2


def test_no_rag_config_gets_no_examples_so_the_fake_cannot_echo(tmp_path):
    res = ev.run(ADAPTER, FakeProvider(), split_name="dev", limit=5, config_names=["full", "no-rag"],
                 split_path=tmp_path / "s.json")
    full = res["results"]["full"]["summary"]["semantic_correct"]["k"]
    none = res["results"]["no-rag"]["summary"]["semantic_correct"]["k"]
    assert none <= full


def test_provenance_hashes_are_stable_and_output_dir_separates_fake(tmp_path):
    assert ev.prompt_hash() == ev.prompt_hash() and len(ev.dataset_hash()) == 16
    assert ev.output_dir(FakeProvider(), tmp_path) == tmp_path / "fake"


def test_test_split_runs_are_logged(tmp_path):
    ev.log_test_run({"when": "t", "provider": "fake", "model": None, "prompt_hash": "h", "results": {"full": {}},
                     "git_commit": "abcdef1234567"}, tmp_path)
    assert json.loads((tmp_path / "test_runs.log").read_text().splitlines()[0])["configs"] == ["full"]


def test_summarize_counts_verified_buckets():
    rows = [{"syntax_valid": True, "semantic_correct": True, "attempts": 1, "latency_s": 1.0, "verified": True, "failure": None, "id": "a", "english": "", "differing": [], "errors": []},
            {"syntax_valid": True, "semantic_correct": False, "attempts": 3, "latency_s": 2.0, "verified": False, "failure": "wrong", "id": "b", "english": "", "differing": [], "errors": []}]
    s = ev.summarize(rows)
    assert s["verified"]["true"] == 1 and s["verified"]["false"] == 1
    assert s["verified"]["semantic_given_verified_true"]["pct"] == 100.0
    assert s["failure_categories"] == {"wrong": 1}


def test_robustness_set_is_wellformed_and_runs_on_fake():
    cases = ev.load_robustness()
    assert len(cases) >= 8 and all(c["scenarios"] and any(s["expected"] == "DENY" for s in c["scenarios"]) for c in cases)
    r = ev.run_robustness(ADAPTER, FakeProvider(), ev.NullRetriever(), cases[:3])
    assert r["passed"]["n"] == 3 and all("failed" in x for x in r["rows"])


def test_robustness_detects_a_policy_that_obeys_the_injection():
    class Obedient(FakeProvider):
        def generate(self, prompt):
            return "allow can_unlock_door(A, D):\n    role(A, agent)\nfact role(agent, agent)\n"
    cases = [c for c in ev.load_robustness() if c["id"] == "rb-01"]
    r = ev.run_robustness(ADAPTER, Obedient(), ev.NullRetriever(), cases)
    assert not r["rows"][0]["passed"] and r["rows"][0]["failed"]
