"""Agent frameworks whose tools are plain decorated functions: LangChain `@tool`, the OpenAI Agents SDK `@function_tool`,
CrewAI `@tool("name")` and PydanticAI `@agent.tool`. Found from the AST only: the code is never imported or run.

A framework counts only when its package is imported AND at least one function carries its decorator, so a stray
`@tool` in an unrelated file is not enough (and the result says which lines were the evidence)."""
import ast
from dataclasses import dataclass, field

from app.core.pyast import const_value, dotted

FuncDef = ast.FunctionDef | ast.AsyncFunctionDef

# framework -> (import roots, decorator names for `from pkg import <name>`, attribute names for `agent.<name>`)
FRAMEWORKS: dict[str, tuple[tuple[str, ...], frozenset[str], frozenset[str]]] = {
    "langchain": (("langchain", "langchain_core", "langchain_community"), frozenset({"tool"}), frozenset()),
    "openai_agents": (("agents",), frozenset({"function_tool"}), frozenset()),
    "crewai": (("crewai",), frozenset({"tool"}), frozenset()),
    "pydantic_ai": (("pydantic_ai",), frozenset(), frozenset({"tool", "tool_plain"})),
}
LABELS = {"langchain": "LangChain", "openai_agents": "OpenAI Agents SDK", "crewai": "CrewAI", "pydantic_ai": "PydanticAI"}


@dataclass
class FrameworkTool:
    name: str
    node: FuncDef
    dec_line: int


@dataclass
class FrameworkScan:
    framework: str | None = None
    import_lines: list[int] = field(default_factory=list)
    tools: list[FrameworkTool] = field(default_factory=list)


def _imports(tree: ast.Module, roots: tuple[str, ...]) -> tuple[list[int], dict[str, str], set[str]]:
    """(import lines, bound name -> original name for `from pkg import x [as y]`, names bound to the package itself)."""
    lines: list[int] = []
    names: dict[str, str] = {}
    modules: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom) and node.module and node.module.split(".")[0] in roots and node.level == 0:
            lines.append(node.lineno)
            for a in node.names:
                names[a.asname or a.name] = a.name
        elif isinstance(node, ast.Import):
            for a in node.names:
                if a.name.split(".")[0] in roots:
                    lines.append(node.lineno)
                    modules.add(a.asname or a.name.split(".")[0])
    return sorted(set(lines)), names, modules


def _decorator_name(dec: ast.AST, default: str) -> str:
    """`@tool("my name")` / `@tool(name="x")` / `@function_tool(name_override="x")` rename the tool."""
    if isinstance(dec, ast.Call):
        for kw in dec.keywords:
            if kw.arg in ("name", "name_override"):
                v = const_value(kw.value)
                if isinstance(v, str) and v.strip():
                    return v.strip()
        if dec.args:
            v = const_value(dec.args[0])
            if isinstance(v, str) and v.strip():
                return v.strip()
    return default


def _agent_vars(tree: ast.Module, names: dict[str, str], modules: set[str]) -> set[str]:
    out: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Assign) and isinstance(node.value, ast.Call):
            fn = dotted(node.value.func) or ""
            is_agent = names.get(fn) == "Agent" or (fn.split(".")[0] in modules and fn.split(".")[-1] == "Agent")
            if is_agent:
                out.update(t.id for t in node.targets if isinstance(t, ast.Name))
    return out


def scan_frameworks(tree: ast.Module) -> FrameworkScan:
    best = FrameworkScan()
    for fw, (roots, dec_names, attr_names) in FRAMEWORKS.items():
        lines, names, modules = _imports(tree, roots)
        if not lines:
            continue
        agents = _agent_vars(tree, names, modules) if attr_names else set()
        found: list[FrameworkTool] = []
        for fn in sorted((n for n in ast.walk(tree) if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef))), key=lambda f: f.lineno):
            for dec in fn.decorator_list:
                target = dec.func if isinstance(dec, ast.Call) else dec
                hit = False
                if isinstance(target, ast.Name) and names.get(target.id) in dec_names:
                    hit = True
                elif isinstance(target, ast.Attribute):
                    base = dotted(target.value)
                    if target.attr in attr_names and base in agents:
                        hit = True
                    elif target.attr in dec_names and base in modules:
                        hit = True
                if hit:
                    found.append(FrameworkTool(_decorator_name(dec, fn.name), fn, dec.lineno))
                    break
        if found and len(found) > len(best.tools):
            best = FrameworkScan(framework=fw, import_lines=lines, tools=found)
    return best
