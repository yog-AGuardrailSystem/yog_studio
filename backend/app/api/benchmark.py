"""Serves committed REAL benchmark results (never the offline-fake ones) so the UI can show evidence, not claims."""
import json

from fastapi import APIRouter, HTTPException

from app.core.config import REPO_ROOT

router = APIRouter()
RESULTS_DIR = REPO_ROOT / "benchmark" / "results"


def _files(kind: str) -> list:
    if not RESULTS_DIR.exists():
        return []
    # fake results live in results/fake/ and are never listed; also skip any file whose own provider says fake
    out = []
    for f in sorted(RESULTS_DIR.glob(f"{kind}-*.json"), reverse=True):
        try:
            data = json.loads(f.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            continue
        if data.get("provider") != "fake":
            out.append((f, data))
    return out


@router.get("/benchmark/list")
def list_results() -> list[dict]:
    return [{"file": f.name, "kind": f.name.split("-")[0], "provider": d.get("provider"), "model": d.get("model"),
             "when": d.get("when")} for kind in ("eval", "retrieval") for f, d in _files(kind)]


@router.get("/benchmark/latest")
def latest() -> dict:
    """The newest real evaluation and retrieval result, or nulls. Nothing is invented when no real run exists."""
    ev, rt = _files("eval"), _files("retrieval")
    return {"evaluation": ev[0][1] if ev else None, "retrieval": rt[0][1] if rt else None,
            "note": None if (ev or rt) else "No real benchmark has been run yet. Run it with a Gemini or Claude key."}


@router.get("/benchmark/file/{name}")
def get_file(name: str) -> dict:
    for kind in ("eval", "retrieval"):
        for f, d in _files(kind):
            if f.name == name:
                return d
    raise HTTPException(404, "no such result")
