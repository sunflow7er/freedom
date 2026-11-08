import datetime
import json
import os
from contextlib import asynccontextmanager
from pathlib import Path

import httpx
from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from fastapi.responses import JSONResponse

from dotenv import load_dotenv
from .db import create_tables, get_db
from .dataset import router as dataset_router
from .checklists import router as checklists_router, seed_checklists
from .evaluation import router as evaluation_router
from .appeals import router as appeals_router

load_dotenv(Path(__file__).parent.parent.parent / ".env", override=True)


async def auto_import():
    """Import dialogs on startup if database is empty. Requires AUTO_IMPORT=1 env var."""
    if os.getenv("AUTO_IMPORT") != "1":
        return
    conn = get_db()
    try:
        count = conn.execute("SELECT COUNT(*) FROM conversations").fetchone()[0]
        if count > 0:
            return
    finally:
        conn.close()

    # Try SAMPLE seed first (always available)
    seed_path = Path(__file__).parent.parent.parent / "seed" / "sample_dialogs.json"
    if seed_path.exists():
        payload = json.loads(seed_path.read_text(encoding="utf-8"))
        records = payload["data"]["records"]
        imported_at = datetime.datetime.now(datetime.UTC).isoformat()
        conn = get_db()
        try:
            for rec in records:
                conn.execute(
                    "INSERT OR IGNORE INTO conversations (id, group_id, channel, language, transcript, audio_url, imported_at) VALUES (?,?,?,?,?,?,?)",
                    (rec["conversation_id"], "SAMPLE", rec["channel"], rec["language"],
                     json.dumps(rec["transcript"], ensure_ascii=False), rec.get("audio_url"), imported_at),
                )
            conn.commit()
        finally:
            conn.close()

    # Also try real API if URL is set
    api_url = os.getenv("DATASET_API_URL", "").strip()
    if not api_url:
        return
    try:
        async with httpx.AsyncClient(timeout=20) as client:
            resp = await client.get(api_url)
        payload = resp.json()
        if not payload.get("isSuccess"):
            return
        records = payload["data"]["records"]
        imported_at = datetime.datetime.now(datetime.UTC).isoformat()
        conn = get_db()
        try:
            for rec in records:
                conn.execute(
                    "INSERT OR IGNORE INTO conversations (id, group_id, channel, language, transcript, audio_url, imported_at) VALUES (?,?,?,?,?,?,?)",
                    (rec["conversation_id"], payload["data"]["dataset_group_id"],
                     rec["channel"], rec["language"],
                     json.dumps(rec["transcript"], ensure_ascii=False),
                     rec.get("audio_url"), imported_at),
                )
            conn.commit()
        finally:
            conn.close()
    except Exception:
        pass  # API unavailable — SAMPLE dialogs already loaded


@asynccontextmanager
async def lifespan(app: FastAPI):
    create_tables()
    seed_checklists()
    await auto_import()
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
