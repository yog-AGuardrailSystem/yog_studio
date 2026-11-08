"""The private claims ledger must stay consistent with the repo: every `backed` row points at a file that exists."""
import importlib.util
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def _load():
    spec = importlib.util.spec_from_file_location("claims_check", ROOT / "scripts" / "claims_check.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def test_ledger_has_no_broken_rows():
    assert _load().main(strict=False) == 0


def test_strict_mode_fails_while_claims_are_aspirational():
    assert _load().main(strict=True) == 1
