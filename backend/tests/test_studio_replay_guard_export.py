"""Trace Replay, the Runtime Guard hardening, the Export Pack and the Scorecard."""
import hashlib
import io
import json
import os
import subprocess
import sys
import zipfile
from pathlib import Path

import pytest

from app.core.config import ENGINE_PATH
from app.studio import pack, replay, scorecard
from app.studio.common import Budget, policy_sha256
from tests.studio_helpers import AGENTS, DEMO, DEMO_TOOLS, adapter, approve, client

A = adapter()
RUNTIME = Path(__file__).resolve().parents[1] / "app" / "modify" / "yog_runtime.py"
SAMPLE = (Path(__file__).resolve().parents[2] / "examples" / "traces" / "smart_home_day.jsonl").read_text(encoding="utf-8")


# ----------------------------------------------------------------------------- replay: parsing
def test_parse_jsonl_with_defaults_and_audit_style_keys():
    rows, problems = replay.parse_rows('{"tool": "a"}\n\n{"tool": "b", "args": {"x": 1}, "sim_hour": 5, "sim_day": "SAT", "actor": "bob"}\n', "jsonl")
    assert problems == [] and (rows[0].hour, rows[0].day, rows[0].actor) == (12, "mon", "agent")
    assert (rows[1].hour, rows[1].day, rows[1].actor, rows[1].args) == (5, "sat", "bob", {"x": 1})


def test_parse_reports_each_bad_row_and_keeps_the_good_ones():
    text = '{"tool": "ok"}\nnot json\n[1,2]\n{"tool": ""}\n{"tool": "x", "hour": 30}\n{"tool": "x", "day": "funday"}\n{"tool": "x", "args": [1]}\n'
    rows, problems = replay.parse_rows(text, "jsonl")
    assert [r.tool for r in rows] == ["ok"] and len(problems) == 6
    assert any("line 2" in p for p in problems) and any("hour must be 0-23" in p for p in problems)


def test_parse_csv_with_json_args_and_arg_columns():
    text = 'tool,hour,day,args,arg_percent\nopen_valve,10,mon,"{""valve_id"": ""garden_tap""}",40\nlock_door,22,tue,,\n'
    rows, problems = replay.parse_rows(text, "csv")
    assert problems == [] and rows[0].args == {"valve_id": "garden_tap", "percent": 40} and rows[1].args == {}


def test_parse_row_cap():
    rows, problems = replay.parse_rows("\n".join('{"tool": "t"}' for _ in range(replay.MAX_ROWS + 5)), "jsonl")
    assert len(rows) == replay.MAX_ROWS and any("only the first" in p for p in problems)


# ----------------------------------------------------------------------------- replay: deciding
def run_rows(text, other=None):
    rows, _ = replay.parse_rows(text, "jsonl")
    return replay.replay(A, DEMO, other, rows, Budget())


def test_sample_trace_is_decided_by_the_policy():
    out, s = run_rows(SAMPLE)
    by = {(r.tool, r.hour, r.day): r.decision for r in out}
    assert s.total == 12 and s.allowed + s.denied == 12
    assert by[("unlock_door", 3, "tue")] == "DENY" and by[("unlock_door", 8, "mon")] == "ALLOW"
    assert by[("set_thermostat", 9, "mon")] == "DENY" and by[("format_disk", 14, "wed")] == "DENY"    # 31 C; and a tool with no rule


def test_comparing_two_policies_marks_the_calls_that_change():
    stricter = DEMO.replace("H < 6", "H < 8")                          # the night now lasts until 08:00
    out, s = run_rows(SAMPLE, stricter)
    changed = [r for r in out if r.changed]
    assert s.changed == len(changed) == 1
    assert (changed[0].tool, changed[0].hour, changed[0].decision, changed[0].other) == ("unlock_door", 7, "ALLOW", "DENY")
    assert s.other_allowed == s.allowed - len(changed)


def test_replay_never_executes_anything_and_survives_odd_args():
    out, _ = run_rows('{"tool": "__import__(\'os\').system(\'x\')", "args": {"a": {"b": [1, 2]}, "c": null, "d": true, "e": 2.7}}')
    assert out[0].decision == "DENY"


def test_replay_api_formats_limits_and_audit():
    c = client()
    j = c.post("/studio/replay", json={"policy": {"policy_id": "demo"}, "text": SAMPLE, "format": "jsonl"}).json()
    assert j["summary"]["total"] == 12 and j["policy_label"].startswith("demo") and j["other_label"] is None
    assert c.post("/studio/replay", json={"policy": {"policy_id": "demo"}, "text": "", "format": "jsonl"}).status_code == 422
    assert c.post("/studio/replay", json={"policy": {"policy_id": "demo"}, "text": "x" * 200_001}).status_code == 422
    assert c.post("/studio/replay", json={"policy": {"policy_id": "demo"}, "format": "audit"}).status_code == 422     # nothing recorded yet
    approve(c)
    c.post("/device/command", json={"tool": "unlock_door", "args": {"door_id": "front_door"}})
    a = c.post("/studio/replay", json={"policy": {"policy_id": "demo"}, "format": "audit"}).json()
    assert a["summary"]["total"] == 1 and a["rows"][0]["tool"] == "unlock_door"
    s = c.get("/studio/replay/sample").json()
    assert s["filename"].endswith(".jsonl") and "unlock_door" in s["text"]


def test_replay_api_compare_between_versions():
    c = client()
    a = approve(c)
    b = approve(c, DEMO.replace("H < 6", "H < 8"))
    j = c.post("/studio/replay", json={"policy": {"policy_id": a["id"]}, "compare": {"policy_id": b["id"]}, "text": SAMPLE, "format": "jsonl"}).json()
    assert j["other_label"].startswith("approved") and j["summary"]["changed"] >= 1 and any(r["changed"] for r in j["rows"])


# ----------------------------------------------------------------------------- runtime guard
@pytest.fixture()
def bundle(tmp_path):
    (tmp_path / "yog.py").write_text(ENGINE_PATH.read_text(encoding="utf-8"), encoding="utf-8")
    (tmp_path / "yog_runtime.py").write_text(RUNTIME.read_text(encoding="utf-8"), encoding="utf-8")
    (tmp_path / "policy.yog").write_bytes(DEMO.encode("utf-8"))              # bytes: write_text would turn \n into \r\n on Windows
    return tmp_path


def run_py(d: Path, code: str, **env):
    e = {**os.environ, **env}
    e.pop("PYTHONPATH", None)
    p = subprocess.run([sys.executable, "-I", "-c", f"import sys; sys.path.insert(0, {str(d)!r})\n" + code],
                       capture_output=True, text=True, cwd=d, env=e, timeout=60)
    return p.returncode, p.stdout.strip(), p.stderr.strip()


CALL = 'import yog_runtime as r\nprint(r.check("unlock_door", {"door_id": "front_door"})["decision"])\n'


def test_pin_matches_the_approved_file_and_blocks_a_changed_one(bundle):
    pin = hashlib.sha256(DEMO.encode()).hexdigest()
    assert run_py(bundle, CALL, YOG_NOW="14,mon", YOG_POLICY_SHA256=pin)[1] == "ALLOW"
    (bundle / "policy.yog").write_bytes(DEMO.replace("H >= 23", "H >= 99").encode())                 # edited after approval
    code, out, err = run_py(bundle, CALL, YOG_NOW="14,mon", YOG_POLICY_SHA256=pin)
    assert code == 0 and out == "DENY"
    code, out, _ = run_py(bundle, 'import yog_runtime as r\nprint(r.check("unlock_door", {"door_id": "x"})["reason"])\n', YOG_NOW="14,mon", YOG_POLICY_SHA256=pin)
    assert "YOG_POLICY_SHA256" in out
    assert run_py(bundle, CALL, YOG_NOW="14,mon")[1] == "ALLOW"                                      # no pin set: runs as before


def test_policy_sha256_helper(bundle):
    code, out, _ = run_py(bundle, "import yog_runtime as r\nprint(r.policy_sha256())\n")
    assert out == hashlib.sha256(DEMO.encode()).hexdigest() == policy_sha256(DEMO)


def test_regression_pin_survives_windows_line_endings_but_not_other_edits(bundle):
    """An editor or git re-saving policy.yog with CRLF must not lock the agent out; a real edit still must."""
    pin = policy_sha256(DEMO)
    (bundle / "policy.yog").write_bytes(DEMO.replace("\n", "\r\n").encode())
    assert run_py(bundle, CALL, YOG_NOW="14,mon", YOG_POLICY_SHA256=pin)[1] == "ALLOW"
    assert policy_sha256(DEMO.replace("\n", "\r\n")) == pin
    (bundle / "policy.yog").write_bytes((DEMO + "\n# one more line\n").replace("\n", "\r\n").encode())
    assert run_py(bundle, CALL, YOG_NOW="14,mon", YOG_POLICY_SHA256=pin)[1] == "DENY"


def test_decision_log_records_normalised_values_not_raw_ones(bundle):
    log = bundle / "decisions.jsonl"
    code = ('import yog_runtime as r\nr.check("unlock_door", {"door_id": "Front Door", "pin": "s3cret-PIN"})\n'
            'r.check("set_thermostat", {"zone": "bedroom", "temperature": 35})\n')
    assert run_py(bundle, code, YOG_NOW="14,mon", YOG_LOG=str(log))[0] == 0
    rows = [json.loads(x) for x in log.read_text().splitlines()]
    assert [r["decision"] for r in rows] == ["ALLOW", "DENY"] and rows[0]["args"]["door_id"] == "front_door"
    assert rows[1]["args"]["temperature"] == 35 and rows[0]["hour"] == 14 and rows[0]["day"] == "mon"
    assert rows[0]["args"]["pin"] == "s3cret_pin"                    # kept only in the normalised form the policy saw


def test_unwritable_log_never_changes_a_decision(bundle):
    out = run_py(bundle, CALL, YOG_NOW="14,mon", YOG_LOG=str(bundle / "no" / "such" / "dir" / "x.jsonl"))
    assert out[0] == 0 and out[1] == "ALLOW"


def test_concurrent_decisions_never_see_each_others_facts(bundle):
    code = '''
import threading
import yog_runtime as r
bad = []
def worker(i):
    for _ in range(60):
        night = (i % 2 == 0)
        # the clock is process-wide, so pin it per call through the environment-free API: facts come from args instead
        res = r.check("set_thermostat", {"zone": "z", "temperature": 35 if night else 20})
        want = "DENY" if night else "ALLOW"
        if res["decision"] != want:
            bad.append((i, res["decision"]))
ts = [threading.Thread(target=worker, args=(i,)) for i in range(8)]
[t.start() for t in ts]; [t.join() for t in ts]
print("BAD", len(bad))
'''
    out = run_py(bundle, code, YOG_NOW="14,mon")
    assert out[0] == 0 and out[1] == "BAD 0", out


def test_selftest_passes_on_a_good_bundle_and_fails_on_a_broken_one(bundle):
    code, out, _ = run_py_file(bundle, ["--selftest"])
    assert code == 0 and "selftest passed" in out and "unknown tool is denied: ok" in out
    (bundle / "policy.yog").write_text("allow nonsense(\n", encoding="utf-8")
    code, out, _ = run_py_file(bundle, ["--selftest"])
    assert code == 1 and "FAIL" in out and "selftest FAILED" in out


def run_py_file(d: Path, args: list[str]):
    e = {k: v for k, v in os.environ.items() if k != "PYTHONPATH"}
    p = subprocess.run([sys.executable, "-I", str(d / "yog_runtime.py"), *args], capture_output=True, text=True, cwd=d, env=e, timeout=60)
    return p.returncode, p.stdout.strip(), p.stderr.strip()


def test_sdk_endpoints():
    c = client()
    s = c.get("/studio/sdk/runtime").json()
    assert s["filename"] == "yog_runtime.py" and "def yog_guard" in s["source"] and s["lines"] > 100
    j = c.post("/studio/sdk/try", json={"policy_id": "demo", "tool": "unlock_door", "args": {"door_id": "Front Door"}, "hour": 3, "day": "TUE"}).json()
    assert j["decision"] == "DENY" and j["resource"] == "front_door" and "hour(now, 3)" in j["context"]
    assert j["policy_sha256"] == hashlib.sha256(DEMO.encode()).hexdigest()
    assert c.post("/studio/sdk/try", json={"policy_id": "demo", "tool": "unlock_door", "day": "funday"}).status_code == 422
    assert c.post("/studio/sdk/try", json={"policy_id": "demo", "tool": "unlock_door", "hour": 24}).status_code == 422


def test_sdk_try_matches_what_the_real_guard_answers(bundle):
    c = client()
    for tool, args, hour in (("unlock_door", {"door_id": "front_door"}, 3), ("unlock_door", {"door_id": "front_door"}, 14),
                             ("set_thermostat", {"zone": "bedroom", "temperature": 35}, 14), ("open_valve", {"valve_id": "garden_tap", "percent": 30}, 14)):
        api = c.post("/studio/sdk/try", json={"policy_id": "demo", "tool": tool, "args": args, "hour": hour, "day": "mon"}).json()["decision"]
        code, out, _ = run_py(bundle, f'import yog_runtime as r\nprint(r.check({tool!r}, {args!r})["decision"])\n', YOG_NOW=f"{hour},mon")
        assert out == api, (tool, hour)


# ----------------------------------------------------------------------------- export pack
def test_pack_contents_and_manifest_hashes():
    c = client()
    rec = approve(c, note="v1")
    r = c.post("/studio/export", json={"policy_id": rec["id"], "source": (AGENTS / "smart_home_mcp.py").read_text(encoding="utf-8"), "filename": "smart_home_mcp.py"})
    assert r.status_code == 200 and r.headers["content-type"] == "application/zip"
    z = zipfile.ZipFile(io.BytesIO(r.content))
    assert sorted(z.namelist()) == ["README.txt", "REPORT.html", "manifest.json", "policy.yog", "scenarios.json", "smart_home_mcp.py", "yog.py", "yog_runtime.py"]
    m = json.loads(z.read("manifest.json"))
    assert m["policy_id"] == rec["id"] and m["policy_sha256"] == hashlib.sha256(DEMO.encode()).hexdigest()
    for name, info in m["files"].items():
        data = z.read(name)
        assert hashlib.sha256(data).hexdigest() == info["sha256"] and len(data) == info["bytes"]
    assert "manifest.json" not in m["files"]
    assert z.read("policy.yog").decode() == DEMO
    assert f"YOG_POLICY_SHA256={m['policy_sha256']}" in z.read("README.txt").decode()
    assert "@yog_guard(" in z.read("smart_home_mcp.py").decode()


def test_policy_only_pack_has_no_agent_files():
    c = client()
    rec = approve(c)
    z = zipfile.ZipFile(io.BytesIO(c.post("/studio/export", json={"policy_id": rec["id"]}).content))
    assert sorted(z.namelist()) == ["REPORT.html", "manifest.json", "policy.yog", "scenarios.json"]


def test_report_is_self_contained_and_escapes_everything():
    c = client()
    evil = DEMO + "# <script>alert(1)</script>\n"
    rec = approve(c, evil, english_rules=["<img src=x onerror=alert(1)> never at night"], note="<b>note</b>")
    html = zipfile.ZipFile(io.BytesIO(c.post("/studio/export", json={"policy_id": rec["id"]}).content)).read("REPORT.html").decode()
    assert "<script>" not in html and "<img" not in html and "&lt;script&gt;" in html and "&lt;img" in html and "&lt;b&gt;note&lt;/b&gt;" in html
    assert "http://" not in html and "https://" not in html and "<link" not in html                  # nothing external
    assert "Scorecard" in html and "The rules, in English" in html and "approved by a person" in html


def test_export_refuses_demo_unknown_and_placeholder_and_bad_agent():
    c = client()
    assert c.post("/studio/export", json={"policy_id": "demo"}).status_code == 409
    assert c.post("/studio/export", json={"policy_id": "p-20200101000000-deadbeef"}).status_code == 404
    ph = approve(c, DEMO + "# OFFLINE FAKE PROVIDER: copied from the nearest example\n")
    r = c.post("/studio/export", json={"policy_id": ph["id"]})
    assert r.status_code == 409 and "placeholder" in r.json()["detail"]
    ok = approve(c)
    assert c.post("/studio/export", json={"policy_id": ok["id"], "source": "def broken(:\n"}).status_code == 422
    assert c.post("/studio/export", json={"policy_id": ok["id"], "source": (AGENTS / "not_an_agent.py").read_text(encoding="utf-8")}).status_code == 422


def test_export_is_per_visitor_and_preview_matches():
    c1, c2 = client(), client()
    rec = approve(c1)
    assert c2.post("/studio/export", json={"policy_id": rec["id"]}).status_code == 404
    p = c1.post("/studio/export/preview", json={"policy_id": rec["id"], "source": "x = 1", "filename": "a.py"}).json()
    assert p["ok"] and p["files"] == ["policy.yog", "REPORT.html", "scenarios.json", "manifest.json", "a.py", "yog_runtime.py", "yog.py", "README.txt"]
    assert c1.post("/studio/export/preview", json={"policy_id": "demo"}).json()["ok"] is False


def test_pack_build_raises_value_error_for_placeholder():
    rec = type("R", (), {"yog_source": DEMO + "# OFFLINE FAKE PROVIDER\n", "id": "p", "approved_at": "t", "note": "", "english_rules": []})()
    with pytest.raises(ValueError):
        pack.build(A, rec)


# ----------------------------------------------------------------------------- scorecard
def test_scorecard_metrics_and_honest_gaps():
    sc = scorecard.compute(A, DEMO, DEMO_TOOLS)
    m = {x.id: x for x in sc.metrics}
    assert list(m) == ["tools", "scenarios", "clauses", "gaps", "redteam", "strength"]
    assert m["tools"].value == "5 of 5" and m["tools"].status == "good"
    assert m["scenarios"].status == "todo" and m["scenarios"].value is None            # no independent scenarios: says so
    assert m["clauses"].value == "100%" and m["gaps"].value == "0" and m["strength"].status in ("good", "warn")
    assert m["redteam"].status == "warn" and int(m["redteam"].value) > 0
    assert "not measured" in sc.headline and all(x.link.startswith("/") for x in sc.metrics)


def test_scorecard_without_tools_or_strength_marks_them_not_measured():
    sc = scorecard.compute(A, DEMO, None, include_strength=False)
    m = {x.id: x for x in sc.metrics}
    assert m["tools"].status == "todo" and m["strength"].status == "todo" and m["strength"].value is None


def test_scorecard_flags_proved_problems():
    bad = "fact role(a, r)\nfact hour(placeholder, 0)\nallow can_x(U, R):\n    role(U, r)\ndeny can_x(U, R):\n    role(U, r)\n"
    m = {x.id: x for x in scorecard.compute(A, bad, ["x"]).metrics}
    assert m["gaps"].status == "bad" and int(m["gaps"].value) >= 1


def test_scorecard_api():
    c = client()
    j = c.post("/studio/scorecard", json={"policy_id": "demo", "tools": DEMO_TOOLS, "include_strength": False}).json()
    assert j["policy_label"].startswith("demo") and len(j["metrics"]) == 6
    assert c.post("/studio/scorecard", json={"tools": ["x"]}).status_code == 409                    # nothing approved, nothing pasted
