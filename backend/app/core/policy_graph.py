"""The structure of one policy as a small graph, for the landing page's example cards.

Built only from `program_info()` (what the parser found), never from keyword counts: one node per predicate (fact data,
derived rule, or allow/deny decision), one edge per body atom that feeds a clause, so the picture can only show what
the policy really contains.
"""
from pydantic import BaseModel, Field


class GraphNode(BaseModel):
    id: str                            # "role/2"
    pred: str
    arity: int
    kind: str                          # "fact" | "rule" | "decision"
    count: int                         # facts, or clauses, defining it
    allow: int = 0                     # decisions: allow clauses
    deny: int = 0                      # decisions: deny clauses
    compares: int = 0                  # comparison goals (X <= Y) in the clauses that define it
    used: bool = True                  # facts/rules: is it read by any clause body?


class GraphEdge(BaseModel):
    src: str                           # node id read by the body
    dst: str                           # node id of the clause head
    negated: bool = False              # the goal is `not src(...)`
    via: str = "allow"                 # kind of clause the goal sits in: allow | deny | rule


class PolicyGraph(BaseModel):
    facts: list[GraphNode] = Field(default_factory=list)
    rules: list[GraphNode] = Field(default_factory=list)
    decisions: list[GraphNode] = Field(default_factory=list)
    edges: list[GraphEdge] = Field(default_factory=list)


def build_graph(info: dict) -> PolicyGraph:
    """`info` is EngineAdapter.program_info(): {"facts": [...], "clauses": [...]}."""
    nodes: dict[str, GraphNode] = {}

    def node(pred: str, arity: int, kind: str) -> GraphNode:
        key = f"{pred}/{arity}"
        if key not in nodes:
            nodes[key] = GraphNode(id=key, pred=pred, arity=arity, kind=kind, count=0, used=False)
        return nodes[key]

    for f in info["facts"]:
        node(f["pred"], len(f["args"]), "fact").count += 1
    for c in info["clauses"]:
        n = node(c["head"]["pred"], len(c["head"]["args"]), "rule" if c["kind"] == "rule" else "decision")
        n.count += 1
        if c["kind"] == "allow":
            n.allow += 1
        elif c["kind"] == "deny":
            n.deny += 1
    edges: dict[tuple, GraphEdge] = {}
    for c in info["clauses"]:
        dst = f"{c['head']['pred']}/{len(c['head']['args'])}"
        for g in c["body"]:
            negated = g["type"] == "not"
            atom = g["atom"] if negated else g
            if g["type"] == "cmp":
                nodes[dst].compares += 1
                continue
            src = f"{atom['pred']}/{len(atom['args'])}"
            if src in nodes:
                nodes[src].used = True
            edges.setdefault((src, dst, negated, c["kind"]), GraphEdge(src=src, dst=dst, negated=negated, via=c["kind"]))
    order = {k: i for i, k in enumerate(nodes)}                       # first appearance in the source
    pick = lambda kind: sorted((n for n in nodes.values() if n.kind == kind), key=lambda n: order[n.id])
    return PolicyGraph(facts=pick("fact"), rules=pick("rule"), decisions=pick("decision"), edges=list(edges.values()))
