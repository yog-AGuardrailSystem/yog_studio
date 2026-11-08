import shutil

import yaml

from app.benchmark import review as rv
from app.engine.python_prototype import PythonPrototypeAdapter

A = PythonPrototypeAdapter()


def _copy_bench(tmp_path):
    f = tmp_path / "rules.yaml"
    shutil.copy(rv.BENCH_FILE, f)
    return f


def test_assign_is_exhaustive_and_balanced():
    out = rv.assign(list(range(10)), ["a", "b", "c"])
    assert sorted(sum(out.values(), [])) == list(range(10))
    assert max(map(len, out.values())) - min(map(len, out.values())) <= 1


def test_sheet_roundtrip_and_parse():
    items = rv.drafted_items([rv.BENCH_FILE])[:2]
    sheet = rv.render_sheet(A, "Varun", items)
    assert items[0][1].id in sheet and "Readback" in sheet
    filled = sheet.replace("
VERDICT: 
", "
VERDICT: ok
", 1)
    assert rv.parse_sheet(filled) == {items[0][1].id: {"verdict": "ok", "revised": None}}
    assert rv.parse_sheet(sheet) == {}, "an unanswered sheet changes nothing"


def test_ok_flips_source_and_keeps_file_valid(tmp_path):
    f = _copy_bench(tmp_path)
    n = len(yaml.safe_load(f.read_text(encoding="utf-8")))
    ex = rv.drafted_items([f])[0][1]
    rep = rv.apply(A, {"Varun": f"## {ex.id}\nVERDICT: ok\n"}, [f])
    assert rep["accepted"] == [ex.id]
    data = yaml.safe_load(f.read_text(encoding="utf-8"))
    assert len(data) == n and {x["id"]: x["source"] for x in data}[ex.id] == "reviewed-by:Varun"


def test_broken_revision_is_refused_and_source_unchanged(tmp_path):
    f = _copy_bench(tmp_path)
    ex = rv.drafted_items([f])[0][1]
    sheet = f"## {ex.id}\nVERDICT: ok\nREVISED_YOG:\n```yog\nallow can_x(A, B) role(\n```\n"
    rep = rv.apply(A, {"Viz": sheet}, [f])
    assert rep["refused"] and not rep["accepted"]
    assert ex.id in {e.id for _, e in rv.drafted_items([f])}


def test_revision_that_fails_item_scenarios_is_refused(tmp_path):
    f = _copy_bench(tmp_path)
    ex = rv.drafted_items([f])[0][1]
    sheet = f"## {ex.id}\nVERDICT: ok\nREVISED_YOG:\n```yog\nfact role(agent, assistant)\n```\n"
    assert rv.apply(A, {"Viz": sheet}, [f])["refused"]


def test_valid_revision_replaces_gold_only_for_that_item(tmp_path):
    f = _copy_bench(tmp_path)
    before = {x["id"]: x for x in yaml.safe_load(f.read_text(encoding="utf-8"))}
    ex = rv.drafted_items([f])[0][1]
    revised = ex.gold_yog.replace("fact role(agent, assistant)", "fact role(agent, assistant)\nfact role(bot, assistant)")
    sheet = f"## {ex.id}\nVERDICT: ok\nREVISED_YOG:\n```yog\n{revised}```\n"
    assert rv.apply(A, {"Viz": sheet}, [f])["accepted"] == [ex.id]
    after = {x["id"]: x for x in yaml.safe_load(f.read_text(encoding="utf-8"))}
    assert "role(bot, assistant)" in after[ex.id]["gold_yog"]
    assert all(after[i] == before[i] for i in before if i != ex.id and i in after) and set(after) == set(before)
    assert after[ex.id]["scenarios"] == before[ex.id]["scenarios"]


def test_reject_changes_nothing(tmp_path):
    f = _copy_bench(tmp_path)
    before = f.read_text(encoding="utf-8")
    ex = rv.drafted_items([f])[0][1]
    assert rv.apply(A, {"Viz": f"## {ex.id}\nVERDICT: reject\n"}, [f])["rejected"] == [ex.id]
    assert f.read_text(encoding="utf-8") == before
