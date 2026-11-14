"""The /download page's files: yogc for Windows (installer + zip) and Linux, built into the Docker image from the
vendored engine by scripts/build_downloads.sh (Dockerfile stage `dist`).

Only the files named in the build's manifest.json are served, by exact name, so no request can reach any other path.
Without the folder (local development) the manifest says `available: false` and how to build it.
"""
import json
import os
from pathlib import Path

from fastapi import APIRouter, HTTPException
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field

from app.core.config import DATA_DIR

router = APIRouter()

CONTENT_TYPES = {".exe": "application/vnd.microsoft.portable-executable", ".zip": "application/zip",
                 ".gz": "application/gzip", ".txt": "text/plain; charset=utf-8"}
BUILD_HINT = ("Downloads are built into Studio's production image. To build them locally run "
              "scripts/build_downloads.sh backend/data/downloads (needs gcc, mingw-w64 and NSIS, or use the Docker "
              "command at the top of that script).")


class DownloadFile(BaseModel):
    name: str
    platform: str
    kind: str
    label: str
    size: int
    sha256: str
    url: str = ""


class DownloadManifest(BaseModel):
    available: bool
    engine_commit: str | None = None
    built_at: str | None = None
    files: list[DownloadFile] = Field(default_factory=list)
    checksums_url: str | None = None
    note: str | None = None


def downloads_dir() -> Path:
    return Path(os.environ.get("YOG_DOWNLOADS_DIR") or DATA_DIR / "downloads")


def _manifest() -> DownloadManifest:
    folder = downloads_dir()
    try:
        raw = json.loads((folder / "manifest.json").read_text(encoding="utf-8"))
        files = [DownloadFile(**f) for f in raw["files"]]
    except (OSError, ValueError, KeyError, TypeError):
        return DownloadManifest(available=False, note=BUILD_HINT)
    files = [f.model_copy(update={"url": f"/api/downloads/{f.name}"}) for f in files if (folder / f.name).is_file()]
    if not files:
        return DownloadManifest(available=False, note=BUILD_HINT)
    sums = "/api/downloads/SHA256SUMS.txt" if (folder / "SHA256SUMS.txt").is_file() else None
    return DownloadManifest(available=True, engine_commit=raw.get("engine_commit"), built_at=raw.get("built_at"),
                            files=files, checksums_url=sums)


@router.get("/downloads", response_model=DownloadManifest)
def list_downloads() -> DownloadManifest:
    return _manifest()


@router.get("/downloads/{name}")
def get_download(name: str) -> FileResponse:
    m = _manifest()
    allowed = {f.name for f in m.files} | ({"SHA256SUMS.txt"} if m.checksums_url else set())
    if name not in allowed:                         # exact names from the manifest only: no paths, no other files
        raise HTTPException(status_code=404, detail="no such download")
    path = downloads_dir() / name
    kind = CONTENT_TYPES.get(path.suffix, "application/octet-stream")
    return FileResponse(path, media_type=kind, filename=name if name != "SHA256SUMS.txt" else None,
                        headers={"X-Content-Type-Options": "nosniff"})
