"""Deterministic detector: what kind of agent file is this? (AST + pattern rules, no LLM.)

Scores are additive and documented so the confidence number is explainable:
  MCP server            import 0.35 + server instance 0.25 + @x.tool decorators 0.35  (max 0.95)
  function-calling      tools schema 0.60 + SDK import 0.20 + `tools=` kwarg on a call 0.20
A kind needs >= 0.5. Below that the answer is `unknown` -- never a silent guess.
"""
import ast
from dataclasses import dataclass, field

from app.core.models import DetectResult
from app.core.pyast import const_value, dotted, evidence

THRESHOLD = 0.5
MCP_CTORS = {"FastMCP", "Server", "MCPServer", "FastMCPServer"}
LLM_SDKS = {"openai", "anthropic", "litellm", "groq", "mistralai", "google"}
MAX_EVIDENCE = 15


def is_mcp_module(name: str) -> bool:
    return name.split(".")[0] in ("mcp", "fastmcp")


@dataclass
class McpInfo:
    import_lines: list[int] = field(default_factory=list)
    imported_names: dict[str, str] = field(default_factory=dict)   # bound name -> original, from `from mcp... import X [as Y]`
    module_aliases: set[str] = field(default_factory=set)   # names bound by `import mcp.x as fm`
    instance_vars: set[str] = field(default_factory=set)
    instance_lines: list[int] = field(default_factory=list)
    tool_decorator_lines: list[int] = field(default_factory=list)   # `@x.tool` lines


def tool_decorator_base(dec: ast.AST) -> ast.expr | None:
    """`@x.tool`, `@x.tool(...)` -> returns the base expression `x`; else None."""
    target = dec.func if isinstance(dec, ast.Call) else dec
    if isinstance(target, ast.Attribute) and target.attr == "tool":
        return target.value
    return None


def scan_mcp(tree: ast.Module) -> McpInfo:
    info = McpInfo()
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom) and node.module and is_mcp_module(node.module):
            info.import_lines.append(node.lineno)
            for a in node.names:
                info.imported_names[a.asname or a.name] = a.name
        elif isinstance(node, ast.Import):
            for a in node.names:
                if is_mcp_module(a.name):
                    info.import_lines.append(node.lineno)
                    info.module_aliases.add(a.asname or a.name.split(".")[0])

    for node in ast.walk(tree):
        value, targets = None, []
        if isinstance(node, ast.Assign):
            value, targets = node.value, node.targets
        elif isinstance(node, ast.AnnAssign) and node.value is not None:
            value, targets = node.value, [node.target]
        if isinstance(value, ast.Call):
            name = dotted(value.func) or ""
            root, last = name.split(".")[0], name.split(".")[-1]
            if "." in name:
                is_ctor = root in info.module_aliases and last in MCP_CTORS
            else:
                is_ctor = info.imported_names.get(name) in MCP_CTORS or name == "FastMCP"
            if is_ctor:
                for t in targets:
                    if isinstance(t, ast.Name):
                        info.instance_vars.add(t.id)
                info.instance_lines.append(node.lineno)

    has_signal = bool(info.import_lines)
    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            for dec in node.decorator_list:
                base = tool_decorator_base(dec)
                if base is None:
                    continue
                b = dotted(base)
                if (b is not None and b in info.instance_vars) or has_signal:
                    info.tool_decorator_lines.append(dec.lineno)
    return info


# ---------------------------------------------------------------- function-calling

@dataclass
class SchemaTool:
    name: str
    description: str | None
    properties: dict
    lineno: int


def _as_schema_tool(node: ast.Dict) -> SchemaTool | None:
    d = const_value(node)
    if not isinstance(d, dict):
        return None
    # OpenAI style: {"type": "function", "function": {"name", "description", "parameters"}}
    fn = d.get("function")
    if d.get("type") == "function" and isinstance(fn, dict) and isinstance(fn.get("name"), str):
        params = fn.get("parameters")
        props = params.get("properties", {}) if isinstance(params, dict) else {}
        return SchemaTool(fn["name"], _str_or_none(fn.get("description")),
                          props if isinstance(props, dict) else {}, node.lineno)
    # Anthropic style: {"name", "description", "input_schema"}
    if isinstance(d.get("name"), str) and isinstance(d.get("input_schema"), dict):
        props = d["input_schema"].get("properties", {})
        return SchemaTool(d["name"], _str_or_none(d.get("description")),
                          props if isinstance(props, dict) else {}, node.lineno)
    return None


def _str_or_none(v) -> str | None:
    return v if isinstance(v, str) else None


def scan_schema_tools(tree: ast.Module) -> list[SchemaTool]:
    found: dict[str, SchemaTool] = {}
    for node in ast.walk(tree):
        if isinstance(node, (ast.List, ast.Tuple)):
            for el in node.elts:
                if isinstance(el, ast.Dict):
                    st = _as_schema_tool(el)
                    if st and st.name not in found:
                        found[st.name] = st
    return list(found.values())


def _sdk_import_lines(tree: ast.Module) -> list[int]:
    lines = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import) and any(a.name.split(".")[0] in LLM_SDKS for a in node.names):
            lines.append(node.lineno)
        elif isinstance(node, ast.ImportFrom) and node.module and node.module.split(".")[0] in LLM_SDKS:
            lines.append(node.lineno)
    return lines


def _tools_kwarg_lines(tree: ast.Module) -> list[int]:
    return [kw.value.lineno if hasattr(kw.value, "lineno") else node.lineno
            for node in ast.walk(tree) if isinstance(node, ast.Call)
            for kw in node.keywords if kw.arg == "tools"]


# ---------------------------------------------------------------- public

def _cap(items: list[str]) -> list[str]:
    if len(items) <= MAX_EVIDENCE:
        return items
    return items[:MAX_EVIDENCE] + [f"... and {len(items) - MAX_EVIDENCE} more"]


def detect(tree: ast.Module, source: str) -> DetectResult:
    lines = source.splitlines()

    mcp = scan_mcp(tree)
    mcp_score, mcp_ev = 0.0, []
    if mcp.import_lines:
        mcp_score += 0.35
        mcp_ev += [evidence(lines, n) for n in sorted(set(mcp.import_lines))]
    if mcp.instance_lines:
        mcp_score += 0.25
        mcp_ev += [evidence(lines, n) for n in sorted(set(mcp.instance_lines))]
    if mcp.tool_decorator_lines:
        mcp_score += 0.35
        mcp_ev += [evidence(lines, n) for n in sorted(set(mcp.tool_decorator_lines))]

    schemas = scan_schema_tools(tree)
    fc_score, fc_ev = 0.0, []
    if schemas:
        fc_score += 0.6
        fc_ev += [f"line {s.lineno}: tool schema '{s.name}'" for s in schemas]
    sdk = _sdk_import_lines(tree)
    if sdk:
        fc_score += 0.2
        fc_ev += [evidence(lines, n) for n in sorted(set(sdk))]
    kw = _tools_kwarg_lines(tree)
    if kw:
        fc_score += 0.2
        fc_ev += [evidence(lines, n) for n in sorted(set(kw))]

    if mcp_score >= THRESHOLD and mcp_score >= fc_score:
        return DetectResult(kind="mcp_server", confidence=round(mcp_score, 2), evidence=_cap(mcp_ev))
    if fc_score >= THRESHOLD:
        return DetectResult(kind="function_calling_agent", confidence=round(fc_score, 2), evidence=_cap(fc_ev))
    weak = _cap(mcp_ev + fc_ev)
    return DetectResult(kind="unknown", confidence=0.0,
                        evidence=weak or ["no MCP server or function-calling signals found"])


__all__ = ["detect", "scan_mcp", "scan_schema_tools", "McpInfo", "SchemaTool"]
