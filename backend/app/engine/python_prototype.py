"""Adapter over the vendored Python reference prototype (engine/yog.py).

yog.py is loaded by file path so the vendored copy stays untouched and
`engine/` does not need to be a package.
"""
import importlib.util
import sys
from functools import lru_cache
from types import ModuleType

from app.core.config import ENGINE_PATH
from app.engine.adapter import (AskResult, CheckResult, CompileInfo, EngineAdapter, EngineError, PredicateInfo,
                                QuerySpec, TokenInfo)
from app.engine.diagnostics import classify


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


def _term_ast(yog, t) -> dict:
    """Term JSON for the compiler explorer. An underscore is parsed into a fresh hidden variable; show a wildcard."""
    if isinstance(t, yog.Var):
        return {"wildcard": True} if t.name.startswith("_G") else {"var": t.name}
    return {"const": t.val}


def _atom_ast(yog, a) -> dict:
    return {"pred": a.pred, "args": [_term_ast(yog, x) for x in a.args], "line": a.line}


def _goal_ast(yog, g) -> dict:
    if isinstance(g, yog.Neg):
        return {"type": "not", "atom": _atom_ast(yog, g.goal)}
    if isinstance(g, yog.Cmp):
        return {"type": "cmp", "op": g.op, "lhs": _term_ast(yog, g.lhs), "rhs": _term_ast(yog, g.rhs),
                "line": g.line}
    return {"type": "atom", **_atom_ast(yog, g)}


def _program_ast(yog, prog) -> dict:
    return {
        "facts": [_atom_ast(yog, f) for f in prog.facts],
        "clauses": [{"kind": c.kind, "head": _atom_ast(yog, c.head),
                     "body": [_goal_ast(yog, g) for g in c.body], "line": c.line} for c in prog.clauses],
        "queries": [_atom_ast(yog, q) for q in prog.queries],
    }


def _predicates(prog) -> list[PredicateInfo]:
    out: dict[tuple[str, int, str], PredicateInfo] = {}
    def add(atom, role):
        key = (atom.pred, len(atom.args), role)
        if key in out:
            out[key].clauses += 1
        else:
            out[key] = PredicateInfo(name=atom.pred, arity=len(atom.args), role=role, clauses=1, line=atom.line or None)
    for f in prog.facts:
        add(f, "fact")
    for c in prog.clauses:
        add(c.head, "rule" if c.kind == "rule" else "decision")
    return list(out.values())


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
        try:
            raw = engine.check(actor, action, resource, atoms)
        except TypeError as e:
            # Engine bug (docs/engine_issues.md #7): ordering comparison between an int and a name crashes.
            # A guardrail must fail closed, so report DENY rather than propagate a 500.
            return CheckResult(decision="DENY", trace=[],
                               reason=f"engine error, failing closed: comparison between incompatible types ({e})")
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

    # -- compiler explorer ----------------------------------------------------
    def compile_info(self, policy: str) -> CompileInfo:
        yog = self.yog
        info = CompileInfo(ok=False)
        lines = policy.splitlines()
        try:
            toks = yog.tokenize(policy)
        except yog.YogError as e:
            info.diagnostics.append(classify(str(e), source_lines=lines))
            return info
        info.tokens = [TokenInfo(kind=t.kind, value=t.val, line=t.line) for t in toks]
        try:
            prog = yog.Parser(toks).parse()
        except yog.YogError as e:
            info.diagnostics.append(classify(str(e), source_lines=lines))
            return info
        except (IndexError, AttributeError) as e:
            info.diagnostics.append(classify(f"syntax error: could not parse policy ({type(e).__name__})"))
            return info
        info.ast = _program_ast(yog, prog)
        info.predicates = _predicates(prog)
        known = {(p.name, p.arity): p.role for p in info.predicates}
        try:
            yog.check_program(prog)
            info.ok = True
        except yog.YogError as e:
            info.diagnostics.append(classify(str(e), known, lines))
        return info

    def queries(self, policy: str) -> list[QuerySpec]:
        yog = self.yog
        prog = self._parse(policy)
        return [QuerySpec(line=q.line, pred=q.pred, terms=[_term_ast(yog, t) for t in q.args], text=repr(q))
                for q in prog.queries]

    def ask(self, policy: str, pred: str, terms: list[dict]) -> AskResult:
        yog = self.yog
        engine = self._engine(policy)
        goal = yog.Atom(pred, [yog.Var(t["var"]) if "var" in t else yog.Const(t["const"]) for t in terms])
        try:
            ok, sols, trace = engine.ask(goal)
        except TypeError as e:           # engine bug #7 (int vs name comparison): fail closed, never a 500
            return AskResult(answer=False, trace=[f"engine error, failing closed: {e}"])
        shown = []
        for s in sols:
            b = {k: (v.val if isinstance(v, yog.Const) else repr(v)) for k, v in s.items()
                 if "#" not in k and not k.startswith("_G")}
            if b:
                shown.append(b)
        return AskResult(answer=ok, bindings=shown, trace=list(trace))
