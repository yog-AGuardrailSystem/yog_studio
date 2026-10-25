from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api import check

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
