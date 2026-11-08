import datetime
import json
import os
from contextlib import asynccontextmanager
from pathlib import Path

import httpx
from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from fastapi.responses import JSONResponse

from fastapi import HTTPException
from dotenv import load_dotenv
from .db import create_tables, get_db
from .dataset import router as dataset_router
from .checklists import router as checklists_router, seed_checklists
from .evaluation import router as evaluation_router
from .appeals import router as appeals_router
from . import audio_analysis

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

    imported_at = datetime.datetime.now(datetime.UTC).isoformat()

    # Try real API first
    api_url = os.getenv("DATASET_API_URL", "").strip()
    if api_url:
        try:
            async with httpx.AsyncClient(timeout=20) as client:
                resp = await client.get(api_url)
            payload = resp.json()
            if payload.get("isSuccess"):
                records = payload["data"]["records"]
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
                return  # API succeeded — done
        except Exception:
            pass  # fall through to SAMPLE

    # Fallback: load SAMPLE seed if API unavailable
    seed_path = Path(__file__).parent.parent.parent / "seed" / "sample_dialogs.json"
    if seed_path.exists():
        payload = json.loads(seed_path.read_text(encoding="utf-8"))
        records = payload["data"]["records"]
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


@app.get("/api/export/{group_id}")
def export_results(group_id: str):
    """Export evaluations in submission JSON format (schema 1.0)."""
    CRITERION_MAP = {
        "c01": "contact", "c02": "discovery", "c03": "identification",
        "c04": "consultation", "c05": "empathy", "c06": "dialogue",
        "c07": "closure", "c08": "critical",
    }

    def convert_value(cid, answer, scale_value):
        if answer == "na":
            return None
        if cid in ("c04", "c06"):
            return int(scale_value) if scale_value is not None else None
        return True if answer == "yes" else False

    conn = get_db()
    try:
        convs = conn.execute(
            "SELECT id FROM conversations WHERE group_id = ? ORDER BY id", (group_id,)
        ).fetchall()

        results = []
        for conv in convs:
            conv_id = conv["id"]
            ev = conn.execute(
                "SELECT * FROM evaluations WHERE conversation_id = ? AND status = 'done' ORDER BY id DESC LIMIT 1",
                (conv_id,)
            ).fetchone()

            if not ev:
                results.append({"conversation_id": conv_id, "status": "error",
                                 "criteria": [], "score": None,
                                 "error": "Диалог не оценён"})
                continue

            crit_rows = conn.execute(
                "SELECT * FROM criterion_results WHERE evaluation_id = ? ORDER BY rowid", (ev["id"],)
            ).fetchall()

            criteria = []
            critical_flag = False
            for r in crit_rows:
                cid = r["criterion_id"]
                value = convert_value(cid, r["answer"], r["scale_value"])
                if cid == "c08" and r["answer"] == "yes":
                    critical_flag = True
                evidence_raw = json.loads(r["evidence"]) if r["evidence"] else []
                evidence_turns = [e["msg_index"] + 1 for e in evidence_raw if "msg_index" in e]
                criteria.append({
                    "criterion_id": CRITERION_MAP.get(cid, cid),
                    "value": value,
                    "rationale": r["explanation"] or "",
                    "evidence_turns": evidence_turns,
                })

            final_score = round(float(ev["total"]), 2) if ev["total"] is not None else None
            results.append({
                "conversation_id": conv_id, "status": "ok",
                "criteria": criteria,
                "score": {"final_score": final_score, "critical_flag": critical_flag},
            })
    finally:
        conn.close()

    return {
        "schema_version": "1.0",
        "team_name": "CQA Team",
        "model": {"mode": "external_api", "name": "claude-sonnet-4-5"},
        "results": results,
    }


@app.get("/api/health")
def health() -> JSONResponse:
    return JSONResponse({
        "status": "ok",
        "time": datetime.datetime.now(datetime.UTC).isoformat(),
    })


@app.post("/api/conversations/{conv_id}/analyze-audio")
async def analyze_audio_endpoint(conv_id: str):
    """Run Whisper analysis on a voice call's audio. Results cached in DB."""
    if not audio_analysis.is_available():
        raise HTTPException(503, "faster-whisper не установлен")

    conn = get_db()
    try:
        row = conn.execute(
            "SELECT audio_url, channel, audio_analysis FROM conversations WHERE id = ?",
            (conv_id,),
        ).fetchone()
    finally:
        conn.close()

    if not row:
        raise HTTPException(404, "Диалог не найден")
    if row["channel"] != "voice call":
        raise HTTPException(400, "Только для звонков")
    if not row["audio_url"]:
        raise HTTPException(400, "Нет ссылки на аудио")

    # Return cached result
    if row["audio_analysis"]:
        return json.loads(row["audio_analysis"])

    # Run Whisper
    try:
        result = audio_analysis.analyze_call_audio(row["audio_url"])
    except Exception as e:
        raise HTTPException(500, f"Ошибка анализа аудио: {e}")

    conn = get_db()
    try:
        conn.execute(
            "UPDATE conversations SET audio_analysis = ? WHERE id = ?",
            (json.dumps(result, ensure_ascii=False), conv_id),
        )
        conn.commit()
    finally:
        conn.close()

    return result


@app.get("/api/conversations/{conv_id}/audio-status")
def audio_status_endpoint(conv_id: str):
    """Check if audio analysis is available and cached."""
    conn = get_db()
    try:
        row = conn.execute(
            "SELECT channel, audio_url, audio_analysis FROM conversations WHERE id = ?",
            (conv_id,),
        ).fetchone()
    finally:
        conn.close()

    if not row:
        raise HTTPException(404, "Диалог не найден")

    return {
        "is_voice_call": row["channel"] == "voice call",
        "has_audio_url": bool(row["audio_url"]),
        "is_analyzed": bool(row["audio_analysis"]),
        "whisper_available": audio_analysis.is_available(),
        "cached": json.loads(row["audio_analysis"]) if row["audio_analysis"] else None,
    }


frontend_path = Path(__file__).parent.parent.parent / "frontend"
if frontend_path.exists():
    app.mount("/", StaticFiles(directory=str(frontend_path), html=True), name="frontend")
