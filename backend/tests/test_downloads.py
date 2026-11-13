"""/downloads: the yogc packages for the /download page. Served only by exact manifest name."""
import hashlib
import json
import shutil
import subprocess
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app.core.config import REPO_ROOT
from app.main import app

client = TestClient(app)


@pytest.fixture()
def built(tmp_path, monkeypatch):
    """A downloads folder shaped like the real build (tiny fake files, real manifest + checksums)."""
    files = {"yog-setup-windows-x64.exe": b"MZ installer", "yog-windows-x64.zip": b"PK zip", "yog-linux-x64.tar.gz": b"gz"}
    entries = []
    for name, data in files.items():
        (tmp_path / name).write_bytes(data)
        entries.append({"name": name, "platform": "windows" if "windows" in name else "linux", "kind": "x", "label": name,
                        "size": len(data), "sha256": hashlib.sha256(data).hexdigest()})
    (tmp_path / "manifest.json").write_text(json.dumps({"engine_commit": "200e481", "built_at": "now", "files": entries}))
    (tmp_path / "SHA256SUMS.txt").write_text("".join(f"{e['sha256']}  {e['name']}\n" for e in entries))
    (tmp_path / "secret.txt").write_text("not listed")
    monkeypatch.setenv("YOG_DOWNLOADS_DIR", str(tmp_path))
    return tmp_path, files


def test_manifest_lists_the_three_packages_with_urls(built):
    m = client.get("/downloads").json()
    assert m["available"] and m["engine_commit"] == "200e481"
    assert [f["name"] for f in m["files"]] == ["yog-setup-windows-x64.exe", "yog-windows-x64.zip", "yog-linux-x64.tar.gz"]
    assert all(f["url"] == f"/api/downloads/{f['name']}" for f in m["files"])
    assert m["checksums_url"] == "/api/downloads/SHA256SUMS.txt"


def test_a_listed_file_downloads_as_an_attachment_with_matching_checksum(built):
    folder, files = built
    r = client.get("/downloads/yog-setup-windows-x64.exe")
    assert r.status_code == 200 and r.content == files["yog-setup-windows-x64.exe"]
    assert 'attachment; filename="yog-setup-windows-x64.exe"' in r.headers["content-disposition"]
    assert r.headers["x-content-type-options"] == "nosniff"
    want = next(f for f in client.get("/downloads").json()["files"] if f["name"] == "yog-setup-windows-x64.exe")["sha256"]
    assert hashlib.sha256(r.content).hexdigest() == want
    assert client.get("/downloads/SHA256SUMS.txt").text.count("\n") == 3


@pytest.mark.parametrize("name", ["secret.txt", "manifest.json", "..%2Fmanifest.json", "%2E%2E%2F%2E%2E%2Fetc%2Fpasswd",
                                  "yog-setup-windows-x64.exe.bak"])
def test_anything_not_in_the_manifest_is_404(built, name):
    assert client.get(f"/downloads/{name}").status_code in (404, 405)


def test_without_a_build_the_page_is_told_how_to_build(tmp_path, monkeypatch):
    monkeypatch.setenv("YOG_DOWNLOADS_DIR", str(tmp_path / "missing"))
    m = client.get("/downloads").json()
    assert m["available"] is False and "build_downloads.sh" in m["note"] and m["files"] == []
    assert client.get("/downloads/yog-windows-x64.zip").status_code == 404


@pytest.mark.skipif(not all(shutil.which(t) for t in ("gcc", "x86_64-w64-mingw32-gcc", "makensis", "zip")),
                    reason="needs gcc, mingw-w64, NSIS and zip (the Docker build has them)")
def test_build_script_produces_working_packages(tmp_path):
    subprocess.run(["bash", str(REPO_ROOT / "scripts" / "build_downloads.sh"), str(tmp_path)], check=True, timeout=600)
    m = json.loads((tmp_path / "manifest.json").read_text())
    for f in m["files"]:
        data = (tmp_path / f["name"]).read_bytes()
        assert hashlib.sha256(data).hexdigest() == f["sha256"] and len(data) == f["size"]
    assert (tmp_path / "yog-setup-windows-x64.exe").read_bytes()[:2] == b"MZ"
    subprocess.run(["tar", "-xzf", str(tmp_path / "yog-linux-x64.tar.gz"), "-C", str(tmp_path)], check=True)
    out = subprocess.run([str(tmp_path / "yog-linux-x64" / "yogc"), "check", str(tmp_path / "yog-linux-x64" / "policy.yog"),
                          "alice", "can_delete", "database_1"], capture_output=True, text=True)
    assert out.returncode == 0 and out.stdout.startswith("ALLOW|")
