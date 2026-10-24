"""Deterministic tool extraction from a parsed Python module. Never executes the code."""
import ast

from app.core.models import DetectResult, Param, Tool
from app.core.pyast import const_value
from app.detect.detector import SchemaTool, scan_mcp, scan_schema_tools, tool_decorator_base
from app.extract.hints import hints_from_body, hints_from_name, ordered

FuncDef = ast.FunctionDef | ast.AsyncFunctionDef


def _params(fn: FuncDef) -> list[Param]:
    a = fn.args
    positional = a.posonlyargs + a.args
    defaults: list[ast.expr | None] = [None] * (len(positional) - len(a.defaults)) + list(a.defaults)
    params = [(arg, d) for arg, d in zip(positional, defaults)]
    params += [(arg, d) for arg, d in zip(a.kwonlyargs, a.kw_defaults)]
    out = []
    for arg, default in params:
        if arg.arg in ("self", "cls"):
            continue
        out.append(Param(
            name=arg.arg,
            type_hint=ast.unparse(arg.annotation) if arg.annotation else None,
            default=ast.unparse(default) if default is not None else None,
        ))
    return out


def _decorator_tool_name(dec: ast.AST, default: str) -> str:
    """`@mcp.tool(name="x")` renames the tool; otherwise the function name is used."""
    if isinstance(dec, ast.Call):
        for kw in dec.keywords:
            if kw.arg == "name":
                v = const_value(kw.value)
                if isinstance(v, str):
                    return v
        if dec.args:
            v = const_value(dec.args[0])
            if isinstance(v, str):
                return v
    return default


def _tool_from_function(fn: FuncDef, name: str) -> Tool:
    hints = hints_from_name(name) | hints_from_name(fn.name) | hints_from_body(fn)
    return Tool(name=name, params=_params(fn), docstring=ast.get_docstring(fn),
                source_line=fn.lineno, side_effect_hints=ordered(hints))


def _functions(tree: ast.Module) -> list[FuncDef]:
    return [n for n in ast.walk(tree) if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef))]


def extract_mcp_tools(tree: ast.Module) -> list[Tool]:
    info = scan_mcp(tree)
    tools: list[Tool] = []
    for fn in sorted(_functions(tree), key=lambda f: f.lineno):
        for dec in fn.decorator_list:
            base = tool_decorator_base(dec)
            if base is None:
                continue
            if dec.lineno in info.tool_decorator_lines:
                tools.append(_tool_from_function(fn, _decorator_tool_name(dec, fn.name)))
                break
    return tools


def _schema_params(st: SchemaTool) -> list[Param]:
    out = []
    for pname, spec in st.properties.items():
        hint = spec.get("type") if isinstance(spec, dict) else None
        out.append(Param(name=str(pname), type_hint=hint if isinstance(hint, str) else None))
    return out


def extract_schema_tools(tree: ast.Module) -> list[Tool]:
    impls = {f.name: f for f in _functions(tree)}
    tools = []
    for st in scan_schema_tools(tree):
        hints = hints_from_name(st.name)
        if st.name in impls:                       # a local implementation exists: look inside it too
            hints |= hints_from_body(impls[st.name])
        tools.append(Tool(name=st.name, params=_schema_params(st), docstring=st.description,
                          source_line=st.lineno, side_effect_hints=ordered(hints)))
    return tools


def extract_tools(tree: ast.Module, detected: DetectResult) -> list[Tool]:
    if detected.kind == "mcp_server":
        return extract_mcp_tools(tree)
    if detected.kind == "function_calling_agent":
        return extract_schema_tools(tree)
    return []


def list_candidates(tree: ast.Module) -> list[Tool]:
    """Every top-level function, for the manual 'pick the tools yourself' path when kind is unknown."""
    return [_tool_from_function(n, n.name) for n in tree.body
            if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef)) and not n.name.startswith("_")]
