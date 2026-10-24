import pytest
from fastapi.testclient import TestClient

from app.api.policies import get_store
from app.engine.python_prototype import PythonPrototypeAdapter
from app.explain.explainer import explain
from app.main import app
from app.policies.store import PolicyStore
from app.rag.examples import load_examples

adapter = PythonPrototypeAdapter()
EXAMPLES = load_examples()
GOOD = next(e for e in EXAMPLES if e.id == "sh-night-lock").gold_yog


@pytest.fixture()
def client(tmp_path):
    store = PolicyStore(tmp_path / "policies")
    app.dependency_overrides[get_store] = lambda: store
    yield TestClient(app), store
    app.dependency_overrides.clear()


# ---------------------------------------------------------------- explainer

@pytest.mark.parametrize("ex", EXAMPLES, ids=lambda e: e.id)
def test_readback_covers_every_clause_and_fact(ex):
    info = adapter.program_info(ex.gold_yog)
    rb = explain(adapter, ex.gold_yog)
    covered_lines = {c.line for c in rb.clauses}
    expected = {c["line"] for c in info["clauses"]} | {f["line"] for f in info["facts"]}
    assert covered_lines == expected
    assert all(c.text.strip() for c in rb.clauses)


def test_readback_content_night_lock():
    rb = explain(adapter, GOOD)
    texts = " ".join(c.text for c in rb.clauses)
    assert "ALLOW" in texts and "DENY" in texts
    assert "the current hour is H" in texts and "H is at least 23" in texts and "H is below 6" in texts
    assert "Actor has the role assistant" in texts
    assert [a.predicate for a in rb.actions] == ["can_unlock_door"]
    act = rb.actions[0]
    assert len(act.allow) == 1 and len(act.deny) == 2
    assert any("DENY wins" in n for n in rb.notes) and any("denied by default" in n for n in rb.notes)
    assert any(i.startswith("hour:") for i in rb.inputs)
    assert not any("placeholder" in f for f in rb.facts)


def test_readback_negation_and_definitions():
    rb = explain(adapter, next(e for e in EXAMPLES if e.id == "db-sensitive-tables").gold_yog)
    assert any("NOT the case" in c.text for c in rb.clauses)
    rb2 = explain(adapter, next(e for e in EXAMPLES if e.id == "fs-system-files-protected").gold_yog)
    assert rb2.definitions and rb2.definitions[0].startswith("Definition:")


def test_explain_invalid_raises():
    from app.engine.adapter import EngineError
    with pytest.raises(EngineError):
        explain(adapter, "allow x(:")


# ---------------------------------------------------------------- API

def test_explain_endpoint_valid_and_invalid(client):
    c, _ = client
    ok = c.post("/explain", json={"yog_source": GOOD}).json()
    assert ok["valid"] and ok["readback"]["clauses"] and ok["errors"] == []
    bad = c.post("/explain", json={"yog_source": "allow can_x(U, R):\n    mystery(U)\n"}).json()
    assert not bad["valid"] and bad["readback"] is None and "mystery" in bad["errors"][0]


def test_approve_persists_exact_text_and_readback(client):
    c, store = client
    r = c.post("/policies/approve", json={"yog_source": GOOD, "english_rules": ["r1"],
                                          "retrieved_examples": ["sh-night-lock"], "attempts": 2})
    assert r.status_code == 200
    rec = r.json()
    assert rec["id"].startswith("p-") and rec["attempts"] == 2 and rec["readback"]
    assert (store.dir / f"{rec['id']}.yog").read_text(encoding="utf-8") == GOOD
    assert c.get(f"/policies/{rec['id']}").json()["yog_source"] == GOOD
    assert [p["id"] for p in c.get("/policies").json()] == [rec["id"]]


def test_invalid_policy_cannot_be_approved(client):
    c, store = client
    r = c.post("/policies/approve", json={"yog_source": "allow can_x(U, R):\n    mystery(U)\n"})
    assert r.status_code == 422 and "cannot approve" in r.json()["detail"]
    assert store.list() == []


def test_policy_without_decisions_cannot_be_approved(client):
    c, store = client
    r = c.post("/policies/approve", json={"yog_source": "fact role(a, b)\n"})
    assert r.status_code == 422 and store.list() == []


def test_reject_stores_nothing(client):
    c, store = client
    assert c.post("/policies/reject", json={"reason": "wrong"}).json() == {"status": "rejected"}
    assert store.list() == []


def test_edit_then_revalidate_then_approve_edited_text(client):
    c, store = client
    edited = GOOD.replace("H >= 23", "H >= 22")
    assert c.post("/explain", json={"yog_source": edited}).json()["valid"]
    rec = c.post("/policies/approve", json={"yog_source": edited}).json()
    assert "H >= 22" in store.get(rec["id"]).yog_source


def test_get_unknown_and_traversal_404(client):
    c, _ = client
    assert c.get("/policies/p-20200101000000-deadbeef").status_code == 404
    assert c.get("/policies/..%2F..%2Fsecret").status_code == 404
