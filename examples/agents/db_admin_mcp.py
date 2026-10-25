"""Database-admin MCP server. Uses an import alias to check the detector is not name-fragile."""
import sqlite3

from mcp.server.fastmcp import FastMCP as MCPServer

app = MCPServer("db-admin")
conn = sqlite3.connect("app.db")


@app.tool()
def run_query(sql: str, limit: int = 100) -> list:
    """Run a read-only SQL query."""
    cur = conn.cursor()
    cur.execute(sql)
    return cur.fetchmany(limit)


@app.tool()
def drop_table(table: str) -> str:
    """Drop a table. Irreversible."""
    conn.execute(f"DROP TABLE {table}")
    return f"dropped {table}"


@app.tool()
def backup_database(dest: str, compress: bool = True) -> str:
    """Write a backup of the database to `dest`."""
    with open(dest, "wb") as fh:
        fh.write(b"...")
    return dest
