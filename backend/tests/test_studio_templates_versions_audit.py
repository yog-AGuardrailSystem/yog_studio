"""Templates, Version History and the Audit log."""
import json
import threading

from app.core import config, session
from app.studio import audit as audit_mod
from app.studio import templates
from app.studio.audit import GENESIS, AuditLog, to_csv
from tests.studio_helpers import DEMO, adapter, approve, client

A = adapter()


# ----------------------------------------------------------------------------- templates
def test_every_template_compiles_alone():
    ts = templates.load()
    assert len(ts) >= 60 and len({t.id for t in ts}) == len(ts)
    bad = [t.id for t in ts if A.validate(t.yog)]
    assert bad == []


def test_templates_are_grouped_into_packs_and_drafts_are_labelled():
    ts = templates.load()
    assert {t.pack for t in ts} >= {"database", "files", "finance", "network", "smart_home", "generic"}
    assert all(t.pack_title and "_" not in t.pack_title for t in ts)
    assert any(not t.reviewed for t in ts)                                          # claude-draft ones say so
    assert all(t.reviewed == (not t.source_label.startswith("claude-draft")) for t in ts if t.source_label != "unknown")


def test_combine_keeps_a_repeated_fact_once_and_validates():
    sh = [t for t in templates.load() if t.pack == "smart_home"][:2]
    r = templates.combine(A, [t.id for t in sh])
    assert r.ok and r.errors == [] and r.used == [t.id for t in sh]
    facts = [ln for ln in r.source.split("\n") if ln.startswith("fact ")]
    assert len(facts) == len({" ".join(f.split()) for f in facts})
    assert A.validate(r.source) == []


def test_combine_rejects_unknown_ids_and_bad_counts():
    assert templates.combine(A, ["nope"]).errors == ["unknown template: nope"]
    assert not templates.combine(A, []).ok
    ids = [t.id for t in templates.load()][: templates.MAX_COMBINE + 1]
    assert not templates.combine(A, ids).ok


def test_combine_reports_engine_errors_for_clashing_templates():
    # two templates that define the same decision with different arities would not compile together; at minimum the
    # result's `ok` always mirrors the engine
    ids = [t.id for t in templates.load()][:4]
    r = templates.combine(A, ids)
    assert r.ok == (A.validate(r.source) == [])


def test_templates_api():
    c = client()
    ts = c.get("/studio/templates").json()
    assert len(ts) >= 60 and {"id", "pack", "english", "yog", "reviewed"} <= set(ts[0])
    j = c.post("/studio/templates/combine", json={"ids": [ts[0]["id"], ts[1]["id"]]}).json()
    assert "source" in j and isinstance(j["ok"], bool)
    assert c.post("/studio/templates/combine", json={"ids": ["x"] * 7}).status_code == 422


# ----------------------------------------------------------------------------- versions
def test_approvals_form_a_chain_with_notes():
    c = client()
    first = approve(c, note="first draft")
    second = approve(c, DEMO.replace("H >= 23", "H >= 22"), note="stricter at night")
    assert first["parent_id"] is None and second["parent_id"] == first["id"] and second["note"] == "stricter at night"
    vs = c.get("/studio/versions").json()
    assert [v["id"] for v in vs] == [second["id"], first["id"]] and vs[0]["latest"] and not vs[1]["latest"]
    assert vs[0]["clauses"] >= 8 and vs[0]["rules"] == 1


def test_diff_lists_text_and_the_requests_whose_answer_changed():
    c = client()
    a = approve(c)
    b = approve(c, DEMO.replace("H >= 23", "H >= 22"))
    j = c.post("/studio/versions/diff", json={"a": a["id"], "b": b["id"]}).json()
    assert j["added"] == 1 and j["removed"] == 1 and "H >= 22" in j["text_diff"]
    assert j["flips_total"] >= 1 and j["changed_actions"] == ["can_unlock_door"]
    f = j["flips"][0]
    assert (f["before"], f["after"]) == ("ALLOW", "DENY") and any("hour(now, 22)" in x for x in f["context"])
    same = c.post("/studio/versions/diff", json={"a": a["id"], "b": a["id"]}).json()
    assert same["summary"] == "The two versions have the same text." and same["flips"] == []


def test_diff_with_text_change_but_no_behaviour_change():
    c = client()
    a = approve(c)
    b = approve(c, DEMO + "# a comment changes the text only\n")
    j = c.post("/studio/versions/diff", json={"a": a["id"], "b": b["id"]}).json()
    assert j["added"] == 1 and j["flips_total"] == 0 and "none of the" in j["summary"]


def test_restore_saves_a_new_version_and_never_overwrites():
    c = client()
    a = approve(c)
    b = approve(c, DEMO.replace("H >= 23", "H >= 22"))
    r = c.post("/studio/versions/restore", json={"policy_id": a["id"]})
    assert r.status_code == 200
    new = r.json()
    assert new["id"] not in (a["id"], b["id"]) and new["restored_from"] == a["id"] and new["parent_id"] == b["id"]
    assert new["yog_source"] == a["yog_source"] and new["note"].startswith("restored ")
    ids = [v["id"] for v in c.get("/studio/versions").json()]
    assert set(ids) == {a["id"], b["id"], new["id"]}
    assert c.get(f"/policies/{b['id']}").json()["yog_source"] == b["yog_source"]            # the middle version is untouched


def test_regression_same_text_saved_twice_in_a_second_gets_two_ids(tmp_path):
    """Found while testing Restore: ids are time-to-the-second plus a hash of the text, so saving identical text twice in
    one second used to overwrite the first record (losing its note and parent) and could make a record its own parent."""
    from app.policies.store import PolicyStore
    store = PolicyStore(tmp_path)
    one, two, three = store.save(DEMO, note="one"), store.save(DEMO, note="two"), store.save(DEMO, note="three")
    assert len({one.id, two.id, three.id}) == 3
    assert [store.get(r.id).note for r in (one, two, three)] == ["one", "two", "three"]
    assert store.latest().id == three.id                        # ordering by approval time is preserved


def test_restore_errors_and_session_isolation():
    c1, c2 = client(), client()
    a = approve(c1)
    assert c1.post("/studio/versions/restore", json={"policy_id": "p-20200101000000-deadbeef"}).status_code == 404
    assert c2.get("/studio/versions").json() == []                                    # another visitor sees none of it
    assert c2.post("/studio/versions/restore", json={"policy_id": a["id"]}).status_code == 404
    assert c2.post("/studio/versions/diff", json={"a": a["id"], "b": a["id"]}).status_code == 404


# ----------------------------------------------------------------------------- audit log
def log(tmp_path) -> AuditLog:
    return AuditLog(tmp_path)


def entry(**kw):
    return {"tool": "unlock_door", "args": {"door_id": "front_door"}, "decision": "DENY", "reason": "r", "sim_hour": 3, **kw}


def test_chain_verifies_and_numbers_entries(tmp_path):
    a = log(tmp_path)
    r1, r2 = a.append(entry()), a.append(entry(decision="ALLOW"))
    assert (r1["seq"], r2["seq"]) == (1, 2) and r1["prev"] == GENESIS and r2["prev"] == r1["hash"]
    assert a.verify() == {"ok": True, "checked": 2, "total": 2, "bad_seq": None, "problem": ""}
    assert a.count() == 2 and [e["seq"] for e in a.read()] == [2, 1]                    # newest first


def test_editing_a_line_breaks_the_chain(tmp_path):
    a = log(tmp_path)
    for i in range(4):
        a.append(entry(sim_hour=i))
    lines = a.path.read_text(encoding="utf-8").split("\n")
    rec = json.loads(lines[1])
    rec["decision"] = "ALLOW"                                                              # someone rewrites history
    lines[1] = json.dumps(rec, sort_keys=True)
    a.path.write_text("\n".join(lines), encoding="utf-8")
    v = a.verify()
    assert not v["ok"] and v["bad_seq"] == 2 and "does not match" in v["problem"]


def test_deleting_or_reordering_lines_is_detected(tmp_path):
    a = log(tmp_path)
    for i in range(4):
        a.append(entry(sim_hour=i))
    lines = [ln for ln in a.path.read_text(encoding="utf-8").split("\n") if ln]
    a.path.write_text("\n".join([lines[0], lines[2], lines[3]]) + "\n", encoding="utf-8")        # entry 2 removed
    assert not a.verify()["ok"]
    a.path.write_text("\n".join([lines[0], lines[2], lines[1], lines[3]]) + "\n", encoding="utf-8")
    assert not a.verify()["ok"]


def test_garbage_in_the_file_is_reported_not_raised(tmp_path):
    a = log(tmp_path)
    a.append(entry())
    a.path.write_text(a.path.read_text(encoding="utf-8") + "this is not json\n", encoding="utf-8")
    assert not a.verify()["ok"] and "not valid JSON" in a.verify()["problem"]
    assert len(a.read()) == 1                                                                 # reading skips the broken line


def test_rotation_keeps_the_chain_valid_through_the_anchor(tmp_path, monkeypatch):
    monkeypatch.setattr(audit_mod, "MAX_LINES", 12)
    monkeypatch.setattr(audit_mod, "DROP", 5)
    a = log(tmp_path)
    for i in range(30):
        a.append(entry(sim_hour=i % 24))
    assert a.count() <= 12 and a.verify()["ok"]
    assert json.loads(a.meta.read_text())["anchor"] != GENESIS
    assert a.read(1)[0]["seq"] == 30                                                           # numbering continues


def test_filters_and_limit(tmp_path):
    a = log(tmp_path)
    a.append(entry())
    a.append(entry(decision="ALLOW", tool="lock_door"))
    assert len(a.read(decision="allow")) == 1 and a.read(tool="lock_door")[0]["decision"] == "ALLOW"
    assert len(a.read(q="FRONT_DOOR")) == 2 and a.read(q="zzz") == [] and len(a.read(limit=1)) == 1


def test_csv_neutralises_spreadsheet_formulas(tmp_path):
    a = log(tmp_path)
    a.append(entry(reason="=HYPERLINK(\"http://evil\")", tool="@cmd", args={"x": "+1"}))
    out = to_csv(list(reversed(a.read())))
    header, row = out.strip().split("\n")[:2]
    assert header.startswith("seq,at,sim_day")
    assert "'=HYPERLINK" in out and "'@cmd" in out and ",=HYPERLINK" not in out


def test_concurrent_appends_keep_one_valid_chain(tmp_path):
    a = log(tmp_path)
    threads = [threading.Thread(target=lambda: [a.append(entry()) for _ in range(10)]) for _ in range(6)]
    [t.start() for t in threads]
    [t.join() for t in threads]
    assert a.count() == 60 and a.verify()["ok"] and sorted(e["seq"] for e in a.read(1000)) == list(range(1, 61))


def test_device_commands_are_recorded_per_visitor():
    c1, c2 = client(), client()
    approve(c1)
    c1.post("/device/command", json={"tool": "unlock_door", "args": {"door_id": "front_door"}})
    c1.post("/device/clock", json={"hour": 3, "day": "tue"})
    c1.post("/device/command", json={"tool": "unlock_door", "args": {"door_id": "front_door"}})
    j = c1.get("/studio/audit").json()
    assert j["total"] == 2 and [e["decision"] for e in j["entries"]] == ["DENY", "ALLOW"]
    assert j["entries"][0]["policy_id"].startswith("p-") and j["entries"][0]["sim_hour"] == 3
    assert c1.get("/studio/audit/verify").json()["ok"]
    assert c2.get("/studio/audit").json() == {"entries": [], "total": 0}                       # nobody else's decisions
    assert "text/csv" in c1.get("/studio/audit/export.csv").headers["content-type"]


def test_failed_commands_are_not_recorded_and_unguarded_ones_are():
    c = client()
    approve(c)
    assert c.post("/device/command", json={"tool": "nope", "args": {}}).status_code == 422
    c.post("/device/command", json={"tool": "get_status", "args": {"device_id": "front_door"}, "guard": False})
    e = c.get("/studio/audit").json()["entries"]
    assert len(e) == 1 and e[0]["decision"] == "UNGUARDED" and e[0]["guarded"] is False


def test_demo_day_fills_the_log_and_filters_work_over_http():
    c = client()
    approve(c)
    assert c.post("/device/demo", json={}).status_code == 200
    total = c.get("/studio/audit").json()["total"]
    assert total == 7
    deny = c.get("/studio/audit", params={"decision": "DENY"}).json()["entries"]
    assert deny and all(e["decision"] == "DENY" for e in deny)
    assert c.get("/studio/audit", params={"limit": 0}).status_code == 422
    assert c.get("/studio/audit", params={"q": "x" * 200}).status_code == 422


def test_audit_files_live_in_the_visitors_own_session_folder():
    c = client()
    approve(c)
    c.post("/device/command", json={"tool": "get_status", "args": {"device_id": "front_door"}})
    sid = c.cookies.get(session.COOKIE)
    assert (config.DATA_DIR / "sessions" / sid / "audit.jsonl").exists()
