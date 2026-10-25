from fastapi.testclient import TestClient

from app.main import app
from tests.test_python_adapter import SAMPLE

client = TestClient(app)


def body(**kw):
    base = {"policy": SAMPLE, "actor": "alice", "action": "can_delete", "resource": "db1"}
    return {**base, **kw}


def test_health():
    assert client.get("/health").json() == {"status": "ok"}


def test_allow():
    r = client.post("/check", json=body())
    assert r.status_code == 200
    j = r.json()
    assert j["decision"] == "ALLOW" and set(j) == {"decision", "reason", "trace"}


def test_deny_beats_allow():
    r = client.post("/check", json=body(actor="bob"))
    assert r.status_code == 200 and r.json()["decision"] == "DENY"


def test_bad_policy_422():
    r = client.post("/check", json=body(policy="allow x(:\n"))
    assert r.status_code == 422 and r.json()["detail"]


def test_missing_field_422():
    assert client.post("/check", json={"policy": SAMPLE}).status_code == 422
