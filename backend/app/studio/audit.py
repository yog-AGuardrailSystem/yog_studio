"""Audit log: one JSON line per decision the device guard made, each carrying the hash of the line before it, so any
edit, deletion or reordering is detectable (the chain stops matching). Per visitor, bounded, append-only.

When the file grows past MAX_LINES the oldest DROP lines are removed and the hash of the last removed line becomes the
new anchor, so the rest of the chain still verifies."""
import csv
import hashlib
import io
import json
import os
import threading
from pathlib import Path

GENESIS = "0" * 64
MAX_LINES = 2000
DROP = 500
_lock = threading.Lock()

COLUMNS = ["seq", "at", "sim_day", "sim_hour", "tool", "args", "guarded", "decision", "reason", "executed", "policy_id", "hash"]


def _canon(entry: dict) -> str:
    return json.dumps(entry, sort_keys=True, separators=(",", ":"), ensure_ascii=True, default=str)


def _digest(prev: str, entry: dict) -> str:
    return hashlib.sha256((prev + _canon(entry)).encode("ascii")).hexdigest()


class AuditLog:
    def __init__(self, directory: Path) -> None:
        self.path = directory / "audit.jsonl"
        self.meta = directory / "audit.meta.json"

    # -- storage ------------------------------------------------------------------
    def _anchor(self) -> str:
        try:
            return json.loads(self.meta.read_text(encoding="utf-8")).get("anchor", GENESIS)
        except (OSError, ValueError):
            return GENESIS

    def _records(self) -> list[dict]:
        if not self.path.exists():
            return []
        out = []
        for ln in self.path.read_text(encoding="utf-8").split("\n"):
            if not ln.strip():
                continue
            try:
                out.append(json.loads(ln))
            except ValueError:
                out.append({"_broken": ln[:80]})
        return out

    @staticmethod
    def _write(path: Path, text: str) -> None:
        tmp = path.with_suffix(path.suffix + ".tmp")
        tmp.write_text(text, encoding="utf-8")
        os.replace(tmp, path)

    # -- public ---------------------------------------------------------------------
    def append(self, entry: dict) -> dict:
        with _lock:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            recs = self._records()
            prev = recs[-1].get("hash", GENESIS) if recs else self._anchor()
            seq = (recs[-1].get("seq", 0) + 1) if recs else 1
            body = {**entry, "seq": seq}
            rec = {**body, "prev": prev, "hash": _digest(prev, body)}
            recs.append(rec)
            if len(recs) > MAX_LINES:
                dropped, recs = recs[:DROP], recs[DROP:]
                self._write(self.meta, json.dumps({"anchor": dropped[-1].get("hash", GENESIS)}))
            self._write(self.path, "\n".join(json.dumps(r, sort_keys=True, ensure_ascii=True, default=str) for r in recs) + "\n")
            return rec

    def read(self, limit: int = 200, decision: str | None = None, tool: str | None = None, q: str | None = None) -> list[dict]:
        recs = [r for r in self._records() if "_broken" not in r]
        if decision:
            recs = [r for r in recs if str(r.get("decision", "")).upper() == decision.upper()]
        if tool:
            recs = [r for r in recs if r.get("tool") == tool]
        if q:
            needle = q.lower()
            recs = [r for r in recs if needle in json.dumps(r, default=str).lower()]
        return list(reversed(recs))[: max(1, min(limit, 1000))]

    def count(self) -> int:
        return len(self._records())

    def verify(self) -> dict:
        """Recompute the chain. `ok` False means the file no longer matches what was written."""
        recs = self._records()
        prev = self._anchor()
        for i, r in enumerate(recs):
            if "_broken" in r:
                return {"ok": False, "checked": i, "total": len(recs), "bad_seq": None, "problem": "a line is not valid JSON"}
            body = {k: v for k, v in r.items() if k not in ("prev", "hash")}
            if r.get("prev") != prev or r.get("hash") != _digest(prev, body):
                return {"ok": False, "checked": i, "total": len(recs), "bad_seq": r.get("seq"),
                        "problem": f"entry {r.get('seq')} does not match the entry before it"}
            prev = r["hash"]
        return {"ok": True, "checked": len(recs), "total": len(recs), "bad_seq": None, "problem": ""}


def _safe_cell(v) -> str:
    """CSV cell that a spreadsheet will not run as a formula."""
    s = v if isinstance(v, str) else json.dumps(v, default=str) if isinstance(v, (dict, list)) else str(v)
    return "'" + s if s[:1] in ("=", "+", "-", "@", "\t", "\r") else s


def to_csv(records: list[dict]) -> str:
    buf = io.StringIO()
    w = csv.writer(buf)
    w.writerow(COLUMNS)
    for r in records:
        w.writerow([_safe_cell(r.get(c, "")) for c in COLUMNS])
    return buf.getvalue()
