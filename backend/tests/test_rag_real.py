"""Retrieval with real-embedding behaviour: document vs query tasks, index invalidation, sources."""
from app.llm.fake import FakeProvider
from app.rag.examples import load_examples, load_retrieval_examples
from app.rag.retriever import Retriever


class TaskProvider(FakeProvider):
    """Behaves like a retrieval embedding model: it accepts a task and records every call."""
    supports_embed_task = True

    def __init__(self, model="embed-a"):
        super().__init__()
        self.embed_model, self.calls = model, []

    def embed(self, texts, task=None):
        self.calls.append((len(texts), task))
        return super().embed(texts)


def test_documents_are_embedded_as_documents_and_queries_as_queries(tmp_path):
    p = TaskProvider()
    r = Retriever(p, load_examples(), tmp_path / "i.npz")
    r.search("never unlock the door at night", ["unlock_door"], 3)
    assert p.calls[0] == (len(load_examples()), "document")
    assert p.calls[1] == (1, "query")


def test_changing_the_embedding_model_rebuilds_the_index_but_the_same_model_reuses_it(tmp_path):
    path = tmp_path / "i.npz"
    a = TaskProvider("embed-a")
    Retriever(a, load_examples(), path).search("delete files", [], 1)
    assert [c[1] for c in a.calls].count("document") == 1

    a2 = TaskProvider("embed-a")
    Retriever(a2, load_examples(), path).search("delete files", [], 1)
    assert [c[1] for c in a2.calls].count("document") == 0, "same model: the saved index is reused"

    b = TaskProvider("embed-b")
    Retriever(b, load_examples(), path).search("delete files", [], 1)
    assert [c[1] for c in b.calls].count("document") == 1, "different model: vectors are not comparable, so rebuild"


def test_providers_without_task_support_still_work(tmp_path):
    r = Retriever(FakeProvider(), load_examples(), tmp_path / "i.npz")
    assert r.search("delete files", [], 2)


def test_results_carry_the_example_source(tmp_path):
    r = Retriever(FakeProvider(), load_retrieval_examples(), tmp_path / "i.npz")
    sources = {h.source for q in ("delete a file", "Only admins may delete from a database.", "transfer money")
               for h in r.search(q, [], 5)}
    assert "team" in sources and "claude-draft" in sources


def test_the_retrieval_set_is_the_drafts_plus_the_team_groups():
    ids = [e.id for e in load_retrieval_examples()]
    assert len(ids) == len(set(ids)) and len(ids) == len(load_examples()) + 14
    assert {i for i in ids if i.startswith("team-")} >= {"team-a", "team-r", "team-mnopq"}
