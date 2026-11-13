"""Shared helpers for the Studio tools: which policy to use, a cap on engine checks per request, and the one way a
tool call becomes an engine request (the same path the device simulator and the runtime guard use)."""
from fastapi import HTTPException
from pydantic import BaseModel, Field

from app.core import facts
from app.core.config import EXAMPLES_DIR
from app.engine.adapter import CheckResult, EngineAdapter, EngineError
from app.policies.store import PolicyStore

MAX_SOURCE_CHARS = 200_000
DEMO_ID = "demo"
DEMO_POLICY_PATH = EXAMPLES_DIR / "policies" / "demo_smart_home.yog"
MAX_CHECKS = 2_000                      # engine checks one request may spend
MAX_ARG_KEYS = 60                       # (tool, param) pairs the probe generators expand; a pasted policy can name thousands


def policy_sha256(text: str) -> str:
    """The hash the runtime guard pins (YOG_POLICY_SHA256): SHA-256 of the policy with Windows line endings read as
    Unix ones, the same rule app/modify/yog_runtime.py applies to the file it loads."""
    import hashlib
    return hashlib.sha256(text.replace("\r\n", "\n").encode("utf-8")).hexdigest()


class PolicyRef(BaseModel):
    """Which policy a tool works on: an approved one by id, the built-in demo ("demo"), or pasted text.
    With neither, the visitor's latest approved policy."""
    policy_id: str | None = None
    source: str | None = Field(default=None, max_length=MAX_SOURCE_CHARS)


class ResolvedPolicy(BaseModel):
    source: str
    label: str
    policy_id: str | None
    approved: bool                       # True only for a policy a human approved in this session


def resolve_policy(ref: PolicyRef, store: PolicyStore) -> ResolvedPolicy:
    if ref.source and ref.source.strip():
        return ResolvedPolicy(source=ref.source, label="pasted policy", policy_id=None, approved=False)
    if ref.policy_id == DEMO_ID:
        return ResolvedPolicy(source=DEMO_POLICY_PATH.read_text(encoding="utf-8"), label="demo policy (hand-written)",
                              policy_id=DEMO_ID, approved=False)
    if ref.policy_id:
        rec = store.get(ref.policy_id)
        if rec is None:
            raise HTTPException(status_code=404, detail="no such approved policy")
        return ResolvedPolicy(source=rec.yog_source, label=f"approved {rec.id}", policy_id=rec.id, approved=True)
    rec = store.latest()
    if rec is None:
        raise HTTPException(status_code=409, detail="no approved policy yet: approve one, paste one, or use the demo policy")
    return ResolvedPolicy(source=rec.yog_source, label=f"approved {rec.id}", policy_id=rec.id, approved=True)


def require_valid(adapter: EngineAdapter, source: str) -> None:
    errors = adapter.validate(source)
    if errors:
        raise HTTPException(status_code=422, detail="the policy does not compile: " + "; ".join(errors[:3]))


class BudgetExceeded(Exception):
    pass


class Budget:
    """A cap on engine checks so one request cannot keep the server busy."""

    def __init__(self, limit: int = MAX_CHECKS) -> None:
        self.limit, self.used = limit, 0

    def spend(self, n: int = 1) -> None:
        self.used += n
        if self.used > self.limit:
            raise BudgetExceeded(f"this would need more than {self.limit} engine checks; narrow the request")


def budget_error(e: BudgetExceeded) -> HTTPException:
    return HTTPException(status_code=422, detail=str(e))


def safe_check(adapter: EngineAdapter, policy: str, actor: str, action: str, resource: str,
               context: list[str]) -> CheckResult:
    """One engine check that never raises on a bad context fact: that row is simply a DENY with the reason."""
    try:
        return adapter.check(policy, actor, action, resource, context)
    except EngineError as e:
        return CheckResult(decision="DENY", reason=f"could not evaluate: {e}", trace=[])


def call_request(tool: str, args: dict, hour: int, day: str, actor: str = "agent") -> tuple[str, str, str, list[str]]:
    """(actor, action, resource, context) for one real tool call, exactly as the guard and the simulator build it."""
    ctx = facts.facts_from_call(tool, args, hour, day)
    resource = next((facts.ident(v) for v in args.values() if isinstance(v, str)), "item")
    return actor, "can_" + facts.ident(tool), resource, ctx


# ----------------------------------------------------------------- what a policy talks about
class Shape(BaseModel):
    actions: list[str]                  # decision predicates, e.g. can_unlock_door
    actors: list[str]
    resources: list[str]
    constants: list[int]                # integers compared against variables (boundaries live here)
    arg_keys: list[tuple[str, str]]     # (tool, param) read through arg(tool, param, V)
    uses_hour: bool
    uses_day: bool


def _atoms(info: dict):
    for c in info["clauses"]:
        for g in c["body"]:
            if g["type"] in ("atom", "not"):
                yield c, (g if g["type"] == "atom" else g["atom"])


def shape(info: dict) -> Shape:
    """What a parsed policy (adapter.program_info) refers to. Everything is read from the program, not guessed."""
    actions = sorted({c["head"]["pred"] for c in info["clauses"] if c["kind"] in ("allow", "deny")})
    actors: list[str] = []
    for f in info["facts"]:
        if f["pred"] == "role" and f["args"] and "const" in f["args"][0]:
            a = str(f["args"][0]["const"])
            if a != "placeholder" and a not in actors:
                actors.append(a)
    resources: list[str] = []
    nums: set[int] = set()
    for c in info["clauses"]:
        for g in c["body"]:
            if g["type"] == "cmp":
                for side in (g["lhs"], g["rhs"]):
                    if "const" in side and isinstance(side["const"], int) and not isinstance(side["const"], bool):
                        nums.add(side["const"])
                    elif "const" in side and isinstance(side["const"], str) and side["const"] not in resources:
                        resources.append(side["const"])
    keys: list[tuple[str, str]] = []
    used: set[str] = set()
    for _c, a in _atoms(info):
        used.add(a["pred"])
        if a["pred"] == "arg" and len(a["args"]) == 3 and "const" in a["args"][0] and "const" in a["args"][1]:
            k = (str(a["args"][0]["const"]), str(a["args"][1]["const"]))
            if k not in keys and k[0] != "placeholder":
                keys.append(k)
    return Shape(actions=actions, actors=actors or ["agent"], resources=resources[:3], constants=sorted(nums),
                 arg_keys=keys[:MAX_ARG_KEYS], uses_hour="hour" in used, uses_day="day" in used)


def boundary_values(constants: list[int], limit: int = 25) -> list[int]:
    """Values around every integer the policy compares against (n-1, n, n+1), plus 0; capped."""
    vals = {0}
    for n in constants:
        vals.update(x for x in (n - 1, n, n + 1) if x >= 0)
    return sorted(vals)[:limit]
