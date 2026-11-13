"""Adapter over the vendored Python reference prototype (engine/yog.py).

yog.py is loaded by file path so the vendored copy stays untouched and
`engine/` does not need to be a package.
"""
import importlib.util
import sys
from functools import lru_cache
from types import ModuleType

from app.core.config import ENGINE_PATH
from app.engine.adapter import (AskResult, CheckResult, ClauseWhy, CompileInfo, EngineAdapter, EngineError,
                                PredicateInfo, QuerySpec, TokenInfo, WhyResult, WhyStep)
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


MAX_SOLVE_STEPS = 400_000      # goal evaluations allowed for ONE decision; honest policies need a few hundred
MAX_TRACE_STEPS = 200_000      # entries the shared trace list may hold


class EvaluationLimit(Exception):
    """A policy needed more work than one decision is allowed. check/explain/ask treat it as DENY (fail closed)."""


def _bounded(engine) -> None:
    """Put a step budget on this engine instance without touching the vendored engine/yog.py.

    The engine only guarantees that evaluation terminates (rules cannot recurse); a non-recursive join over a few
    facts still enumerates exponentially many proofs when its last goal fails, and every step appends to an in-memory
    trace. Engine.solve calls itself through `self.solve`, so replacing the instance attribute counts every goal."""
    original = engine.solve
    steps = [0]

    def solve(goal, s, trace, depth=0):
        # One unit per goal PLUS one per stored fact it must be tried against: the engine has no index, so a goal over a
        # predicate with many facts costs that many unifications. Counting only goals let a big fact table through.
        key = getattr(goal, "key", None) or getattr(getattr(goal, "goal", None), "key", None)
        steps[0] += 1 + (len(engine.facts.get(key, ())) if key is not None else 0)
        if steps[0] > MAX_SOLVE_STEPS or len(trace) > MAX_TRACE_STEPS:
            raise EvaluationLimit(f"evaluation budget exceeded ({MAX_SOLVE_STEPS} steps)")
        yield from original(goal, s, trace, depth)

    engine.solve = solve


def _parse_text(policy: str):
    yog = _load_yog()
    try:
        return yog.Parser(yog.tokenize(policy)).parse()
    except yog.YogError as e:
        raise EngineError(str(e)) from e
    except (IndexError, AttributeError) as e:      # parser edge cases on truncated input
        raise EngineError(f"syntax error: could not parse policy ({type(e).__name__})") from e
    except (RecursionError, ValueError) as e:       # absurdly nested text, or a number literal Python cannot convert
        raise EngineError(f"could not parse policy ({type(e).__name__}): it is too large or too deeply nested") from e


# Tokenize and parse a policy once per distinct text. A tool that makes thousands of checks against one policy used to
# re-tokenize and re-parse the whole text for every check, so a request budget counted calls but the real cost was
# calls x policy size. The Program is read-only (each Engine copies what it changes), so sharing it is safe, and
# exceptions are not cached. Only policy texts go through the cache; one-line context facts do not (they would evict it).
_parse_small = lru_cache(maxsize=16)(_parse_text)
CACHE_MAX_CHARS = 30_000       # a parsed policy is ~50x its text; larger ones are parsed per call so the cache stays small


def _parse_cached(policy: str):
    return _parse_small(policy) if len(policy) <= CACHE_MAX_CHARS else _parse_text(policy)


_parse_cached.cache_info = _parse_small.cache_info          # type: ignore[attr-defined]
_parse_cached.cache_clear = _parse_small.cache_clear        # type: ignore[attr-defined]


LIMIT_REASON = "evaluation budget exceeded, failing closed: the policy needs more work than one decision is allowed"


class PythonPrototypeAdapter(EngineAdapter):
    def __init__(self) -> None:
        self.yog = _load_yog()

    # -- helpers ---------------------------------------------------------
    def _parse(self, policy: str):
        return _parse_cached(policy)

    def _engine(self, policy: str):
        prog = self._parse(policy)
        try:
            engine = self.yog.Engine(prog)
        except self.yog.YogError as e:
            raise EngineError(str(e)) from e
        except RecursionError as e:                 # a chain of thousands of rules overflows the semantic checker
            raise EngineError("the policy's rules are nested too deeply to check") from e
        _bounded(engine)
        return engine

    def _context_atoms(self, context: list[str]) -> list:
        atoms = []
        for text in context:
            text = text.strip()
            if not text:
                continue
            try:
                facts = _parse_text("fact " + text).facts
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
        except EvaluationLimit:
            return CheckResult(decision="DENY", trace=[], reason=LIMIT_REASON)
        except RecursionError:                      # a very long clause body: fail closed, never a 500 or an ALLOW
            return CheckResult(decision="DENY", trace=[], reason="engine error, failing closed: the policy is nested too deeply")
        return CheckResult(decision=raw["decision"], reason=raw["reason"], trace=list(raw["trace"]))

    # -- why: the proof behind a decision ---------------------------------------
    def _render(self, goal, s) -> str:
        yog = self.yog
        def one(t):
            t = yog.walk(t, s)
            return repr(t)
        if isinstance(goal, yog.Cmp):
            return f"{one(goal.lhs)} {goal.op} {one(goal.rhs)}"
        if isinstance(goal, yog.Neg):
            return f"not {yog.fmt(goal.goal, s)}"
        return yog.fmt(goal, s)

    def _prove(self, engine, goals: list, s: dict):
        """Backtracking proof of a clause body, like the engine's own, that also remembers how far it got.
        Returns (final substitution or None, deepest goal index reached, substitution at that point)."""
        best = {"depth": -1, "s": s}

        def rec(i: int, sub: dict):
            if i == len(goals):
                return sub
            for s2 in engine.solve(goals[i], sub, [], 0):
                r = rec(i + 1, s2)
                if r is not None:
                    return r
            if i > best["depth"]:
                best["depth"], best["s"] = i, sub
            return None

        final = rec(0, s)
        return final, best["depth"], best["s"]

    def _fail_note(self, goal, s) -> str:
        yog = self.yog
        if isinstance(goal, yog.Cmp):
            return "this comparison is false"
        if isinstance(goal, yog.Neg):
            return "this holds, so the 'not' fails"
        return "no fact or rule matches"

    def explain(self, policy, actor, action, resource, context=None) -> WhyResult:
        yog = self.yog
        engine = self._engine(policy)
        atoms = self._context_atoms(context or [])
        ctx_text = [repr(a) for a in atoms]
        for f in atoms:                                       # per-request facts, like Engine.check
            engine.facts.setdefault(f.key, []).append(f)
        try:
            goal = yog.Atom(action, [yog.Const(actor), yog.Const(resource)])
            if goal.key not in engine.decisions:
                return WhyResult(decision="DENY", reason=f"no allow/deny clause defines action {action}/2",
                                 verdict=f"DENY: no allow or deny rule is written for {action}, so it is denied.",
                                 context=ctx_text)
            out: list[ClauseWhy] = []
            try:
                for kind in ("deny", "allow"):
                    for clause in [c for c in engine.decisions[goal.key] if c.kind == kind]:
                        c = engine.rename(clause)
                        s0 = engine.unify_atom(goal, c.head, {})
                        if s0 is None:
                            out.append(ClauseWhy(kind=kind, line=clause.line, head=repr(clause.head),
                                                 status="head_mismatch"))
                            continue
                        final, depth, s_at = self._prove(engine, c.body, s0)
                        if final is not None:
                            steps = [WhyStep(text=self._render(g, final), ok=True) for g in c.body]
                            out.append(ClauseWhy(kind=kind, line=clause.line, head=repr(clause.head),
                                                 status="matched", steps=steps))
                            continue
                        steps = []
                        for i, g in enumerate(c.body):
                            if i < depth:
                                steps.append(WhyStep(text=self._render(g, s_at), ok=True))
                            elif i == depth:
                                steps.append(WhyStep(text=self._render(g, s_at), ok=False, note=self._fail_note(g, s_at)))
                            else:
                                steps.append(WhyStep(text=self._render(g, s_at), ok=None, note="not reached"))
                        out.append(ClauseWhy(kind=kind, line=clause.line, head=repr(clause.head),
                                             status="failed", steps=steps, failed_at=depth))
            except TypeError as e:                            # engine issue #7: fail closed
                return WhyResult(decision="DENY", error=True, clauses=out, context=ctx_text,
                                 reason=f"engine error, failing closed: comparison between incompatible types ({e})",
                                 verdict="DENY: the engine hit an error comparing a number with a name, so it failed closed.")
            except EvaluationLimit:
                return WhyResult(decision="DENY", error=True, clauses=out, context=ctx_text, reason=LIMIT_REASON,
                                 verdict="DENY: this policy needs more work than one decision is allowed, so it failed closed.")
            deny = next((c for c in out if c.kind == "deny" and c.status == "matched"), None)
            allow = next((c for c in out if c.kind == "allow" and c.status == "matched"), None)
            if deny:
                extra = f" An allow rule at line {allow.line} also matched, but DENY beats ALLOW." if allow else ""
                return WhyResult(decision="DENY", winner_line=deny.line, clauses=out, context=ctx_text,
                                 reason=f"deny clause at line {deny.line} matched",
                                 verdict=f"DENY: the deny rule at line {deny.line} matched.{extra}")
            if allow:
                return WhyResult(decision="ALLOW", winner_line=allow.line, clauses=out, context=ctx_text,
                                 reason=f"allow clause at line {allow.line} matched",
                                 verdict=f"ALLOW: the allow rule at line {allow.line} matched and no deny rule matched.")
            allows = [c for c in out if c.kind == "allow"]
            near = max(allows, key=lambda c: (c.failed_at if c.failed_at is not None else -1), default=None)
            if near is None:
                hint = " There is no allow rule for this action."
            elif near.status == "head_mismatch":
                hint = f" The allow rule at line {near.line} is about a different actor or resource."
            else:
                bad = near.steps[near.failed_at] if near.failed_at is not None else None
                hint = f" The closest allow rule (line {near.line}) stopped at: {bad.text}." if bad else ""
            return WhyResult(decision="DENY", clauses=out, context=ctx_text,
                             reason="default deny: no allow clause was satisfied",
                             verdict=f"DENY by default: no allow rule matched.{hint}")
        finally:
            for f in atoms:
                lst = engine.facts.get(f.key, [])
                if f in lst:
                    lst.remove(f)

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
        except EvaluationLimit:
            return AskResult(answer=False, trace=[LIMIT_REASON])
        shown = []
        for s in sols:
            b = {k: (v.val if isinstance(v, yog.Const) else repr(v)) for k, v in s.items()
                 if "#" not in k and not k.startswith("_G")}
            if b:
                shown.append(b)
        return AskResult(answer=ok, bindings=shown, trace=list(trace))
