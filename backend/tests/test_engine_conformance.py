"""Engine conformance: the 64 gold examples (+30 benchmark golds) run through EVERY available adapter."""
import os

import pytest

from app.api.deps import get_adapter
from app.benchmark.runner import load_benchmark
from app.engine.adapter import EngineAdapter
from app.engine.c_engine import CEngineAdapter, CEngineUnavailable
from app.engine.python_prototype import PythonPrototypeAdapter
from app.rag.examples import load_examples

ADAPTERS = [("python", PythonPrototypeAdapter)]
if CEngineAdapter.available():
    ADAPTERS.append(("c", CEngineAdapter))
elif os.environ.get("YOG_REQUIRE_C") == "1":      # CI: a missing C engine must fail loudly, never skip silently
    raise RuntimeError("YOG_REQUIRE_C=1 but the C engine (yogc) is not available")
CASES = load_examples() + load_benchmark()


@pytest.mark.parametrize("name,cls", ADAPTERS, ids=[a[0] for a in ADAPTERS])
def test_every_gold_scenario_on_every_adapter(name, cls):
    adapter: EngineAdapter = cls()
    n = 0
    for ex in CASES:
        assert adapter.validate(ex.gold_yog) == [], ex.id
        for s in ex.scenarios:
            r = adapter.check(ex.gold_yog, s.actor, s.action, s.resource, s.context)
            assert r.decision == s.expected, (name, ex.id, s)
            assert r.reason and isinstance(r.trace, list)
            n += 1
    assert n >= 250


def test_adapters_agree_on_error_behaviour():
    a = PythonPrototypeAdapter()
    assert a.validate("allow x(:") and a.validate("allow can_x(U, R):\n    nope(U)\n")


def test_default_engine_is_python(monkeypatch):
    monkeypatch.delenv("YOG_ENGINE", raising=False)
    get_adapter.cache_clear()
    assert isinstance(get_adapter(), PythonPrototypeAdapter)


def test_selecting_c_without_a_binary_is_an_error_not_a_silent_fallback(monkeypatch):
    monkeypatch.setenv("YOG_ENGINE", "c")
    monkeypatch.setenv("YOG_YOGC", "/nonexistent/yogc")
    get_adapter.cache_clear()
    with pytest.raises(CEngineUnavailable):
        get_adapter()


def test_unknown_engine_name_rejected(monkeypatch):
    monkeypatch.setenv("YOG_ENGINE", "rust")
    get_adapter.cache_clear()
    with pytest.raises(RuntimeError, match="unknown YOG_ENGINE"):
        get_adapter()


@pytest.mark.skipif(not CEngineAdapter.available(), reason="needs the C engine")
def test_c_and_python_agree_on_decision_and_reason_for_every_gold_scenario():
    c, p = CEngineAdapter(), PythonPrototypeAdapter()
    n = 0
    for ex in CASES:
        reqs = [(s.actor, s.action, s.resource, s.context) for s in ex.scenarios]
        for s, got in zip(ex.scenarios, c.check_many(ex.gold_yog, reqs)):
            want = p.check(ex.gold_yog, s.actor, s.action, s.resource, s.context)
            assert (got.decision, got.reason) == (want.decision, want.reason), (ex.id, s)
            n += 1
    assert n >= 250


@pytest.mark.skipif(not CEngineAdapter.available(), reason="needs the C engine")
def test_the_landing_page_cross_engine_figures_match_the_corpus():
    """The landing page quotes these counts; this keeps them true (update LandingPage.tsx if the corpus grows)."""
    from app.core.config import REPO_ROOT
    page = (REPO_ROOT / "frontend" / "src" / "pages" / "LandingPage.tsx").read_text(encoding="utf-8")
    scenarios = sum(len(ex.scenarios) for ex in CASES)
    assert f"'{scenarios} / {scenarios}'" in page, f"landing page should say {scenarios} / {scenarios}"
    assert f"['{len(CASES)}', 'gold policies compiled by both engines']" in page, len(CASES)


def test_landing_compiler_figures_were_measured_at_the_vendored_engine_commit():
    """The landing page quotes the engine's own test counts (66 tests, 30,886 checks, 25/25). They were measured at one
    commit with scripts/c_engine_report.py; if engine/c_front is re-vendored, re-run it and update LandingPage.tsx."""
    import re
    from app.core.config import REPO_ROOT
    page = (REPO_ROOT / "frontend" / "src" / "pages" / "LandingPage.tsx").read_text(encoding="utf-8")
    version = (REPO_ROOT / "engine" / "c_front" / "VERSION").read_text(encoding="utf-8")
    pinned = re.search(r"^commit:\s*([0-9a-f]{40})", version, re.M).group(1)
    measured = re.search(r"const MEASURED_AT = '([0-9a-f]{7,40})'", page).group(1)
    assert pinned.startswith(measured), f"page figures measured at {measured}, vendored engine is {pinned[:7]}: re-measure"
    for figure in ("['66', 'tests across", "['30,886', 'checks inside", "['25 / 25', 'queries of the team"):
        assert figure in page, figure
