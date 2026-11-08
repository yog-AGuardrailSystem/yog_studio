#!/usr/bin/env python3
"""Ask a running Studio server whether its real C lexer is live and agrees with the Python reference.

    python3 scripts/check_c_lexer.py http://localhost:10000

Exit 0 = the C lexer is available, accepted the sample, and produced exactly the reference's tokens.
Used by the `docker` job in .github/workflows/ci-cd.yml against the production image.
"""
import json
import sys
import urllib.request

SAMPLE = "fact role(alice, admin)\nallow can_x(U, R):\n    role(U, admin)\n"


def main(base: str) -> int:
    req = urllib.request.Request(
        base.rstrip("/") + "/api/compile/c-lexer",
        data=json.dumps({"source": SAMPLE}).encode(),
        headers={"content-type": "application/json"},
    )
    with urllib.request.urlopen(req, timeout=30) as resp:
        r = json.load(resp)
    problems = []
    if not r.get("available"):
        problems.append(f"C lexer not available: {r.get('reason')}")
    if not r.get("ok"):
        problems.append(f"C lexer rejected the sample: {r.get('reason')}")
    if r.get("mismatches"):
        problems.append(f"{len(r['mismatches'])} token mismatch(es), first: {r['mismatches'][0]}")
    if r.get("compared", 0) <= 10:
        problems.append(f"too few tokens compared: {r.get('compared')}")
    if problems:
        print("C lexer check FAILED:\n  " + "\n  ".join(problems))
        return 1
    print(f"C lexer OK: {r['compared']} tokens compared, 0 mismatches ({r.get('binary')})")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1] if len(sys.argv) > 1 else "http://localhost:10000"))
