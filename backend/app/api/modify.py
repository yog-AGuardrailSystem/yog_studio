import io
import zipfile
from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import Response
from pydantic import BaseModel, Field

from app.api.policies import get_store
from app.core.config import ENGINE_PATH
from app.core.pyast import SourceError
from app.modify.modifier import ModifyError, ModifyResult, modify
from app.policies.store import PolicyStore

router = APIRouter()
RUNTIME_PATH = Path(__file__).resolve().parents[1] / "modify" / "yog_runtime.py"


class ModifyRequest(BaseModel):
    filename: str = "agent.py"
    source: str
    tools: list[str] = Field(default_factory=list)       # empty = guard every detected tool


@router.post("/modify", response_model=ModifyResult)
def modify_script(req: ModifyRequest) -> ModifyResult:
    try:
        return modify(req.source, req.tools or None, req.filename)
    except (SourceError, ModifyError) as e:
        raise HTTPException(status_code=422, detail=str(e))


class BundleRequest(ModifyRequest):
    policy_id: str


@router.post("/modify/bundle")
def bundle(req: BundleRequest, store: PolicyStore = Depends(get_store)) -> Response:
    """Zip = patched agent + yog_runtime.py + yog.py + policy.yog. Only an APPROVED policy can be bundled."""
    rec = store.get(req.policy_id)
    if rec is None:
        raise HTTPException(status_code=404, detail="no such approved policy: approve a policy first")
    try:
        res = modify(req.source, req.tools or None, req.filename)
    except (SourceError, ModifyError) as e:
        raise HTTPException(status_code=422, detail=str(e))
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as z:
        z.writestr(req.filename, res.patched_source)
        z.writestr("yog_runtime.py", RUNTIME_PATH.read_text(encoding="utf-8"))
        z.writestr("yog.py", ENGINE_PATH.read_text(encoding="utf-8"))
        z.writestr("policy.yog", rec.yog_source)
        z.writestr("README.txt", "Run your agent from this folder. Set YOG_NOW=\"3,sat\" to pin the clock when testing.\n"
                                 "Denied calls raise yog_runtime.YogDenied.\n")
    return Response(buf.getvalue(), media_type="application/zip",
                    headers={"Content-Disposition": 'attachment; filename="yog_patched_agent.zip"'})
