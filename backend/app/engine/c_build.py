"""Locate or build the engine team's C tools (`lexdump`, `yogc`) from the vendored sources in engine/c_front/.

Order: $<env_var> (must exist, never built over), then a previous build in backend/data/c_front/ that matches the
vendored VERSION file, then a fresh build with the system C compiler. No compiler -> None (callers say so honestly).
We never edit the vendored sources; a new pinned commit changes VERSION, which triggers a rebuild.
"""
import hashlib
import os
import re
import shutil
import subprocess
from pathlib import Path

from app.core.config import DATA_DIR, REPO_ROOT

C_FRONT = REPO_ROOT / "engine" / "c_front"
OUT_DIR = DATA_DIR / "c_front"
BUILD_TIMEOUT_S = 120

_LEXER = ["src/lexer/lexer.c"]
_CORE = _LEXER + ["src/parser/*.c", "src/sema/*.c", "src/ir/*.c", "src/vm/*.c", "src/api/yog.c"]
TOOLS: dict[str, tuple[list[str], str]] = {      # name -> (sources, env var that overrides the build)
    "lexdump": (_LEXER + ["tools/lexdump.c"], "YOG_LEXDUMP"),
    "yogc": (_CORE + ["tools/yogc.c"], "YOG_YOGC"),
}


def _compiler() -> str | None:
    for name in (os.environ.get("CC"), "cc", "gcc", "clang"):
        if name and shutil.which(name):
            return shutil.which(name)
    return None


def _stamp() -> str:
    """Identifies the vendored source: hash of VERSION (pinned commit) so a re-vendor forces a rebuild."""
    try:
        return hashlib.sha256((C_FRONT / "VERSION").read_bytes()).hexdigest()
    except OSError:
        return "unknown"


def engine_commit() -> str | None:
    """Short commit of the vendored C engine (engine/c_front/VERSION), for the UI's engine badge."""
    try:
        m = re.search(r"^commit:\s*([0-9a-f]{7,40})", (C_FRONT / "VERSION").read_text(), re.M)
    except OSError:
        return None
    return m.group(1)[:7] if m else None


def _sources(patterns: list[str]) -> list[str]:
    out: list[str] = []
    for p in patterns:
        out += sorted(str(f) for f in C_FRONT.glob(p))
    return out


def find_tool(name: str, build: bool = True) -> Path | None:
    sources, env_var = TOOLS[name]
    env = os.environ.get(env_var)
    if env:
        return Path(env) if Path(env).is_file() else None
    exe = OUT_DIR / (name + (".exe" if os.name == "nt" else ""))
    stamp = OUT_DIR / f"{name}.stamp"
    fresh = exe.is_file() and stamp.is_file() and stamp.read_text().strip() == _stamp()
    if fresh:
        return exe
    if not build:
        return None
    cc = _compiler()
    srcs = _sources(sources)
    if not cc or not srcs:
        return None
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    tmp = exe.with_name(exe.name + ".tmp")
    cmd = [cc, "-std=c11", "-O2", "-I", str(C_FRONT / "src"), "-I", str(C_FRONT / "include"), *srcs, "-o", str(tmp)]
    try:
        subprocess.run(cmd, check=True, capture_output=True, timeout=BUILD_TIMEOUT_S)
        os.replace(tmp, exe)
    except (subprocess.SubprocessError, OSError):
        tmp.unlink(missing_ok=True)
        return None
    stamp.write_text(_stamp())
    return exe
