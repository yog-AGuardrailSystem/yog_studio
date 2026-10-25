"""File-operations MCP server (FastMCP from the standalone `fastmcp` package)."""
import os
from pathlib import Path

from fastmcp import FastMCP

mcp = FastMCP(name="file-ops")


@mcp.tool
def read_file(path: str) -> str:
    """Return the text content of a file."""
    with open(path) as fh:
        return fh.read()


@mcp.tool()
def write_file(path: str, content: str, append: bool = False) -> str:
    """Write (or append) text to a file."""
    with open(path, "a" if append else "w") as fh:
        fh.write(content)
    return "ok"


@mcp.tool()
def delete_file(path: str) -> str:
    """Permanently delete a file."""
    os.remove(path)
    return "deleted"


@mcp.tool(name="list_directory")
async def ls_dir(path: str = ".") -> list[str]:
    """List the entries of a directory."""
    return sorted(p.name for p in Path(path).iterdir())
