from fastapi.testclient import TestClient

from app.main import app

client = TestClient(app)


def test_version_reports_render_commit(monkeypatch):
    monkeypatch.setenv("RENDER_GIT_COMMIT", "abc123")
    assert client.get("/version").json() == {"commit": "abc123"}


def test_version_falls_back_to_git_commit_then_unknown(monkeypatch):
    monkeypatch.delenv("RENDER_GIT_COMMIT", raising=False)
    monkeypatch.setenv("GIT_COMMIT", "def456")
    assert client.get("/version").json() == {"commit": "def456"}
    monkeypatch.delenv("GIT_COMMIT", raising=False)
    assert client.get("/version").json() == {"commit": "unknown"}


def test_health_unchanged():
    assert client.get("/health").json() == {"status": "ok"}
