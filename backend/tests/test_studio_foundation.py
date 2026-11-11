"""Foundation: which policy a tool uses, the check budget, the call -> request mapping, and the device log bound."""
import pytest
from fastapi import HTTPException

from app.api.device import get_sim
from app.core import facts
from app.device.simulator import MAX_LOG, DeviceSim
from app.policies.store import PolicyStore
from app.studio.common import (DEMO_ID, Budget, BudgetExceeded, PolicyRef, boundary_values, call_request, require_valid,
                               resolve_policy, safe_check, shape)
from tests.studio_helpers import DEMO, adapter, approve, client


def test_resolve_demo_and_pasted(tmp_path):
    store = PolicyStore(tmp_path)
    d = resolve_policy(PolicyRef(policy_id=DEMO_ID), store)
    assert d.source == DEMO and not d.approved and d.policy_id == DEMO_ID
    p = resolve_policy(PolicyRef(source="fact a(b)\n"), store)
    assert p.source == "fact a(b)\n" and not p.approved and p.policy_id is None


def test_resolve_pasted_beats_id(tmp_path):
    store = PolicyStore(tmp_path)
    assert resolve_policy(PolicyRef(policy_id=DEMO_ID, source="fact x(y)\n"), store).label == "pasted policy"


def test_resolve_latest_approved_and_missing(tmp_path):
    store = PolicyStore(tmp_path)
    with pytest.raises(HTTPException) as e:
        resolve_policy(PolicyRef(), store)
    assert e.value.status_code == 409
    rec = store.save(DEMO)
    got = resolve_policy(PolicyRef(), store)
    assert got.approved and got.policy_id == rec.id and got.source == DEMO
    with pytest.raises(HTTPException) as e2:
        resolve_policy(PolicyRef(policy_id="p-20200101000000-deadbeef"), store)
    assert e2.value.status_code == 404
    with pytest.raises(HTTPException) as e3:
        resolve_policy(PolicyRef(policy_id="../../etc/passwd"), store)          # not a valid id: refused, not read
    assert e3.value.status_code == 404


def test_require_valid_reports_compile_errors():
    require_valid(adapter(), DEMO)
    with pytest.raises(HTTPException) as e:
        require_valid(adapter(), "allow nonsense(\n")
    assert e.value.status_code == 422 and "does not compile" in e.value.detail


def test_budget_caps_work():
    b = Budget(3)
    b.spend(2)
    b.spend(1)
    with pytest.raises(BudgetExceeded):
        b.spend(1)


def test_safe_check_never_raises_on_bad_context():
    r = safe_check(adapter(), DEMO, "agent", "can_unlock_door", "front_door", ["this is not a fact"])
    assert r.decision == "DENY" and "could not evaluate" in r.reason


def test_call_request_matches_the_facts_path():
    actor, action, resource, ctx = call_request("Unlock Door", {"door_id": "Front Door", "pin": 12}, 3, "Tue")
    assert (actor, action, resource) == ("agent", "can_unlock_door", "front_door")
    assert ctx == facts.facts_from_call("Unlock Door", {"door_id": "Front Door", "pin": 12}, 3, "Tue")


def test_shape_of_the_demo_policy():
    a = adapter()
    sh = shape(a.program_info(DEMO))
    assert sh.actions == ["can_get_status", "can_lock_door", "can_open_valve", "can_set_thermostat", "can_unlock_door"]
    assert sh.actors == ["agent"] and sh.uses_hour and not sh.uses_day
    assert {6, 16, 23, 28, 50} <= set(sh.constants)
    assert ("set_thermostat", "temperature") in sh.arg_keys and ("open_valve", "percent") in sh.arg_keys
    assert all(k[0] != "placeholder" for k in sh.arg_keys)


def test_boundary_values_surround_each_constant_and_are_capped():
    assert boundary_values([16, 28]) == [0, 15, 16, 17, 27, 28, 29]
    assert len(boundary_values(list(range(1, 200)), limit=10)) == 10
    assert boundary_values([]) == [0]


def test_device_log_is_bounded_and_numbering_keeps_counting():
    sim = DeviceSim()
    a = adapter()
    for _ in range(MAX_LOG + 25):
        sim.command("get_status", {"device_id": "front_door"}, a, DEMO, guard=False)
    assert len(sim.log) == MAX_LOG
    assert sim.log[-1].n == MAX_LOG + 25 and sim.log[0].n == 26          # numbers never repeat after trimming
    sim.reset()
    assert sim.log == []
    sim.command("get_status", {"device_id": "front_door"}, a, DEMO, guard=False)
    assert sim.log[0].n == 1


def test_device_api_log_does_not_grow_without_bound():
    get_sim.cache_clear()
    c = client()
    approve(c)
    for _ in range(5):
        assert c.post("/device/command", json={"tool": "get_status", "args": {"device_id": "front_door"}}).status_code == 200
    assert len(c.get("/device/state").json()["log"]) == 5
