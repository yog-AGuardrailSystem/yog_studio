from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api import analyze, check, device, evaluate, modify, policies, retrieve, samples, translate

app = FastAPI(title="YOG Studio")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173", "http://127.0.0.1:5173"],
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/health")
def health() -> dict:
    return {"status": "ok"}


app.include_router(check.router)
app.include_router(analyze.router)
app.include_router(samples.router)
app.include_router(retrieve.router)
app.include_router(translate.router)
app.include_router(policies.router)
app.include_router(evaluate.router)
app.include_router(modify.router)
app.include_router(device.router)
