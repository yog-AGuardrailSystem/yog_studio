"""Thin wrapper: python scripts/review_pack.py pack|apply ...  (see backend/app/benchmark/review.py).
Run from backend/ with uv:  uv run python ../scripts/review_pack.py pack --reviewers A,B,C"""
import runpy
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "backend"))
runpy.run_module("app.benchmark.review", run_name="__main__")
