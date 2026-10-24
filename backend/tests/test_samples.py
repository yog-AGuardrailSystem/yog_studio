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


def test_demo_policy_compiles_and_blocks_3am_unlock():
    from app.engine.python_prototype import PythonPrototypeAdapter
    j = client.get("/samples/demo-policy").json()
    a = PythonPrototypeAdapter()
    assert a.validate(j["yog_source"]) == [] and len(j["english_rules"]) == 3 and "not LLM" in j["note"]
    unlock = lambda h: a.check(j["yog_source"], "agent", "can_unlock_door", "front_door", [f"hour(now, {h})"]).decision
    assert (unlock(3), unlock(23), unlock(14)) == ("DENY", "DENY", "ALLOW")
    thermo = lambda t: a.check(j["yog_source"], "agent", "can_set_thermostat", "hall", [f"arg(set_thermostat, temperature, {t})"]).decision
    assert (thermo(15), thermo(16), thermo(28), thermo(29)) == ("DENY", "ALLOW", "ALLOW", "DENY")
