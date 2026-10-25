import importlib

from fastapi.testclient import TestClient


def make_client(monkeypatch, tmp_path):
    (tmp_path / "assets").mkdir()
    (tmp_path / "index.html").write_text("<html>SPA</html>")
    (tmp_path / "assets" / "app.js").write_text("console.log(1)")
    (tmp_path / "favicon.svg").write_text("<svg/>")
    monkeypatch.setenv("YOG_STATIC_DIR", str(tmp_path))
    import app.asgi as asgi
    importlib.reload(asgi)
    return TestClient(asgi.app)


def test_ui_and_api_from_one_process(monkeypatch, tmp_path):
    c = make_client(monkeypatch, tmp_path)
    assert c.get("/api/health").json() == {"status": "ok"}
    assert "SPA" in c.get("/").text
    assert "SPA" in c.get("/review").text                      # client-side route falls back to index.html
    assert c.get("/assets/app.js").text == "console.log(1)"
    assert c.get("/favicon.svg").text == "<svg/>"
    r = c.post("/api/check", json={"policy": "", "actor": "a", "action": "can_x", "resource": "r"})
    assert r.status_code == 200 and r.json()["decision"] == "DENY"


def test_path_traversal_cannot_leave_static_dir(monkeypatch, tmp_path):
    c = make_client(monkeypatch, tmp_path)
    r = c.get("/..%2F..%2FCLAUDE.md")
    assert "SPA" in r.text or r.status_code == 404
    assert "YOG Studio" not in r.text.split("<html>")[0]
