"""Deterministic YOG -> plain-English readback.

Built from the parsed program (never from the LLM) so it is faithful: every clause is rendered, none dropped,
nothing invented. This is what the human reads before pressing Approve.
"""
from pydantic import BaseModel

from app.engine.adapter import EngineAdapter

OPS = {"==": "is", "!=": "is not", "<": "is below", "<=": "is at most", ">": "is above", ">=": "is at least"}
PLACEHOLDER = "placeholder"
INPUT_HELP = {
    "hour": "the current hour of day (0-23)",
    "day": "the current day of the week",
    "arg": "the arguments of the tool call",
}


class ClauseReadback(BaseModel):
    kind: str            # allow | deny | rule | fact
    line: int
    text: str


class ActionReadback(BaseModel):
    action: str          # e.g. "unlock door"
    predicate: str       # e.g. "can_unlock_door"
    allow: list[str]
    deny: list[str]


class Readback(BaseModel):
    actions: list[ActionReadback]
    definitions: list[str]
    facts: list[str]
    inputs: list[str]
    notes: list[str]
    clauses: list[ClauseReadback]      # flat, in source order: covers EVERY clause and fact


def _t(term: dict) -> str:
    return term["var"].split("#")[0] if "var" in term else str(term["const"])


def _atom(a: dict) -> str:
    p, args = a["pred"], [_t(x) for x in a["args"]]
    if p == "role" and len(args) == 2:
        return f"{args[0]} has the role {args[1]}"
    if p == "hour" and len(args) == 2 and args[0] == "now":
        return f"the current hour is {args[1]}"
    if p == "day" and len(args) == 2 and args[0] == "now":
        return f"the current day is {args[1]}"
    if p == "arg" and len(args) == 3:
        return f"the '{args[1]}' given to {args[0]} is {args[2]}"
    if p == "environment" and len(args) == 2:
        return f"{args[0]} is in the {args[1]} environment"
    if p == "owner" and len(args) == 2:
        return f"{args[1]} owns {args[0]}"
    if p == "location" and len(args) == 2:
        return f"{args[0]} is located in {args[1]}"
    if p == "approved" and len(args) == 2:
        return f"approval for {args[0]} is '{args[1]}'"
    if len(args) == 1:
        return f"{p.replace('_', ' ')}: {args[0]}"
    return f"{p.replace('_', ' ')}({', '.join(args)})"


def _goal(g: dict) -> str:
    if g["type"] == "not":
        return f"it is NOT the case that {_goal(g['atom'])}"
    if g["type"] == "cmp":
        return f"{_t(g['lhs'])} {OPS[g['op']]} {_t(g['rhs'])}"
    return _atom(g)


def _body(body: list[dict]) -> str:
    return " AND ".join(_goal(g) for g in body)


def _action_name(pred: str) -> str:
    return (pred[4:] if pred.startswith("can_") else pred).replace("_", " ")


def explain(adapter: EngineAdapter, policy: str) -> Readback:
    """Raises EngineError if the policy does not compile."""
    info = adapter.program_info(policy)
    clauses: list[ClauseReadback] = []
    facts: list[str] = []
    definitions: list[str] = []
    inputs: list[str] = []
    actions: dict[str, ActionReadback] = {}
    items: list[tuple[int, ClauseReadback]] = []

    for f in info["facts"]:
        args = [_t(a) for a in f["args"]]
        if PLACEHOLDER in args:
            name = f["pred"]
            inputs.append(f"{name}: {INPUT_HELP.get(name, 'supplied with each request')}")
            items.append((f["line"], ClauseReadback(kind="fact", line=f["line"],
                          text=f"(declares that '{name}' is supplied with each request)")))
            continue
        text = _atom({"pred": f["pred"], "args": f["args"]})
        facts.append(text)
        items.append((f["line"], ClauseReadback(kind="fact", line=f["line"], text=f"Fact: {text}.")))

    for c in info["clauses"]:
        head = c["head"]
        args = [_t(a) for a in head["args"]]
        body = _body(c["body"])
        if c["kind"] == "rule":
            text = f"Definition: {_atom(head)} when {body}."
            definitions.append(text)
        else:
            act = actions.setdefault(head["pred"], ActionReadback(
                action=_action_name(head["pred"]), predicate=head["pred"], allow=[], deny=[]))
            who = f"{args[0]} to {_action_name(head['pred'])} {args[1]}" if len(args) == 2 else _atom(head)
            verb = "ALLOW" if c["kind"] == "allow" else "DENY"
            text = f"{verb} {who} when {body}."
            (act.allow if c["kind"] == "allow" else act.deny).append(text)
        items.append((c["line"], ClauseReadback(kind=c["kind"], line=c["line"], text=text)))

    clauses = [c for _, c in sorted(items, key=lambda x: x[0])]
    notes = ["If an ALLOW rule and a DENY rule both match a request, DENY wins.",
             "If no ALLOW rule matches a request, it is denied by default.",
             "Several rules for the same action are alternatives (any one of them can match)."]
    if inputs:
        notes.append("Missing per-request information means a rule that needs it does not match: an ALLOW "
                     "needing it will not grant, but a DENY needing it will not block.")
    return Readback(actions=list(actions.values()), definitions=definitions, facts=facts,
                    inputs=sorted(set(inputs)), notes=notes, clauses=clauses)
