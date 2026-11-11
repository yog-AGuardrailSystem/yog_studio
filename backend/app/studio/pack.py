"""Export Pack: one zip with everything about an approved policy, checksummed. The report is a single self-contained
HTML page. Nothing in the pack contains keys, other visitors' data, or anything the visitor did not approve."""
import hashlib
import html
import io
import json
import os
import zipfile
from datetime import datetime, timezone
from pathlib import Path

from app.core.config import ENGINE_PATH
from app.engine.adapter import EngineAdapter
from app.evaluate.evaluator import evaluate
from app.explain.explainer import explain
from app.modify.modifier import modify
from app.policies.store import PolicyRecord
from app.studio import gaps as gaps_mod
from app.studio import scorecard
from app.studio.common import Budget, policy_sha256

RUNTIME_PATH = Path(__file__).resolve().parents[1] / "modify" / "yog_runtime.py"
PLACEHOLDER_MARKER = "OFFLINE FAKE PROVIDER"


def _e(x) -> str:
    return html.escape(str(x), quote=True)


def _sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


CSS = """body{font:15px/1.5 system-ui,sans-serif;max-width:900px;margin:2rem auto;padding:0 1rem;color:#1a1a1a;background:#fff}
h1,h2{line-height:1.2}h2{margin-top:2rem;border-bottom:1px solid #ddd;padding-bottom:.2rem}
pre{background:#f5f5f5;padding:.8rem;overflow:auto;border-radius:6px}table{border-collapse:collapse;width:100%}
td,th{border:1px solid #ddd;padding:.3rem .5rem;text-align:left;font-size:13px}.good{color:#116329}.bad{color:#a40e26}.warn{color:#8a4b00}
@media (prefers-color-scheme:dark){body{background:#111;color:#eee}pre{background:#1c1c1c}td,th{border-color:#333}.good{color:#6fdd8b}.bad{color:#ff8a8a}.warn{color:#ffc266}}"""


def report_html(adapter: EngineAdapter, rec: PolicyRecord, tools: list[str] | None) -> str:
    rb = explain(adapter, rec.yog_source)
    ev = evaluate(adapter, rec.yog_source)
    g = gaps_mod.analyze(adapter, rec.yog_source, tools=tools or None, budget=Budget(6000))
    sc = scorecard.compute(adapter, rec.yog_source, tools, include_strength=True)
    parts = [f"<!doctype html><html lang='en'><head><meta charset='utf-8'><title>YOG policy report {_e(rec.id)}</title>"
             f"<style>{CSS}</style></head><body>",
             f"<h1>YOG policy report</h1><p>Policy <b>{_e(rec.id)}</b>, approved {_e(rec.approved_at)}"
             + (f". Note: {_e(rec.note)}" if rec.note else "") + ".</p>",
             f"<p>Made by YOG Studio on {_e(datetime.now(timezone.utc).isoformat(timespec='seconds'))}. "
             "The policy was approved by a person; Studio did not approve it.</p>"]
    if rec.english_rules:
        parts.append("<h2>The rules, in English</h2><ol>" + "".join(f"<li>{_e(r)}</li>" for r in rec.english_rules) + "</ol>")
    parts.append("<h2>What the policy says (read back from the parsed program)</h2><ul>"
                 + "".join(f"<li>line {c.line}: {_e(c.text)}</li>" for c in rb.clauses) + "</ul>")
    parts.append(f"<h2>The policy</h2><pre>{_e(rec.yog_source)}</pre>")
    parts.append("<h2>Scorecard</h2><table><tr><th>Check</th><th>Result</th><th>Detail</th></tr>"
                 + "".join(f"<tr><td>{_e(m.label)}</td><td class='{m.status}'>{_e(m.value or 'not measured')}</td><td>{_e(m.detail)}</td></tr>"
                           for m in sc.metrics) + f"</table><p>{_e(sc.headline)}.</p>")
    rows = ev.results[:200]
    parts.append(f"<h2>Test results ({len(ev.results)} probes, {ev.summary.unconfirmed} unconfirmed)</h2><table><tr><th>Request</th><th>Context</th><th>Decision</th><th>Reason</th></tr>"
                 + "".join(f"<tr><td>{_e(r.action)}({_e(r.actor)}, {_e(r.resource)})</td><td>{_e(', '.join(r.context))}</td>"
                           f"<td class='{'good' if r.actual == 'ALLOW' else 'bad'}'>{_e(r.actual)}</td><td>{_e(r.reason)}</td></tr>" for r in rows)
                 + "</table><p>Unconfirmed rows record what the engine did; they are not checks against your intent.</p>")
    parts.append("<h2>Gap findings</h2>" + ("<ul>" + "".join(
        f"<li><b>{_e(f.title)}</b> ({_e(f.certainty)}): {_e(f.detail)}</li>" for f in g.findings) + "</ul>" if g.findings else "<p>None.</p>"))
    parts.append("</body></html>")
    return "".join(parts)


def build(adapter: EngineAdapter, rec: PolicyRecord, *, agent_source: str | None = None, filename: str = "agent.py",
          tools: list[str] | None = None) -> tuple[bytes, dict]:
    """Returns (zip bytes, manifest). Raises ValueError for a policy that must not be exported."""
    if PLACEHOLDER_MARKER in rec.yog_source:
        raise ValueError("This policy is still the offline placeholder (copied from the nearest example, not translated). "
                         "Edit it in the workbench or generate it with a real LLM before exporting.")
    files: dict[str, bytes] = {"policy.yog": rec.yog_source.encode("utf-8")}
    files["REPORT.html"] = report_html(adapter, rec, tools).encode("utf-8")
    ev = evaluate(adapter, rec.yog_source)
    files["scenarios.json"] = json.dumps([r.model_dump() for r in ev.results], indent=2).encode("utf-8")
    pin = policy_sha256(rec.yog_source)
    if agent_source is not None:
        res = modify(agent_source, tools or None, filename)
        files[filename] = res.patched_source.encode("utf-8")
        files["yog_runtime.py"] = RUNTIME_PATH.read_bytes()
        files["yog.py"] = ENGINE_PATH.read_bytes()
        files["README.txt"] = (
            "Run your agent from this folder.\n"
            "Denied calls raise yog_runtime.YogDenied. The guard fails closed: any error means DENY.\n"
            "Optional settings (environment variables):\n"
            "  YOG_NOW=\"3,sat\"            pin the clock when testing\n"
            f"  YOG_POLICY_SHA256={pin}\n"
            "                             refuse to run if policy.yog is not exactly the approved one\n"
            "  YOG_LOG=decisions.jsonl    write every decision to a file (Trace Replay can read it)\n"
            "Self-test:  python yog_runtime.py --selftest\n").encode("utf-8")
    manifest = {
        "policy_id": rec.id, "policy_sha256": pin, "approved_at": rec.approved_at,
        "created_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "studio_commit": os.environ.get("RENDER_GIT_COMMIT") or os.environ.get("GIT_COMMIT") or "unknown",
        "files": {name: {"sha256": _sha(data), "bytes": len(data)} for name, data in sorted(files.items())},
    }
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as z:
        for name, data in files.items():
            z.writestr(name, data)
        z.writestr("manifest.json", json.dumps(manifest, indent=2))
    return buf.getvalue(), manifest
