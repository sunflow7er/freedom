import datetime
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from fastapi.responses import JSONResponse

from dotenv import load_dotenv
from .db import create_tables
from .dataset import router as dataset_router
from .checklists import router as checklists_router, seed_checklists
from .evaluation import router as evaluation_router
from .appeals import router as appeals_router

load_dotenv(Path(__file__).parent.parent.parent / ".env", override=True)


@asynccontextmanager
async def lifespan(app: FastAPI):
    create_tables()
    seed_checklists()
    yield


app = FastAPI(title="CQA API", version="0.1.0", lifespan=lifespan)
app.include_router(dataset_router)
app.include_router(checklists_router)
app.include_router(evaluation_router)
app.include_router(appeals_router)


@app.get("/api/health")
def health() -> JSONResponse:
    return JSONResponse({
        "status": "ok",
        "time": datetime.datetime.now(datetime.UTC).isoformat(),
    })


frontend_path = Path(__file__).parent.parent.parent / "frontend"
if frontend_path.exists():
    app.mount("/", StaticFiles(directory=str(frontend_path), html=True), name="frontend")
