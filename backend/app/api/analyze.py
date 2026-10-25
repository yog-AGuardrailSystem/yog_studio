from fastapi import APIRouter, File, HTTPException, UploadFile
from pydantic import BaseModel

from app.core.models import DetectResult, Tool
from app.core.pyast import MAX_SOURCE_BYTES, SourceError, parse_source
from app.detect.detector import detect
from app.extract.ast_extractor import extract_tools, list_candidates

router = APIRouter()


class AnalyzeRequest(BaseModel):
    filename: str = "agent.py"
    source: str


class AnalyzeResponse(BaseModel):
    filename: str
    source: str
    detect: DetectResult
    tools: list[Tool]
    candidates: list[Tool]      # filled only when kind == "unknown": functions the user may pick by hand


def analyze_source(filename: str, source: str) -> AnalyzeResponse:
    """Static analysis only. Raises SourceError for non-Python / unparsable input."""
    tree = parse_source(source)
    detected = detect(tree, source)
    tools = extract_tools(tree, detected)
    candidates = list_candidates(tree) if detected.kind == "unknown" else []
    return AnalyzeResponse(filename=filename, source=source, detect=detected, tools=tools, candidates=candidates)


@router.post("/analyze", response_model=AnalyzeResponse)
def analyze(req: AnalyzeRequest) -> AnalyzeResponse:
    try:
        return analyze_source(req.filename, req.source)
    except SourceError as e:
        raise HTTPException(status_code=422, detail=str(e))


@router.post("/analyze/upload", response_model=AnalyzeResponse)
async def analyze_upload(file: UploadFile = File(...)) -> AnalyzeResponse:
    raw = await file.read(MAX_SOURCE_BYTES + 1)
    try:
        source = raw.decode("utf-8")
    except UnicodeDecodeError:
        raise HTTPException(status_code=422, detail="file is not UTF-8 text")
    try:
        return analyze_source(file.filename or "agent.py", source)
    except SourceError as e:
        raise HTTPException(status_code=422, detail=str(e))
