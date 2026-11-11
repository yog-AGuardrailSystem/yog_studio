"""Integration: one visitor goes through the whole Studio path over HTTP, using only what the previous step produced.
Upload -> approve -> map -> why -> gaps -> red-team -> test strength -> new version -> diff -> restore -> device ->
audit -> replay -> scorecard -> export. Each step checks the others agree (the map, the explainer, the guard and the
device must give the same answer for the same request)."""
import hashlib
import io
import json
import subprocess
import sys
import os
import zipfile

from tests.studio_helpers import AGENTS, DEMO, client

AGENT = (AGENTS / "smart_home_mcp.py").read_text(encoding="utf-8")


def test_the_whole_path():
    c = client()

    # 1. upload an agent: framework-aware analysis, tools found
    a = c.post("/analyze", json={"filename": "smart_home_mcp.py", "source": AGENT}).json()
    tools = [t["name"] for t in a["tools"]]
    assert a["detect"]["kind"] == "mcp_server" and set(tools) == {"unlock_door", "lock_door", "set_thermostat", "open_valve", "get_status"}

    # 2. approve the demo policy through the normal gate (server re-validates and evaluates)
    p1 = c.post("/policies/approve", json={"yog_source": DEMO, "english_rules": ["never unlock 11pm-6am"], "note": "v1"}).json()

    # 3. every tool now works on "latest approved" with no id given
    m = c.post("/studio/map", json={"action": "can_unlock_door", "x": {"kind": "hour"}}).json()
    assert m["policy_label"] == f"approved {p1['id']}" and "".join(m["cells"][0]) == "DDDDDD" + "A" * 17 + "D"

    # 4. the explainer agrees with every cell of the map it came from
    for hour in (0, 5, 6, 14, 22, 23):
        w = c.post("/studio/why", json={"actor": "agent", "action": "can_unlock_door", "resource": "front_door", "context": [f"hour(now, {hour})"]}).json()
        assert w["consistent"] and w["result"]["decision"][0] == m["cells"][0][hour]

    # 5. gaps with the uploaded tools: fully covered, no proved problems
    g = c.post("/studio/gaps", json={"tools": tools}).json()
    assert g["coverage_pct"] == 100.0 and not [f for f in g["findings"] if f["certainty"] == "proved" and f["severity"] == "warning"]

    # 6. red-team: the stated promise holds; a counterexample is saved and fed to test strength
    rt = c.post("/studio/redteam", json={"invariants": [{"action": "can_unlock_door", "must": "DENY", "hour_min": 23, "hour_max": 5}]}).json()
    assert rt["counterexamples"] == 0
    keep = {"actor": "agent", "action": "can_unlock_door", "resource": "front_door", "context": ["hour(now, 2)"], "expected": "DENY"}
    ok = {**keep, "context": ["hour(now, 12)"], "expected": "ALLOW"}
    ts = c.post("/studio/mutation", json={"scenarios": [keep, ok]}).json()
    assert ts["tests_source"] == "yours" and ts["tests_used"] == 2 and ts["survived"] >= 1                    # two tests miss most edits

    # 7. a stricter version: diff shows the one request that flips, restore brings the old one back as a new version
    p2 = c.post("/policies/approve", json={"yog_source": DEMO.replace("H < 6", "H < 8"), "english_rules": ["until 8"], "note": "until 8am"}).json()
    d = c.post("/studio/versions/diff", json={"a": p1["id"], "b": p2["id"]}).json()
    assert d["changed_actions"] == ["can_unlock_door"] and any(any("hour(now, 7)" in x for x in f["context"]) for f in d["flips"])
    rest = c.post("/studio/versions/restore", json={"policy_id": p1["id"]}).json()
    assert rest["yog_source"] == DEMO and rest["parent_id"] == p2["id"]
    assert [v["note"] for v in c.get("/studio/versions").json()][1:] == ["until 8am", "v1"]

    # 8. the device obeys the latest (restored) policy; the audit log records each decision with a valid chain
    c.post("/device/clock", json={"hour": 3, "day": "tue"})
    assert c.post("/device/command", json={"tool": "unlock_door", "args": {"door_id": "front_door"}}).json()["decision"] == "DENY"
    c.post("/device/clock", json={"hour": 7, "day": "tue"})
    assert c.post("/device/command", json={"tool": "unlock_door", "args": {"door_id": "front_door"}}).json()["decision"] == "ALLOW"    # restored: 7am is fine
    au = c.get("/studio/audit").json()
    assert au["total"] == 2 and all(e["policy_id"] == rest["id"] for e in au["entries"]) and c.get("/studio/audit/verify").json()["ok"]

    # 9. replay what the device saw against the stricter version: the 7am unlock would have been blocked
    rp = c.post("/studio/replay", json={"policy": {"policy_id": rest["id"]}, "compare": {"policy_id": p2["id"]}, "format": "audit"}).json()
    assert rp["summary"]["total"] == 2 and rp["summary"]["changed"] == 1
    assert [(r["hour"], r["decision"], r["other"]) for r in rp["rows"] if r["changed"]] == [(7, "ALLOW", "DENY")]

    # 10. scorecard on the restored policy
    sc = c.post("/studio/scorecard", json={"policy_id": rest["id"], "tools": tools, "include_strength": False}).json()
    assert {m["id"]: m["status"] for m in sc["metrics"]}["tools"] == "good"

    # 11. export: the pack's pin, the zip's policy and the policy the device used are the same text
    z = c.post("/studio/export", json={"policy_id": rest["id"], "source": AGENT, "filename": "smart_home_mcp.py", "tools": tools})
    assert z.status_code == 200
    zf = zipfile.ZipFile(io.BytesIO(z.content))
    man = json.loads(zf.read("manifest.json"))
    assert zf.read("policy.yog").decode() == DEMO and man["policy_sha256"] == hashlib.sha256(DEMO.encode()).hexdigest()

    # 12. the unzipped bundle really enforces the policy: run the patched agent's guard from the pack
    import tempfile
    with tempfile.TemporaryDirectory() as d_:
        zf.extractall(d_)
        env = {**os.environ, "YOG_POLICY_SHA256": man["policy_sha256"], "YOG_NOW": "3,tue"}
        env.pop("PYTHONPATH", None)
        code = ('import yog_runtime as r\nprint(r.check("unlock_door", {"door_id": "front_door"})["decision"], '
                'r.check("get_status", {"device_id": "front_door"})["decision"])\n')
        out = subprocess.run([sys.executable, "-I", "-c", f"import sys; sys.path.insert(0, {d_!r})\n" + code], capture_output=True, text=True, env=env, cwd=d_, timeout=60)
        assert out.stdout.strip() == "DENY ALLOW", out.stderr
        st = subprocess.run([sys.executable, "-I", os.path.join(d_, "yog_runtime.py"), "--selftest"], capture_output=True, text=True, env=env, cwd=d_, timeout=60)
        assert st.returncode == 0 and "selftest passed" in st.stdout


def test_a_second_visitor_sees_none_of_it():
    a, b = client(), client()
    p = a.post("/policies/approve", json={"yog_source": DEMO, "english_rules": ["x"]}).json()
    a.post("/device/command", json={"tool": "get_status", "args": {"device_id": "front_door"}})
    assert b.get("/studio/versions").json() == [] and b.get("/studio/audit").json()["total"] == 0
    assert b.post("/studio/map", json={"action": "can_unlock_door", "x": {"kind": "hour"}}).status_code == 409        # nothing approved for b
    assert b.post("/studio/export", json={"policy_id": p["id"]}).status_code == 404
    assert b.post("/studio/replay", json={"policy": {"policy_id": p["id"]}, "format": "audit"}).status_code == 404
    # ...but the demo policy is the same for everyone
    assert b.post("/studio/map", json={"policy_id": "demo", "action": "can_unlock_door", "x": {"kind": "hour"}}).status_code == 200


def test_every_tool_endpoint_rejects_a_policy_that_does_not_compile():
    c = client()
    bad = {"source": "allow broken(\n"}
    for path, extra in (("/studio/why", {"actor": "a", "action": "can_x", "resource": "r"}), ("/studio/map/suggest", {}),
                        ("/studio/map", {"action": "can_x", "x": {"kind": "hour"}}), ("/studio/gaps", {}), ("/studio/redteam", {}),
                        ("/studio/mutation", {}), ("/studio/scorecard", {}), ("/studio/sdk/try", {"tool": "t"})):
        r = c.post(path, json={**bad, **extra})
        assert r.status_code == 422 and "does not compile" in r.json()["detail"], path


def test_oversized_pasted_policy_is_refused_everywhere():
    c = client()
    big = "fact a(b)\n" * 30_000
    for path in ("/studio/gaps", "/studio/redteam", "/studio/mutation", "/studio/scorecard"):
        assert c.post(path, json={"source": big}).status_code == 422, path
