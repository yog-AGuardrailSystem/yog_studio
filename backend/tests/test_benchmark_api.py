import json

from fastapi.testclient import TestClient

from app.api import benchmark as b
from app.main import app

client = TestClient(app)


def test_no_real_results_gives_nulls_and_a_note(tmp_path, monkeypatch):
    monkeypatch.setattr(b, "RESULTS_DIR", tmp_path)
    r = client.get("/benchmark/latest").json()
    assert r["evaluation"] is None and r["retrieval"] is None and "No real benchmark" in r["note"]


def test_fake_results_are_never_served(tmp_path, monkeypatch):
    monkeypatch.setattr(b, "RESULTS_DIR", tmp_path)
    (tmp_path / "eval-dev-fake-1.json").write_text(json.dumps({"provider": "fake"}))
    (tmp_path / "eval-dev-gemini-2.json").write_text(json.dumps({"provider": "gemini", "when": "x"}))
    assert [x["file"] for x in client.get("/benchmark/list").json()] == ["eval-dev-gemini-2.json"]
    assert client.get("/benchmark/latest").json()["evaluation"]["provider"] == "gemini"
    assert client.get("/benchmark/file/eval-dev-fake-1.json").status_code == 404
    assert client.get("/benchmark/file/..%2Fx").status_code == 404
