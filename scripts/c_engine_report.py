#!/usr/bin/env python3
"""Re-measure the C engine's own test evidence from a checkout of yog_engine (the figures the landing page quotes).

    python3 scripts/c_engine_report.py ../yog_engine

Builds each C test program of the engine repo with the engine's warning flags (-Wall -Wextra -Wpedantic -Wshadow
-Wconversion -Werror) plus AddressSanitizer and UndefinedBehaviorSanitizer, runs it, adds up tests and checks, then
runs the engine's own C-versus-Python differential script against a plain `yogc` build. cmake is not needed.
Prints one line per test program, a total, and the differential result. Exit 0 only if everything passed and the
sanitizers reported nothing. The checkout is only read (builds go to a temporary directory).
"""
import re
import subprocess
import sys
import tempfile
from pathlib import Path

FLAGS = ["-std=c11", "-g", "-O1", "-fsanitize=address,undefined", "-fno-omit-frame-pointer", "-Wall", "-Wextra",
         "-Wpedantic", "-Wshadow", "-Wconversion", "-Werror", "-I", "src", "-I", "include", "-I", "tests"]
LEXER = ["src/lexer/lexer.c"]
UPTO = {
    "lexer": LEXER,
    "parser": LEXER + ["src/parser/*.c"],
    "sema": LEXER + ["src/parser/*.c", "src/sema/*.c"],
    "ir": LEXER + ["src/parser/*.c", "src/sema/*.c", "src/ir/*.c"],
    "vm": LEXER + ["src/parser/*.c", "src/sema/*.c", "src/ir/*.c", "src/vm/*.c", "src/api/yog.c"],
    "api": LEXER + ["src/parser/*.c", "src/sema/*.c", "src/ir/*.c", "src/vm/*.c", "src/api/yog.c"],
}


def sources(root: Path, patterns: list[str]) -> list[str]:
    return [str(p) for pat in patterns for p in sorted(root.glob(pat))]


def main(repo: str) -> int:
    yog = Path(repo).resolve() / "yog"
    if not (yog / "src").is_dir():
        print(f"{repo} does not look like a yog_engine checkout (no yog/src)")
        return 2
    commit = subprocess.run(["git", "-C", str(yog), "rev-parse", "--short", "HEAD"], capture_output=True, text=True).stdout.strip()
    ok, tests, checks = True, 0, 0
    with tempfile.TemporaryDirectory() as tmp:
        for name, patterns in UPTO.items():
            test_c = yog / "tests" / name / f"test_{name}.c"
            exe = Path(tmp) / f"test_{name}"
            build = subprocess.run(["gcc", *FLAGS, str(test_c), *sources(yog, patterns), "-o", str(exe)], cwd=yog,
                                   capture_output=True, text=True)
            if build.returncode:
                print(f"{name:7} BUILD FAILED\n{build.stderr[:400]}")
                ok = False
                continue
            run = subprocess.run([str(exe)], cwd=yog / "tests" / name, capture_output=True, text=True)
            out = run.stdout
            m = re.search(r"(\d+) checks, (\d+) failed, (\d+)/(\d+) tests passed", out)       # the lexer's own summary
            if m:
                n_checks, n_tests, passed = int(m.group(1)), int(m.group(4)), int(m.group(3)) == int(m.group(4)) and not int(m.group(2))
            else:
                m = re.search(r"PASS: test_\w+ \((\d+) checks\)", out)
                n_checks = int(m.group(1)) if m else 0
                main_body = test_c.read_text().split("int main", 1)[1]
                n_tests = len(re.findall(r"^\s+test_\w+\(\);", main_body, re.M))
                passed = bool(m)
            clean = run.returncode == 0 and not run.stderr.strip()                          # sanitizers print to stderr
            ok &= passed and clean
            tests, checks = tests + n_tests, checks + n_checks
            print(f"{name:7} {n_tests:3} tests {n_checks:6} checks  {'ok' if passed and clean else 'FAILED'}")
        print(f"total   {tests:3} tests {checks:6} checks  under ASan+UBSan, -Werror  (yog_engine {commit})")
        yogc = Path(tmp) / "yogc"
        subprocess.run(["gcc", "-std=c11", "-O2", "-I", "src", "-I", "include", *sources(yog, UPTO["api"]), "tools/yogc.c",
                        "-o", str(yogc)], cwd=yog, check=True)
        diff = subprocess.run([sys.executable, "-B", str(yog / "tests" / "differential" / "diff_vs_python.py"), "--yogc", str(yogc)],
                              cwd=yog.parent, capture_output=True, text=True, env={"PYTHONDONTWRITEBYTECODE": "1", "PATH": "/usr/bin:/bin"})
        print(diff.stdout.strip().splitlines()[-1] if diff.stdout.strip() else "differential: no output")
        for line in diff.stdout.splitlines():
            if "queries match" in line:
                print(line.split("/")[-1].strip())
        ok &= diff.returncode == 0
    print("RESULT:", "all passed" if ok else "FAILED")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main(sys.argv[1] if len(sys.argv) > 1 else "../yog_engine"))
