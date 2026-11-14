"""The C compiler's intermediate representation (`yogc ir`), for the workbench's "C IR" tab.

The C engine compiles a program to a clause table (constant pool, predicates, clauses with goals, queries); there is no
bytecode (engine/c_front/src/ir/ir.h). This shows that table exactly as the engine team's tool prints it. It works
whichever engine is deciding (YOG_ENGINE), as long as yogc can be found or built (see c_build.py).
"""
import re
import subprocess
import tempfile
from pathlib import Path

from pydantic import BaseModel, Field

from app.engine.c_build import find_tool

MAX_SOURCE_BYTES = 200_000
MAX_OUTPUT_CHARS = 200_000
RUN_TIMEOUT_S = 5
_COUNT = re.compile(r"^(values|predicates|clauses|queries)=(\d+)$", re.M)
_ERR = re.compile(r"^(\d+):(\d+): error: (.*)$")


class CIRResult(BaseModel):
    available: bool
    ok: bool = False
    text: str = ""
    truncated: bool = False
    counts: dict[str, int] = Field(default_factory=dict)
    error: str | None = None
    line: int | None = None
    column: int | None = None


def run_c_ir(source: str) -> CIRResult:
    if len(source.encode("utf-8", "surrogatepass")) > MAX_SOURCE_BYTES or "\x00" in source:
        return CIRResult(available=True, error="the program is too large, or contains a NUL byte")
    yogc = find_tool("yogc")
    if yogc is None:
        return CIRResult(available=False, error="the C compiler (yogc) is not built on this server")
    with tempfile.TemporaryDirectory() as tmp:
        path = Path(tmp) / "input.yog"
        path.write_bytes(source.encode("utf-8", "surrogatepass"))
        try:
            p = subprocess.run([str(yogc), "ir", str(path)], capture_output=True, timeout=RUN_TIMEOUT_S, cwd=tmp)
        except subprocess.TimeoutExpired:
            return CIRResult(available=True, error=f"the C compiler did not finish within {RUN_TIMEOUT_S}s")
        except OSError as e:
            return CIRResult(available=False, error=f"could not run the C compiler: {e}")
        stderr = p.stderr.decode("utf-8", "replace").strip()
        if p.returncode != 0:
            last = (stderr.splitlines() or ["compile error"])[-1].replace(str(path) + ":", "", 1)
            m = _ERR.match(last)
            if m:
                return CIRResult(available=True, error=m.group(3), line=int(m.group(1)), column=int(m.group(2)))
            return CIRResult(available=True, error=last[:300])
    text = p.stdout.decode("utf-8", "replace")
    return CIRResult(available=True, ok=True, text=text[:MAX_OUTPUT_CHARS], truncated=len(text) > MAX_OUTPUT_CHARS,
                     counts={k: int(v) for k, v in _COUNT.findall(text)})
