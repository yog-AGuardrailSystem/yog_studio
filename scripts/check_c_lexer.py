#!/usr/bin/env python3
"""Ask a running Studio server whether its real C lexer is live and agrees with the Python reference, and whether the C
engine is the one deciding (/info, a real /check, and the C IR).

    python3 scripts/check_c_lexer.py http://localhost:10000

Exit 0 = the C lexer is available, accepted the sample, and produced exactly the reference's tokens; /info says the
engine is "c"; /check allows alice and denies bob on the sample; /compile/c-ir returns the clause table; the three
yogc downloads are listed and served byte-for-byte as their SHA-256 says.
Used by the `docker` job in .github/workflows/ci-cd.yml against the production image.
"""
import hashlib
import json
import sys
import urllib.request

SAMPLE = "fact role(alice, admin)\nallow can_x(U, R):\n    role(U, admin)\n"


def _call(base: str, path: str, body: dict | None = None) -> dict:
    req = urllib.request.Request(base.rstrip("/") + "/api" + path, data=json.dumps(body).encode() if body is not None else None,
                                 headers={"content-type": "application/json"})
    with urllib.request.urlopen(req, timeout=30) as resp:
        return json.load(resp)


def main(base: str) -> int:
    r = _call(base, "/compile/c-lexer", {"source": SAMPLE})
    problems = []
    if not r.get("available"):
        problems.append(f"C lexer not available: {r.get('reason')}")
    if not r.get("ok"):
        problems.append(f"C lexer rejected the sample: {r.get('reason')}")
    if r.get("mismatches"):
        problems.append(f"{len(r['mismatches'])} token mismatch(es), first: {r['mismatches'][0]}")
    if r.get("compared", 0) <= 10:
        problems.append(f"too few tokens compared: {r.get('compared')}")
    info = _call(base, "/info")
    if info.get("engine") != "c":
        problems.append(f"the deciding engine is {info.get('engine')!r}, expected 'c'")
    for actor, want in (("alice", "ALLOW"), ("bob", "DENY")):
        d = _call(base, "/check", {"policy": SAMPLE, "actor": actor, "action": "can_x", "resource": "db", "context": []})
        if d.get("decision") != want:
            problems.append(f"/check {actor}: got {d.get('decision')} ({d.get('reason')}), expected {want}")
    ir = _call(base, "/compile/c-ir", {"source": SAMPLE})
    if not ir.get("ok") or ir.get("counts", {}).get("clauses") != 2:
        problems.append(f"C IR not available or wrong: {ir.get('error') or ir.get('counts')}")
    # the /download page's packages are in the image, listed, and served byte-for-byte as listed
    dl = _call(base, "/downloads")
    names = sorted(f["name"] for f in dl.get("files", []))
    if not dl.get("available") or names != ["yog-linux-x64.tar.gz", "yog-setup-windows-x64.exe", "yog-windows-x64.zip"]:
        problems.append(f"downloads missing or incomplete: {names or dl.get('note')}")
    for f in dl.get("files", []):
        with urllib.request.urlopen(base.rstrip("/") + f["url"], timeout=60) as resp:
            data = resp.read()
        if hashlib.sha256(data).hexdigest() != f["sha256"] or len(data) != f["size"]:
            problems.append(f"{f['name']}: served bytes do not match the manifest")
    if dl.get("engine_commit") != info.get("engine_commit"):
        problems.append(f"downloads built from {dl.get('engine_commit')}, server runs {info.get('engine_commit')}")
    if problems:
        print("C engine check FAILED:\n  " + "\n  ".join(problems))
        return 1
    print(f"C lexer OK: {r['compared']} tokens compared, 0 mismatches ({r.get('binary')}); "
          f"C engine deciding (commit {info.get('engine_commit')}), /check and C IR OK; "
          f"{len(dl['files'])} downloads match their checksums")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1] if len(sys.argv) > 1 else "http://localhost:10000"))
