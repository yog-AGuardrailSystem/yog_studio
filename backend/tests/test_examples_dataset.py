"""The dataset must not silently rot: every gold policy compiles and every scenario matches the engine."""
import pytest

from app.engine.python_prototype import PythonPrototypeAdapter
from app.rag.examples import load_examples

EXAMPLES = load_examples()
adapter = PythonPrototypeAdapter()


def test_at_least_60_examples_with_unique_ids():
    assert len(EXAMPLES) >= 60
    assert len({e.id for e in EXAMPLES}) == len(EXAMPLES)


@pytest.mark.parametrize("ex", EXAMPLES, ids=lambda e: e.id)
def test_gold_compiles(ex):
    assert adapter.validate(ex.gold_yog) == []


@pytest.mark.parametrize("ex", EXAMPLES, ids=lambda e: e.id)
def test_scenarios_match_engine(ex):
    assert ex.scenarios, "every example needs scenarios"
    for s in ex.scenarios:
        r = adapter.check(ex.gold_yog, s.actor, s.action, s.resource, s.context)
        assert r.decision == s.expected, f"{ex.id}: {s.actor} {s.action} {s.resource} {s.context} -> {r.decision} ({r.reason})"


@pytest.mark.parametrize("ex", EXAMPLES, ids=lambda e: e.id)
def test_example_has_both_outcomes_or_is_explained(ex):
    # A policy whose scenarios are all ALLOW (or all DENY) proves little; require a mix.
    assert {s.expected for s in ex.scenarios} == {"ALLOW", "DENY"}, f"{ex.id} scenarios are one-sided"
