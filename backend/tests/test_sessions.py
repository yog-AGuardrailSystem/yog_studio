"""Visitors must never see or drive each other's policies and devices (public deployment)."""
import time

import pytest
from fastapi.testclient import TestClient

from app.core import config, session
from app.main import app
from app.rag.examples import load_retrieval_examples

POLICY = next(e for e in load_retrieval_examples() if e.id == "sh-night-lock").gold_yog


def approve(c: TestClient, **extra):
    return c.post("/policies/approve", json={"yog_source": POLICY, "english_rules": ["never at night"], **extra})


def approve_distinct(c: TestClient, n: int):
    return approve(c, yog_source=POLICY + f"# variant {n}\n")        # ids derive from the text: identical text would overwrite


@pytest.fixture()
def a():
    return TestClient(app)


@pytest.fixture()
def b():
    return TestClient(app)


def test_policies_are_private_to_each_visitor(a, b):
    rec = approve(a).json()
    assert [p["id"] for p in a.get("/policies").json()] == [rec["id"]]
    assert b.get("/policies").json() == []
    assert b.get(f"/policies/{rec['id']}").status_code == 404           # even knowing the id
    assert a.get(f"/policies/{rec['id']}").status_code == 200


def test_a_visitor_keeps_their_policies_across_requests(a):
    first = approve(a).json()["id"]
    assert a.get("/policies").json()[0]["id"] == first
    assert a.get("/policies").json()[0]["id"] == first


def test_the_device_only_obeys_the_visitors_own_policy(a, b):
    approve(a)
    assert a.get("/device/state").json()["policy_id"] is not None
    assert b.get("/device/state").json()["policy_id"] is None            # b has approved nothing
    refused = b.post("/device/command", json={"tool": "unlock_door", "args": {"door_id": "front"}, "guard": True})
    assert refused.status_code == 409 and "approve" in refused.json()["detail"]


def test_each_visitor_has_their_own_device(a, b):
    a.post("/device/clock", json={"hour": 3, "day": "mon"})
    assert a.get("/device/state").json()["clock"]["hour"] == 3
    assert b.get("/device/state").json()["clock"]["hour"] != 3


def test_the_session_cookie_is_httponly_lax_and_set_once(a):
    r = a.get("/health")
    cookie = r.headers["set-cookie"].lower()
    assert "yog_sid=" in cookie and "httponly" in cookie and "samesite=lax" in cookie and "secure" not in cookie
    assert "set-cookie" not in a.get("/health").headers                    # not reissued while valid


def test_the_cookie_is_secure_over_https():
    c = TestClient(app, base_url="https://testserver")
    assert "secure" in c.get("/health").headers["set-cookie"].lower()
    c2 = TestClient(app)
    assert "secure" in c2.get("/health", headers={"x-forwarded-proto": "https"}).headers["set-cookie"].lower()


@pytest.mark.parametrize("bad", ["../../etc", "x" * 32, "", "0" * 31, "G" * 32, "a" * 33])
def test_a_forged_cookie_is_replaced_not_trusted(bad):
    c = TestClient(app)
    r = c.get("/health", headers={"cookie": f"yog_sid={bad}"})
    new = r.headers["set-cookie"].split(";")[0].split("=", 1)[1]
    assert session.valid(new) and new != bad


def test_session_directories_cannot_escape_the_data_folder():
    with pytest.raises(ValueError):
        session.session_dir("../../etc")
    assert session.session_dir("a" * 32).parent == config.DATA_DIR / "sessions"


def test_a_visitor_cannot_use_another_visitors_session_without_the_cookie(a, b):
    approve(a)
    sid_a = a.cookies.get("yog_sid")
    assert b.get("/policies").json() == []
    stolen = TestClient(app).get("/policies", headers={"cookie": f"yog_sid={sid_a}"})   # holding the cookie IS the capability
    assert len(stolen.json()) == 1


def test_expired_sessions_are_deleted_and_fresh_ones_kept(a):
    approve(a)
    fresh = session.session_dir(a.cookies.get("yog_sid"))
    old = session.session_dir(session.new_sid())
    (old / "policies").mkdir(parents=True)
    (old / "policies" / "p.txt").write_text("x")
    long_ago = time.time() - 30 * 86400
    import os
    for path in (old / "policies" / "p.txt", old / "policies", old):
        os.utime(path, (long_ago, long_ago))
    assert session.cleanup_sessions(max_age_days=7) == 1
    assert fresh.exists() and not old.exists()


def test_cleanup_runs_at_most_once_an_hour(monkeypatch):
    monkeypatch.setattr(session, "_last_cleanup", 0.0)
    calls = []
    monkeypatch.setattr(session, "cleanup_sessions", lambda now=None: calls.append(now) or 0)
    session.maybe_cleanup(now=10_000.0)
    session.maybe_cleanup(now=10_100.0)
    session.maybe_cleanup(now=10_000.0 + 3601)
    assert len(calls) == 2


def test_there_is_a_cap_on_policies_per_session(a, monkeypatch):
    monkeypatch.setenv("MAX_POLICIES_PER_SESSION", "2")
    assert [approve_distinct(a, i).status_code for i in range(3)] == [200, 200, 409]
    b = TestClient(app)
    assert approve(b).status_code == 200                                    # the cap is per visitor


def test_unreadable_cleanup_target_does_not_crash(tmp_path, monkeypatch):
    monkeypatch.setattr(config, "DATA_DIR", tmp_path)
    (tmp_path / "sessions").mkdir()
    (tmp_path / "sessions" / "not-a-session").mkdir()                     # never deleted: not one of ours
    (tmp_path / "sessions" / "afile").write_text("x")
    assert session.cleanup_sessions(max_age_days=0) == 0
    assert (tmp_path / "sessions" / "not-a-session").exists()
