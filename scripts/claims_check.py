"""List the claims the site makes that are not yet demonstrable, and verify the evidence paths of the rest.

    python scripts/claims_check.py          # exit 1 if a `backed` row points at a missing file
    python scripts/claims_check.py --strict # exit 1 if anything is still aspirational (use before the demo)
"""
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
LEDGER = ROOT / "docs" / "claims-ledger.md"
PATH_RE = re.compile(r"[\w./-]+\.(?:py|ts|tsx|mjs|md|yaml|json)\b|\bDockerfile\b")


def rows(text: str) -> list[tuple[str, str, str, str]]:
    out = []
    for line in text.splitlines():
        cells = [c.strip() for c in line.strip().strip("|").split("|")]
        if len(cells) == 4 and re.fullmatch(r"C\d+", cells[0]):
            out.append((cells[0], cells[1], cells[2], cells[3]))
    return out


def main(strict: bool = False) -> int:
    items = rows(LEDGER.read_text(encoding="utf-8"))
    if not items:
        print("no claims found in", LEDGER)
        return 1
    bad, aspirational = [], []
    for cid, claim, status, evidence in items:
        if status == "aspirational":
            aspirational.append((cid, claim, evidence))
        elif status == "backed":
            missing = [p for p in PATH_RE.findall(evidence) if not (ROOT / p).exists()]
            if missing or not PATH_RE.search(evidence):
                bad.append((cid, missing or ["(no evidence path)"]))
        else:
            bad.append((cid, [f"unknown status {status!r}"]))
    print(f"{len(items)} claims: {len(items) - len(aspirational) - len(bad)} backed, {len(aspirational)} aspirational, {len(bad)} broken")
    for cid, claim, ev in aspirational:
        print(f"  ASPIRATIONAL {cid}: {claim}\n      needs: {ev}")
    for cid, missing in bad:
        print(f"  BROKEN {cid}: {missing}")
    return 1 if bad or (strict and aspirational) else 0


if __name__ == "__main__":
    sys.exit(main("--strict" in sys.argv))
