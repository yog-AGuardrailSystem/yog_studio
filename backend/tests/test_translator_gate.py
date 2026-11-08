"""The semantic gate: independent scenarios check each compiling draft; disagreements are fed back for repair.
Plus the attempt log, retrieved examples with scores, progress events, cancellation and the job API."""
import json
import threading
import time

import pytest
from fastapi.testclient import TestClient

from app.api.deps import get_adapter, get_llm
from app.api.retrieve import get_retriever
from app.api.translate import get_jobs
from app.core.models import Tool
from app.engine.python_prototype import PythonPrototypeAdapter
from app.llm.fake import FakeProvider
from app.llm.provider import LLMError
from app.main import app
from app.rag.examples import load_retrieval_examples
from app.rag.retriever import Retriever
from app.translate.jobs import JobStore
from app.translate.translator import TranslateCancelled, translate

adapter = PythonPrototypeAdapter()
RULE = "The agent may never unlock the door between 11pm and 6am."
TOOLS = [Tool(name="unlock_door", source_line=1)]

GOOD = """fact role(agent, assistant)
fact hour(placeholder, 0)
allow can_unlock_door(Actor, Door):
    role(Actor, assistant)
deny can_unlock_door(Actor, Door):
    hour(now, H)
    H >= 23
deny can_unlock_door(Actor, Door):
    hour(now, H)
    H < 6
"""
BAD = """fact role(agent, assistant)
allow can_unlock_door(Actor, Door):
    role(Actor, assistant)
"""
SCENARIOS = json.dumps({"scenarios": [
    {"actor": "agent", "action": "can_unlock_door", "resource": "front_door", "context": ["hour(now, 3)"],
     "expected": "DENY", "note": "3am"},
    {"actor": "agent", "action": "can_unlock_door", "resource": "front_door", "context": ["hour(now, 14)"],
     "expected": "ALLOW", "note": "2pm"},
]})


def fence(policy):
    return f"```yog\n{policy}```"


class Scripted(FakeProvider):
    """Returns queued replies in order and records every prompt."""
    supports_json_schema = True

    def __init__(self, replies):
        super().__init__()
        self.replies, self.prompts, self.schemas = list(replies), [], []

    def generate(self, prompt, system=None, *, json_schema=None):
        self.prompts.append(prompt)
        self.schemas.append(json_schema)
        reply = self.replies.pop(0)
        if isinstance(reply, Exception):
            raise reply
        return reply


@pytest.fixture
def retriever(tmp_path):
    return Retriever(FakeProvider(), load_retrieval_examples(), tmp_path / "idx.npz")


def run(replies, retriever, **kw):
    p = Scripted(replies)
    return translate([RULE], TOOLS, p, retriever, adapter, **kw), p


# ------------------------------------------------------------------ the gate
def test_without_verify_there_is_no_scenario_call_and_verified_is_unknown(retriever):
    d, p = run([fence(GOOD)], retriever)
    assert d.valid and d.verified is None and d.scenario_summary is None and len(p.prompts) == 1


def test_a_correct_draft_passes_the_independent_check(retriever):
    d, p = run([SCENARIOS, fence(GOOD)], retriever, verify=True)
    assert d.valid and d.verified is True and d.attempts == 1
    assert (d.scenario_summary.total, d.scenario_summary.passed) == (2, 2)
    assert p.schemas[0] is not None and p.schemas[1] is None, "only the scenario call asks for structured JSON"


def test_a_draft_that_compiles_but_contradicts_the_english_is_repaired(retriever):
    d, p = run([SCENARIOS, fence(BAD), fence(GOOD)], retriever, verify=True)
    assert d.valid and d.verified is True and d.attempts == 2
    first, second = d.attempt_log
    assert first.compiled and first.errors == [] and len(first.scenario_failures) == 1
    assert "expected DENY but the policy gives ALLOW" in first.scenario_failures[0] and "hour(now, 3)" in first.scenario_failures[0]
    assert second.compiled and second.scenario_failures == []
    repair_prompt = p.prompts[2]
    assert "check:" in repair_prompt and "expected DENY" in repair_prompt
    assert "can be wrong" in repair_prompt, "the model is warned that the independent check may itself be mistaken"


def test_when_the_disagreement_never_resolves_the_best_draft_is_returned_unverified(retriever):
    d, _ = run([SCENARIOS, fence(BAD), fence(BAD), fence(BAD)], retriever, verify=True)
    assert d.valid is True, "it compiles: valid means compiles"
    assert d.verified is False and d.attempts == 3
    assert d.scenario_summary.failures and d.scenario_summary.passed == 1 and d.scenario_summary.total == 2
    assert d.yog_source.strip() == BAD.strip()


def test_the_least_wrong_attempt_wins(retriever):
    # still wrong (a deny that can never fire) and it does compile, because hour/2 is declared
    worse = "fact hour(placeholder, 0)\n" + BAD + "deny can_unlock_door(Actor, Door):\n    hour(now, H)\n    H > 99\n"
    # attempt 1: wrong (1 failure). attempt 2: does not compile. attempt 3: wrong again with a no-op deny
    d, _ = run([SCENARIOS, fence(BAD), "```yog\nallow nonsense\n```", fence(worse)], retriever, verify=True)
    assert d.verified is False and d.valid is True
    assert d.yog_source.strip() == BAD.strip(), "attempt 1 had no more failures than attempt 3, so it is kept"
    assert [a.compiled for a in d.attempt_log] == [True, False, True]


def test_noisy_scenarios_that_cannot_run_are_skipped_not_counted(retriever):
    noisy = json.dumps({"scenarios": [
        {"actor": "agent", "action": "can_unlock_door", "resource": "d", "context": ["this is not a fact"], "expected": "DENY"},
        {"actor": "agent", "action": "can_unlock_door", "resource": "d", "context": ["hour(now, 14)"], "expected": "ALLOW"},
    ]})
    d, _ = run([noisy, fence(GOOD)], retriever, verify=True)
    assert d.verified is True and d.scenario_summary.total == 1


def test_if_every_scenario_is_noise_nothing_is_claimed(retriever):
    allnoise = json.dumps({"scenarios": [
        {"actor": "agent", "action": "can_unlock_door", "resource": "d", "context": ["junk"], "expected": "DENY"}]})
    d, _ = run([allnoise, fence(GOOD)], retriever, verify=True)
    assert d.valid and d.verified is None and d.scenario_summary is None


def test_if_scenarios_cannot_be_generated_the_draft_still_works(retriever):
    d, _ = run([LLMError("quota"), fence(GOOD)], retriever, verify=True)
    assert d.valid and d.verified is None


def test_compile_errors_are_logged_per_attempt_and_repaired(retriever):
    d, p = run([fence("allow can_unlock_door(Actor, Door)\n    role(Actor)\n"), fence(GOOD)], retriever)
    assert d.valid and d.attempts == 2
    assert d.attempt_log[0].compiled is False and d.attempt_log[0].errors
    assert d.attempt_log[1].compiled is True
    assert "colon" in p.prompts[1] or "expected" in p.prompts[1]


def test_an_llm_failure_mid_loop_is_logged_and_reported(retriever):
    d, _ = run([fence(BAD.replace("allow", "alow")), LLMError("quota exceeded")], retriever)
    assert not d.valid and d.attempts == 2 and "quota exceeded" in d.errors[0]
    assert d.attempt_log[-1].errors == d.errors


def test_the_retrieved_examples_are_the_ones_in_the_prompt_with_scores_and_sources(retriever):
    d, p = run([fence(GOOD)], retriever)
    assert d.retrieved and [r.id for r in d.retrieved] == d.retrieved_examples
    assert all(0 <= r.score <= 1.0001 for r in d.retrieved)
    assert all(r.id in p.prompts[0] or r.english in p.prompts[0] for r in d.retrieved)
    sources = {r.source for r in d.retrieved}
    assert sources <= {"team", "claude-draft", "unknown"} or all(s for s in sources)


def test_team_examples_are_retrievable(retriever):
    hits = retriever.search("Only admins may delete from a database.", [], 3)
    assert hits[0].id == "team-a" and hits[0].source == "team"
    assert "can_delete" in hits[0].gold_yog and "query" not in hits[0].gold_yog


# ------------------------------------------------------------------ progress events and cancellation
def test_events_describe_every_phase(retriever):
    events = []
    run([SCENARIOS, fence(BAD), fence(GOOD)], retriever, verify=True, on_event=events.append)
    phases = [(e["phase"], e.get("state") or e.get("n")) for e in events]
    assert phases[0] == ("retrieving", None) and phases[1][0] == "retrieved"
    assert ("scenarios", "generating") in phases and ("scenarios", "ready") in phases
    assert ("attempt", "generating") in [(e["phase"], e.get("state")) for e in events]
    checked = [e for e in events if e["phase"] == "attempt" and e.get("state") == "checked"]
    assert len(checked) == 2 and checked[0]["scenario_failures"] and not checked[1]["scenario_failures"]
    assert events[-1] == {"phase": "done", "valid": True, "verified": True}
    assert events[1]["examples"][0]["id"]


def test_cancel_stops_before_the_next_llm_call(retriever):
    p = Scripted([fence(GOOD)])
    calls = {"n": 0}

    def should_cancel():
        calls["n"] += 1
        return calls["n"] > 1                    # allow retrieval, cancel before the first generation
    with pytest.raises(TranslateCancelled):
        translate([RULE], TOOLS, p, retriever, adapter, should_cancel=should_cancel)
    assert p.prompts == []


# ------------------------------------------------------------------ the job API
@pytest.fixture
def api(retriever):
    jobs = JobStore()
    state = {"provider": Scripted([SCENARIOS, fence(BAD), fence(GOOD)])}
    app.dependency_overrides[get_llm] = lambda: state["provider"]
    app.dependency_overrides[get_retriever] = lambda: retriever
    app.dependency_overrides[get_adapter] = lambda: adapter
    app.dependency_overrides[get_jobs] = lambda: jobs
    yield TestClient(app), state
    app.dependency_overrides.clear()


def wait_done(client, job_id, timeout=10):
    end = time.time() + timeout
    while time.time() < end:
        v = client.get(f"/translate/{job_id}").json()
        if v["status"] != "running":
            return v
        time.sleep(0.02)
    raise AssertionError("job did not finish")


BODY = {"english_rules": [RULE], "tools": [t.model_dump() for t in TOOLS]}


def test_job_flow_gives_live_events_then_the_result(api):
    client, state = api
    state["provider"].name = "scripted"                     # a "real" provider: verification switches on by itself
    jid = client.post("/translate/start", json=BODY).json()["job_id"]
    v = wait_done(client, jid)
    assert v["status"] == "done" and v["result"]["verified"] is True and v["result"]["attempts"] == 2
    phases = [e["phase"] for e in v["events"]]
    assert phases[0] == "retrieving" and phases[-1] == "done" and "attempt" in phases
    again = client.get(f"/translate/{jid}", params={"since": v["next"]}).json()
    assert again["events"] == [] and again["status"] == "done"
    partial = client.get(f"/translate/{jid}", params={"since": 2}).json()
    assert partial["events"][0]["i"] == 2


def test_verification_is_automatic_for_real_providers_and_off_for_the_fake(api):
    client, state = api
    fake = client.post("/translate", json=BODY)                   # the default offline provider path
    assert fake.status_code == 200
    state["provider"] = Scripted([fence(GOOD)])
    state["provider"].name = "fake"
    j = client.post("/translate", json=BODY).json()
    assert j["verified"] is None and j["valid"] is True


def test_explicit_verify_overrides_the_automatic_choice(api):
    client, state = api
    state["provider"] = Scripted([SCENARIOS, fence(GOOD)])
    state["provider"].name = "fake"
    j = client.post("/translate", json={**BODY, "verify": True}).json()
    assert j["verified"] is True


def test_cancelling_a_running_job(api):
    client, state = api
    gate, entered = threading.Event(), threading.Event()

    class Slow(Scripted):
        def generate(self, prompt, system=None, *, json_schema=None):
            entered.set()
            gate.wait(5)
            return super().generate(prompt, system, json_schema=json_schema)
    state["provider"] = Slow([fence(GOOD), fence(GOOD)])
    jid = client.post("/translate/start", json={**BODY, "verify": False}).json()["job_id"]
    assert entered.wait(5)
    assert client.post(f"/translate/{jid}/cancel").json() == {"cancelled": True}
    gate.set()
    # the call in flight finishes, then the job stops before using it: here it already had its only attempt
    v = wait_done(client, jid)
    assert v["status"] in ("cancelled", "done")


def test_unknown_jobs_are_404(api):
    client, _ = api
    assert client.get("/translate/nope").status_code == 404
    assert client.post("/translate/nope/cancel").status_code == 404


def test_a_provider_error_becomes_an_error_job_not_a_crash(api):
    client, state = api
    state["provider"] = Scripted([LLMError("boom")])
    jid = client.post("/translate/start", json={**BODY, "verify": False}).json()["job_id"]
    v = wait_done(client, jid)
    assert v["status"] == "done" and v["result"]["valid"] is False and "boom" in v["result"]["errors"][0]


def test_job_store_prunes_old_jobs():
    store = JobStore(max_jobs=3)
    ids = [store.start(lambda emit, c: __import__("app.core.models", fromlist=["PolicyDraft"]).PolicyDraft(
        english_rules=[], yog_source="", retrieved_examples=[], attempts=0, valid=False, errors=[]), blocking=True)
        for _ in range(6)]
    assert store.view(ids[-1]) is not None and store.view(ids[0]) is None
