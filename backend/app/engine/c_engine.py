"""CEngineAdapter placeholder (W10). The C engine has no published ABI yet (only its lexer exists), so this class
deliberately does not guess one. When the engine team ships a shared library, implement the three methods here and
nothing else in Studio changes: the conformance suite (tests/test_engine_conformance.py) runs the 64 gold
examples' scenarios through every adapter that reports available().

Selecting it: set YOG_ENGINE=c and YOG_C_ENGINE_LIB=<path to the shared library>.
"""
import os
from pathlib import Path

from app.engine.adapter import CheckResult, EngineAdapter


class CEngineUnavailable(RuntimeError):
    pass


class CEngineAdapter(EngineAdapter):
    ENV_LIB = "YOG_C_ENGINE_LIB"

    @classmethod
    def available(cls) -> bool:
        lib = os.environ.get(cls.ENV_LIB)
        return bool(lib) and Path(lib).is_file() and cls._implemented

    _implemented = False          # flip to True once the ctypes bindings below exist

    def __init__(self) -> None:
        if not self.available():
            raise CEngineUnavailable(
                f"C engine not available: set {self.ENV_LIB} to the shared library and implement the ctypes bindings "
                "in app/engine/c_engine.py. Falling back to the Python prototype is configured in app/api/deps.py.")

    def check(self, policy, actor, action, resource, context=None) -> CheckResult:
        raise NotImplementedError("ctypes binding to the C engine's check() goes here")

    def validate(self, policy: str) -> list[str]:
        raise NotImplementedError("ctypes binding to the C engine's compile step goes here")

    def program_info(self, policy: str) -> dict:
        raise NotImplementedError("needs the C engine to expose its AST (or reuse the Python parser for explanation)")
