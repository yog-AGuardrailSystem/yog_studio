"""Tiny file store for APPROVED policies: <id>.yog + <id>.json. No database (CLAUDE.md principle 7)."""
import hashlib
import json
import re
from datetime import datetime, timezone
from pathlib import Path

from pydantic import BaseModel, Field

from app.core.config import DATA_DIR

ID_RE = re.compile(r"^p-\d{14}-[0-9a-f]{8}$")


class PolicyRecord(BaseModel):
    id: str
    approved_at: str
    english_rules: list[str] = Field(default_factory=list)
    retrieved_examples: list[str] = Field(default_factory=list)
    attempts: int = 0
    readback: list[str] = Field(default_factory=list)       # one line per clause, as the human saw it
    evaluation: dict | None = None                          # scenario summary shown at approval (W6)
    yog_source: str = ""


class PolicyStore:
    def __init__(self, directory: Path | None = None) -> None:
        self.dir = directory or (DATA_DIR / "policies")

    def save(self, yog_source: str, **meta) -> PolicyRecord:
        self.dir.mkdir(parents=True, exist_ok=True)
        now = datetime.now(timezone.utc)
        digest = hashlib.sha256(yog_source.encode()).hexdigest()[:8]
        pid = f"p-{now:%Y%m%d%H%M%S}-{digest}"
        rec = PolicyRecord(id=pid, approved_at=now.isoformat(), yog_source=yog_source, **meta)
        (self.dir / f"{pid}.yog").write_text(yog_source, encoding="utf-8")
        (self.dir / f"{pid}.json").write_text(rec.model_dump_json(indent=2), encoding="utf-8")
        return rec

    def get(self, pid: str) -> PolicyRecord | None:
        if not ID_RE.match(pid):                    # also blocks path traversal
            return None
        f = self.dir / f"{pid}.json"
        if not f.exists():
            return None
        return PolicyRecord(**json.loads(f.read_text(encoding="utf-8")))

    def list(self) -> list[PolicyRecord]:
        if not self.dir.exists():
            return []
        recs = [PolicyRecord(**json.loads(f.read_text(encoding="utf-8"))) for f in self.dir.glob("p-*.json")]
        return sorted(recs, key=lambda r: r.approved_at, reverse=True)
