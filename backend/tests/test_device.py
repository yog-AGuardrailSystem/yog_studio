import pytest
from fastapi.testclient import TestClient

from app.api.policies import get_store
from app.main import app
from app.policies.store import PolicyStore
from app.rag.examples import load_examples

EX = {e.id: e for e in load_examples()}

# Combined demo policy: the two rules from CLAUDE.md section 12 plus the valve cap.
DEMO_POLICY = """fact role(agent, assistant)
fact hour(placeholder, 0)
fact arg(placeholder, placeholder, 0)
allow can_unlock_door(Actor, Door):
    role(Actor, assistant)
allow can_lock_door(Actor, Door):
    role(Actor, assistant)
allow can_set_thermostat(Actor, Zone):
    role(Actor, assistant)
    arg(set_thermostat, temperature, T)
    T >= 16
    T <= 28
allow can_open_valve(Actor, Valve):
    role(Actor, assistant)
deny can_unlock_door(Actor, Door):
    hour(now, H)
    H >= 23
deny can_unlock_door(Actor, Door):
    hour(now, H)
    H < 6
deny can_open_valve(Actor, Valve):
    arg(open_valve, percent, P)
    P > 50
"""


@pytest.fixture()
def api(tmp_path):
    store = PolicyStore(tmp_path / "p")
    app.dependency_overrides[get_store] = lambda: store
    c = TestClient(app)
    yield c, store
    app.dependency_overrides.clear()


def cmd(c, tool, **args):
    return c.post("/device/command", json={"tool": tool, "args": args})


def test_refuses_to_run_without_approved_policy(api):
    c, _ = api
    r = cmd(c, "unlock_door", door_id="front_door")
    assert r.status_code == 409 and "approve" in r.json()["detail"]
    assert c.post("/device/demo", json={}).status_code == 409
    assert c.get("/device/state").json()["state"]["doors"]["front_door"] == "locked"


def test_unlock_at_3am_is_denied_and_door_stays_locked(api):
    c, store = api
    store.save(DEMO_POLICY)
    c.post("/device/clock", json={"hour": 3, "day": "tue"})
    r = cmd(c, "unlock_door", door_id="front_door").json()
    assert r["decision"] == "DENY" and r["executed"] is False and "BLOCKED" in r["message"]
    assert "deny clause" in r["reason"] and "hour(now, 3)" in r["facts"]
    assert c.get("/device/state").json()["state"]["doors"]["front_door"] == "locked"


def test_unlock_in_afternoon_is_allowed_and_door_unlocks(api):
    c, store = api
    store.save(DEMO_POLICY)
    c.post("/device/clock", json={"hour": 14, "day": "mon"})
    r = cmd(c, "unlock_door", door_id="Front Door").json()                  # normalised to front_door
    assert r["decision"] == "ALLOW" and r["executed"]
    assert c.get("/device/state").json()["state"]["doors"]["front_door"] == "unlocked"


@pytest.mark.parametrize("hour,expected", [(22, "ALLOW"), (23, "DENY"), (0, "DENY"), (5, "DENY"), (6, "ALLOW")])
def test_unlock_boundaries(api, hour, expected):
    c, store = api
    store.save(DEMO_POLICY)
    c.post("/device/clock", json={"hour": hour, "day": "mon"})
    assert cmd(c, "unlock_door", door_id="front_door").json()["decision"] == expected


def test_thermostat_range_with_float_normalisation(api):
    c, store = api
    store.save(DEMO_POLICY)
    assert cmd(c, "set_thermostat", zone="living_room", temperature=21.5).json()["decision"] == "ALLOW"
    assert c.get("/device/state").json()["state"]["thermostats"]["living_room"] == 22
    r = cmd(c, "set_thermostat", zone="living_room", temperature=35).json()
    assert r["decision"] == "DENY"
    assert c.get("/device/state").json()["state"]["thermostats"]["living_room"] == 22       # unchanged


def test_valve_cap(api):
    c, store = api
    store.save(DEMO_POLICY)
    assert cmd(c, "open_valve", valve_id="garden_tap", percent=50).json()["decision"] == "ALLOW"
    assert cmd(c, "open_valve", valve_id="garden_tap", percent=80).json()["decision"] == "DENY"
    assert c.get("/device/state").json()["state"]["valves"]["garden_tap"] == 50


def test_tool_with_no_rule_is_default_denied(api):
    c, store = api
    store.save(DEMO_POLICY)
    r = cmd(c, "get_status", device_id="front_door").json()
    assert r["decision"] == "DENY" and "no allow/deny clause" in r["reason"]


def test_guard_off_shows_what_would_have_happened(api):
    c, store = api
    store.save(DEMO_POLICY)
    c.post("/device/clock", json={"hour": 3, "day": "tue"})
    r = c.post("/device/command", json={"tool": "unlock_door", "args": {"door_id": "front_door"}, "guard": False}).json()
    assert r["decision"] == "UNGUARDED" and r["executed"]
    assert c.get("/device/state").json()["state"]["doors"]["front_door"] == "unlocked"


def test_guard_off_works_without_policy(api):
    c, _ = api
    r = c.post("/device/command", json={"tool": "lock_door", "args": {"door_id": "front_door"}, "guard": False})
    assert r.status_code == 200


def test_demo_script_includes_blocked_3am_unlock(api):
    c, store = api
    store.save(DEMO_POLICY)
    snap = c.post("/device/demo", json={}).json()
    log = snap["log"]
    assert len(log) == 7 and snap["policy_id"]
    by = {(e["sim_hour"], e["tool"], e["args"].get("door_id")): e for e in log}
    assert by[(3, "unlock_door", "front_door")]["decision"] == "DENY"
    assert by[(14, "unlock_door", "front_door")]["decision"] == "ALLOW"
    assert by[(23, "unlock_door", "back_door")]["decision"] == "DENY"
    assert snap["state"]["doors"]["back_door"] == "locked"
    assert [e["decision"] for e in log].count("DENY") == 4
    unguarded = c.post("/device/demo", json={"guard": False}).json()
    assert all(e["decision"] == "UNGUARDED" for e in unguarded["log"]) and unguarded["state"]["doors"]["back_door"] == "unlocked"


def test_uses_latest_approved_policy_or_explicit_id(api):
    c, store = api
    old = store.save("fact role(agent, assistant)\nallow can_lock_door(A, D):\n    role(A, assistant)\n")
    c.post("/device/reset")
    assert cmd(c, "lock_door", door_id="front_door").json()["decision"] == "ALLOW"
    deny_all = store.save("fact role(x, y)\nallow can_lock_door(A, D):\n    role(A, y)\n")
    assert cmd(c, "lock_door", door_id="front_door").json()["decision"] == "DENY"          # latest wins
    r = c.post("/device/command", json={"tool": "lock_door", "args": {"door_id": "front_door"}, "policy_id": old.id})
    assert r.json()["decision"] == "ALLOW" and deny_all.id != old.id


@pytest.mark.parametrize("tool,args,msg", [
    ("launch_missile", {}, "unknown tool"), ("unlock_door", {}, "needs argument"),
    ("unlock_door", {"door_id": "moon_door"}, "unknown door"), ("set_thermostat", {"zone": "nowhere", "temperature": 20}, "unknown zone"),
    ("set_thermostat", {"zone": "bedroom", "temperature": "hot"}, "must be a number"), ("open_valve", {"valve_id": "x"}, "unknown valve")])
def test_bad_commands_are_422_and_change_nothing(api, tool, args, msg):
    c, store = api
    store.save(DEMO_POLICY)
    r = cmd(c, tool, **args)
    assert r.status_code == 422 and msg in r.json()["detail"]
    assert c.get("/device/state").json()["log"] == []


def test_clock_validation_and_reset(api):
    c, store = api
    assert c.post("/device/clock", json={"hour": 24, "day": "mon"}).status_code == 422
    assert c.post("/device/clock", json={"hour": 5, "day": "someday"}).status_code == 422
    store.save(DEMO_POLICY)
    cmd(c, "lock_door", door_id="front_door")
    snap = c.post("/device/reset").json()
    assert snap["log"] == [] and snap["clock"] == {"hour": 14, "day": "mon"}


def test_gold_night_lock_policy_also_blocks_3am(api):
    c, store = api
    store.save(EX["sh-night-lock"].gold_yog)
    c.post("/device/clock", json={"hour": 3, "day": "mon"})
    assert cmd(c, "unlock_door", door_id="front_door").json()["decision"] == "DENY"
