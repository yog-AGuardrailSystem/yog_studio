"""The team's all_examples.yog (vendored at examples/team/), split into one standalone program per GROUP.

The file is one program whose groups use distinct name prefixes so they can coexist. Splitting it lets Studio load a
single group into the editor. tests/test_team_examples.py proves each group alone gives the same decisions as the
whole file, which also checks the team's own warning about predicate names colliding across groups.
"""
import re
from functools import lru_cache

from pydantic import BaseModel

from app.core.config import EXAMPLES_DIR
from app.core.policy_graph import PolicyGraph, build_graph

TEAM_FILE = EXAMPLES_DIR / "team" / "all_examples.yog"

_RULE_LINE = re.compile(r"^# =+\s*$")
_HEADER = re.compile(r"^# GROUP (?P<id>[A-Z](?:/[A-Z])*)\s*(?:[—-]\s*(?P<title>.*))?$")
_REFS = re.compile(r"\s*\((?:[^()]*\.md[^()]*)\)\s*$")          # "(examples.md Ex2, ...)" = the team's source-doc refs

# One plain-English line per group: what the policy says. Hand-written from the policies themselves.
ENGLISH = {
    "A": "Only admins may delete from a database.",
    "B": "Developers may deploy, but only to staging.",
    "C": "Members of the team that owns a database may modify it.",
    "D": "Deleting in production needs all three: the admin role, a production environment and finance ownership.",
    "E": "Only admins may read a file.",
    "F": "Admins may email anyone; support staff may email only internal addresses.",
    "G": "Admins may update any configuration; devops may update only staging configuration.",
    "H": "Admins may create any user; HR bots may create users only in non-technical departments.",
    "I": "Finance admins may transfer freely; customers only up to their own limit (the amount arrives with each request).",
    "J": "Admins may run any command; sandboxed agents may run only safe commands.",
    "K": "Admins may upload anything; analysts may upload only non-confidential files to staging.",
    "L": "Admins may call any API; researchers only approved research domains.",
    "M/N/O/P/Q": "Single-role gates: each of five actions needs one specific role.",
    "R": "Employees may access documents, except confidential ones (a deny overrides an allow).",
}
TITLE_FALLBACK = {"M/N/O/P/Q": "single-role gates"}


class TeamGroup(BaseModel):
    id: str
    title: str
    english: str
    source: str                 # a standalone, runnable YOG program (header comments included)
    queries: int
    uses_context: bool          # needs per-request context facts (group I): not runnable with `query` alone
    graph: PolicyGraph | None = None    # what the policy contains (facts, rules, decisions, who feeds whom), for the card diagram


def _display_title(raw: str | None, gid: str) -> str:
    title = _REFS.sub("", (raw or "").strip()).strip()
    if ".md" in title:                       # the header was only a reference to the team's source doc
        title = ""
    return title or TITLE_FALLBACK.get(gid, f"group {gid}")


@lru_cache(maxsize=1)
def _graph(source: str) -> PolicyGraph | None:
    from app.engine.adapter import EngineError
    from app.engine.python_prototype import PythonPrototypeAdapter     # structure always comes from the reference parser
    try:
        return build_graph(PythonPrototypeAdapter().program_info(source))
    except EngineError:
        return None


def load_groups() -> tuple[TeamGroup, ...]:
    lines = TEAM_FILE.read_text(encoding="utf-8").splitlines()
    heads: list[tuple[int, str, str | None]] = []          # (index of the opening ==== line, id, raw title)
    for i, line in enumerate(lines):
        m = _HEADER.match(line)
        if m and i > 0 and _RULE_LINE.match(lines[i - 1]):
            heads.append((i - 1, m.group("id"), m.group("title")))
    groups: list[TeamGroup] = []
    for n, (start, gid, raw_title) in enumerate(heads):
        end = heads[n + 1][0] if n + 1 < len(heads) else len(lines)
        body = "\n".join(lines[start:end]).rstrip() + "\n"
        code_lines = [ln for ln in body.splitlines() if ln.strip() and not ln.lstrip().startswith("#")]
        groups.append(TeamGroup(
            id=gid,
            title=_display_title(raw_title, gid),
            english=ENGLISH.get(gid, ""),
            source=body,
            queries=sum(1 for ln in code_lines if ln.lstrip().startswith("query ")),
            uses_context=gid == "I",
            graph=_graph(body),
        ))
    return tuple(groups)
