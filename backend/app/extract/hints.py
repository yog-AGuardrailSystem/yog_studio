"""Side-effect hints from tool names and the calls inside the tool body (static only)."""
import ast
import re

from app.core.pyast import dotted

NAME_KEYWORDS: dict[str, set[str]] = {
    "deletes": {"delete", "remove", "drop", "destroy", "purge", "wipe", "erase", "truncate", "rm", "clear"},
    "actuates": {"unlock", "lock", "open", "close", "set", "turn", "toggle", "start", "stop", "activate",
                 "deactivate", "trigger", "move", "enable", "disable", "arm", "disarm", "power", "reboot",
                 "restart", "deploy"},
    "network": {"send", "post", "fetch", "download", "upload", "request", "email", "publish", "notify",
                "http", "webhook", "sms"},
    "filesystem": {"write", "save", "file", "files", "path", "mkdir", "rename", "copy", "directory", "dir",
                   "backup", "read"},
    "database": {"query", "sql", "insert", "update", "db", "database", "table"},
    "shell": {"exec", "shell", "command", "cmd", "subprocess", "eval"},
    "financial": {"transfer", "pay", "payment", "charge", "refund", "withdraw", "deposit", "purchase"},
}

DELETE_CALLS = {"os.remove", "os.unlink", "os.rmdir", "os.removedirs", "shutil.rmtree"}
DELETE_ATTRS = {"unlink", "rmdir", "rmtree"}
SHELL_ROOTS = {"subprocess"}
SHELL_CALLS = {"os.system", "os.popen", "eval", "exec"}
NETWORK_ROOTS = {"requests", "httpx", "urllib", "urllib3", "aiohttp", "smtplib", "socket", "ftplib",
                 "websockets", "paramiko"}
FS_CALLS = {"open", "shutil.copy", "shutil.copyfile", "shutil.copytree", "shutil.move", "os.rename",
            "os.makedirs", "os.mkdir"}
FS_ATTRS = {"write_text", "write_bytes", "mkdir", "touch", "rename", "read_text", "read_bytes"}
DB_CALLS = {"sqlite3.connect", "psycopg2.connect", "pymysql.connect", "sqlalchemy.create_engine"}
DB_ATTRS = {"execute", "executemany", "executescript"}

ORDER = ["deletes", "actuates", "network", "filesystem", "database", "shell", "financial"]


def _tokens(name: str) -> set[str]:
    spaced = re.sub(r"(?<=[a-z0-9])(?=[A-Z])", "_", name)
    return {t for t in re.split(r"[_\W]+", spaced.lower()) if t}


def hints_from_name(name: str) -> set[str]:
    toks = _tokens(name)
    return {hint for hint, words in NAME_KEYWORDS.items() if toks & words}


def hints_from_body(fn: ast.AST) -> set[str]:
    out: set[str] = set()
    for node in ast.walk(fn):
        if not isinstance(node, ast.Call):
            continue
        name = dotted(node.func) or ""
        root = name.split(".")[0]
        attr = node.func.attr if isinstance(node.func, ast.Attribute) else None
        if name in DELETE_CALLS or attr in DELETE_ATTRS:
            out.add("deletes")
        if root in SHELL_ROOTS or name in SHELL_CALLS:
            out.add("shell")
        if root in NETWORK_ROOTS:
            out.add("network")
        if name in FS_CALLS or attr in FS_ATTRS:
            out.add("filesystem")
        if name in DB_CALLS or attr in DB_ATTRS:
            out.add("database")
    return out


def ordered(hints: set[str]) -> list[str]:
    return [h for h in ORDER if h in hints]
