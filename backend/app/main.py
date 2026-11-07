import datetime
from pathlib import Path

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from fastapi.responses import JSONResponse

from .db import create_tables

app = FastAPI(title="CQA API", version="0.1.0")


@app.on_event("startup")
async def startup() -> None:
    create_tables()


@app.get("/api/health")
def health() -> JSONResponse:
    return JSONResponse({
        "status": "ok",
        "time": datetime.datetime.utcnow().isoformat() + "Z",
    })


frontend_path = Path(__file__).parent.parent.parent / "frontend"
if frontend_path.exists():
    app.mount("/", StaticFiles(directory=str(frontend_path), html=True), name="frontend")
