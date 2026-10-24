"""Adapter over the vendored Python reference prototype (engine/yog.py).

yog.py is loaded by file path so the vendored copy stays untouched and
`engine/` does not need to be a package.
"""
import importlib.util
import sys
from functools import lru_cache
from types import ModuleType

from app.core.config import ENGINE_PATH
from app.engine.adapter import CheckResult, EngineAdapter, EngineError


@lru_cache(maxsize=1)
def _load_yog() -> ModuleType:
    spec = importlib.util.spec_from_file_location("yog_vendored", ENGINE_PATH)
    mod = importlib.util.module_from_spec(spec)
    sys.modules["yog_vendored"] = mod        # dataclasses need the module registered
    old, sys.dont_write_bytecode = sys.dont_write_bytecode, True   # keep engine/ free of __pycache__
    try:
        spec.loader.exec_module(mod)
    finally:
        sys.dont_write_bytecode = old
    return mod


def _term_json(yog, t) -> dict:
    if isinstance(t, yog.Var):
        return {"var": t.name}
    return {"const": t.val}


def _goal_json(yog, g) -> dict:
    if isinstance(g, yog.Neg):
        return {"type": "not", "atom": _goal_json(yog, g.goal)}
    if isinstance(g, yog.Cmp):
        return {"type": "cmp", "op": g.op,
                "lhs": _term_json(yog, g.lhs), "rhs": _term_json(yog, g.rhs)}
    return {"type": "atom", "pred": g.pred, "args": [_term_json(yog, a) for a in g.args]}


class PythonPrototypeAdapter(EngineAdapter):
    def __init__(self) -> None:
        self.yog = _load_yog()

    # -- helpers ---------------------------------------------------------
    def _parse(self, policy: str):
        yog = self.yog
        try:
            return yog.Parser(yog.tokenize(policy)).parse()
        except yog.YogError as e:
            raise EngineError(str(e)) from e
        except (IndexError, AttributeError) as e:      # parser edge cases on truncated input
            raise EngineError(f"syntax error: could not parse policy ({type(e).__name__})") from e

    def _engine(self, policy: str):
        prog = self._parse(policy)
        try:
            return self.yog.Engine(prog)
        except self.yog.YogError as e:
            raise EngineError(str(e)) from e

    def _context_atoms(self, context: list[str]) -> list:
        atoms = []
        for text in context:
            text = text.strip()
            if not text:
                continue
            try:
                facts = self._parse("fact " + text).facts
            except EngineError as e:
                raise EngineError(f"bad context fact {text!r}: {e}") from e
            if len(facts) != 1:
                raise EngineError(f"bad context fact {text!r}: expected exactly one fact")
            atoms.extend(facts)
        return atoms

    # -- EngineAdapter ---------------------------------------------------
    def check(self, policy, actor, action, resource, context=None) -> CheckResult:
        engine = self._engine(policy)
        atoms = self._context_atoms(context or [])
        raw = engine.check(actor, action, resource, atoms)
        return CheckResult(decision=raw["decision"], reason=raw["reason"], trace=list(raw["trace"]))

    def validate(self, policy: str) -> list[str]:
        try:
            self._engine(policy)
        except EngineError as e:
            return [str(e)]
        return []

    def program_info(self, policy: str) -> dict:
        prog = self._parse(policy)
        try:
            self.yog.check_program(prog)
        except self.yog.YogError as e:
            raise EngineError(str(e)) from e
        yog = self.yog
        return {
            "facts": [{"pred": f.pred, "args": [_term_json(yog, a) for a in f.args], "line": f.line}
                      for f in prog.facts],
            "clauses": [{"kind": c.kind,
                         "head": {"pred": c.head.pred, "args": [_term_json(yog, a) for a in c.head.args]},
                         "body": [_goal_json(yog, g) for g in c.body],
                         "line": c.line} for c in prog.clauses],
        }
