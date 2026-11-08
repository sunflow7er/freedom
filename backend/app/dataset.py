import json
import os
import datetime
from pathlib import Path
import httpx
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from typing import Optional, List
from .db import get_db

router = APIRouter()


class TranscriptMessage(BaseModel):
    timestamp: str = "00:00"
    speaker: str
    text: str


class ConversationCreate(BaseModel):
    id: Optional[str] = None
    channel: str = "agent chat"
    language: str = "RU"
    transcript: List[TranscriptMessage]
    audio_url: Optional[str] = None


def _get_api_url(group_id: str) -> str:
    base = os.getenv("DATASET_API_URL", "").strip()
    if not base:
        raise HTTPException(status_code=500, detail="DATASET_API_URL not set in .env")
    return base


SEED_PATH = Path(__file__).parent.parent.parent / "seed" / "sample_dialogs.json"


@router.post("/api/datasets/{group_id}/import")
async def import_dataset(group_id: str):
    if group_id.upper() == "SAMPLE":
        if not SEED_PATH.exists():
            raise HTTPException(status_code=404, detail="seed/sample_dialogs.json not found")
        payload = json.loads(SEED_PATH.read_text(encoding="utf-8"))
    else:
        url = _get_api_url(group_id)
        async with httpx.AsyncClient(timeout=30) as client:
            try:
                resp = await client.get(url)
            except httpx.HTTPError as e:
                raise HTTPException(status_code=502, detail=f"Upstream error: {e}")
            if resp.status_code >= 400:
                raise HTTPException(status_code=502, detail=f"Upstream HTTP {resp.status_code}")
        try:
            payload = resp.json()
        except Exception:
            raise HTTPException(status_code=502, detail=f"Non-JSON response: {resp.text[:300]}")
        if not payload.get("isSuccess"):
            raise HTTPException(status_code=502, detail=f"isSuccess=false: {payload.get('error', str(payload)[:200])}")

    records = payload["data"]["records"]
    imported_at = datetime.datetime.now(datetime.UTC).isoformat()

    conn = get_db()
    inserted = 0
    skipped = 0
    try:
        for rec in records:
            existing = conn.execute(
                "SELECT id FROM conversations WHERE id = ?",
                (rec["conversation_id"],)
            ).fetchone()
            if existing:
                skipped += 1
                continue
            conn.execute(
                """INSERT INTO conversations
                   (id, group_id, channel, language, transcript, audio_url, imported_at)
                   VALUES (?, ?, ?, ?, ?, ?, ?)""",
                (
                    rec["conversation_id"],
                    group_id,
                    rec["channel"],
                    rec["language"],
                    json.dumps(rec["transcript"], ensure_ascii=False),
                    rec.get("audio_url"),
                    imported_at,
                ),
            )
            inserted += 1
        conn.commit()
    finally:
        conn.close()

    return {
        "group_id": group_id,
        "total": len(records),
        "inserted": inserted,
        "skipped": skipped,
    }


@router.post("/api/conversations")
def create_conversation(body: ConversationCreate):
    imported_at = datetime.datetime.now(datetime.UTC).isoformat()
    conv_id = body.id or f"manual-{int(datetime.datetime.now(datetime.UTC).timestamp())}"
    transcript = [m.model_dump() for m in body.transcript]

    conn = get_db()
    try:
        existing = conn.execute("SELECT id FROM conversations WHERE id = ?", (conv_id,)).fetchone()
        if existing:
            raise HTTPException(status_code=409, detail=f"Диалог с ID «{conv_id}» уже существует")
        conn.execute(
            """INSERT INTO conversations (id, group_id, channel, language, transcript, audio_url, imported_at)
               VALUES (?, ?, ?, ?, ?, ?, ?)""",
            (conv_id, "MANUAL", body.channel, body.language.upper(),
             json.dumps(transcript, ensure_ascii=False), body.audio_url, imported_at),
        )
        conn.commit()
    finally:
        conn.close()

    return {"id": conv_id, "channel": body.channel, "language": body.language.upper()}


@router.get("/api/conversations")
def list_conversations(
    lang: str = None,
    channel: str = None,
    status: str = None,
    gross: bool = None,
    q: str = None,
    sort: str = "imported_at_desc",
):
    conn = get_db()
    try:
        query = """
            SELECT c.id, c.group_id, c.channel, c.language, c.audio_url, c.imported_at,
                   e.id AS eval_id, e.status AS eval_status, e.total, e.gross_error,
                   substr(json_extract(c.transcript, '$[0].text'), 1, 90) AS preview
            FROM conversations c
            LEFT JOIN evaluations e ON e.conversation_id = c.id
                AND e.id = (SELECT MAX(id) FROM evaluations WHERE conversation_id = c.id)
            WHERE 1=1
        """
        params = []
        if lang:
            query += " AND c.language = ?"
            params.append(lang.upper())
        if channel:
            query += " AND c.channel = ?"
            params.append(channel)
        if status == "evaluated":
            query += " AND e.status = 'done'"
        elif status == "pending":
            query += " AND e.id IS NULL"
        if gross is True:
            query += " AND e.gross_error = 1"
        if q:
            query += " AND c.id LIKE ?"
            params.append(f"%{q}%")

        order = "c.imported_at DESC"
        if sort == "id_asc":
            order = "c.id ASC"
        elif sort == "score_desc":
            order = "CAST(e.total AS REAL) DESC NULLS LAST"
        elif sort == "score_asc":
            order = "CAST(e.total AS REAL) ASC NULLS LAST"
        elif sort == "gross_first":
            order = "e.gross_error DESC, c.imported_at DESC"
        query += f" ORDER BY {order}"

        rows = conn.execute(query, params).fetchall()
        return [dict(r) for r in rows]
    finally:
        conn.close()


@router.get("/api/conversations/{conv_id}")
def get_conversation(conv_id: str):
    conn = get_db()
    try:
        row = conn.execute(
            "SELECT * FROM conversations WHERE id = ?", (conv_id,)
        ).fetchone()
        if not row:
            raise HTTPException(status_code=404, detail="Conversation not found")
        data = dict(row)
        data["transcript"] = json.loads(data["transcript"])
        return data
    finally:
        conn.close()


@router.get("/api/analytics")
def get_analytics():
    conn = get_db()
    try:
        # Totals
        totals = conn.execute("""
            SELECT
                COUNT(c.id) AS total_convs,
                COUNT(e.id) AS evaluated,
                SUM(CASE WHEN e.gross_error = 1 THEN 1 ELSE 0 END) AS gross_errors,
                AVG(CAST(e.total AS REAL)) AS avg_score
            FROM conversations c
            LEFT JOIN evaluations e ON e.conversation_id = c.id
                AND e.id = (SELECT MAX(id) FROM evaluations WHERE conversation_id = c.id)
        """).fetchone()

        # Score distribution buckets
        dist = conn.execute("""
            SELECT
                SUM(CASE WHEN CAST(total AS REAL) >= 90 THEN 1 ELSE 0 END) AS d90,
                SUM(CASE WHEN CAST(total AS REAL) >= 75 AND CAST(total AS REAL) < 90 THEN 1 ELSE 0 END) AS d75,
                SUM(CASE WHEN CAST(total AS REAL) >= 50 AND CAST(total AS REAL) < 75 THEN 1 ELSE 0 END) AS d50,
                SUM(CASE WHEN CAST(total AS REAL) >= 25 AND CAST(total AS REAL) < 50 THEN 1 ELSE 0 END) AS d25,
                SUM(CASE WHEN CAST(total AS REAL) < 25 THEN 1 ELSE 0 END) AS d0
            FROM evaluations
            WHERE status = 'done' AND total IS NOT NULL
        """).fetchone()

        # Criteria failure rates (top failures)
        criteria_rows = conn.execute("""
            SELECT cr.criterion_id,
                   COUNT(*) AS total,
                   SUM(CASE WHEN cr.answer = 'no' THEN 1 ELSE 0 END) AS failures,
                   SUM(CASE WHEN cr.answer = 'na' THEN 1 ELSE 0 END) AS na_count
            FROM criterion_results cr
            JOIN evaluations e ON e.id = cr.evaluation_id
            WHERE e.status = 'done'
            GROUP BY cr.criterion_id
            ORDER BY failures DESC
        """).fetchall()

        # By channel
        by_channel = conn.execute("""
            SELECT c.channel,
                   COUNT(e.id) AS evaluated,
                   ROUND(AVG(CAST(e.total AS REAL)), 1) AS avg_score
            FROM conversations c
            JOIN evaluations e ON e.conversation_id = c.id
                AND e.id = (SELECT MAX(id) FROM evaluations WHERE conversation_id = c.id)
            WHERE e.status = 'done'
            GROUP BY c.channel
        """).fetchall()

        # By language
        by_lang = conn.execute("""
            SELECT c.language,
                   COUNT(e.id) AS evaluated,
                   ROUND(AVG(CAST(e.total AS REAL)), 1) AS avg_score
            FROM conversations c
            JOIN evaluations e ON e.conversation_id = c.id
                AND e.id = (SELECT MAX(id) FROM evaluations WHERE conversation_id = c.id)
            WHERE e.status = 'done'
            GROUP BY c.language
            ORDER BY evaluated DESC
        """).fetchall()

        return {
            "totals": dict(totals),
            "distribution": dict(dist) if dist else {},
            "criteria": [dict(r) for r in criteria_rows],
            "by_channel": [dict(r) for r in by_channel],
            "by_lang": [dict(r) for r in by_lang],
        }
    finally:
        conn.close()
