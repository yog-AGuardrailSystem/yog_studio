from fastapi.testclient import TestClient

from app.main import app

client = TestClient(app)


def test_list_and_get():
    names = client.get("/samples/agents").json()
    assert "smart_home_mcp.py" in names and len(names) >= 6
    r = client.get("/samples/agents/smart_home_mcp.py")
    assert r.status_code == 200 and "FastMCP" in r.json()["source"]


def test_unknown_and_traversal_404():
    assert client.get("/samples/agents/nope.py").status_code == 404
    assert client.get("/samples/agents/..%2F..%2FCLAUDE.md").status_code == 404
