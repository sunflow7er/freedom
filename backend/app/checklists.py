import json
import datetime
from pathlib import Path
from fastapi import APIRouter, HTTPException
from .db import get_db

router = APIRouter()

SEED_DIR = Path(__file__).parent.parent.parent / "seed"


def seed_checklists() -> None:
    """Load default checklists from seed/ into DB if they don't exist yet."""
    conn = get_db()
    try:
        for seed_file in [SEED_DIR / "checklist_chat.json", SEED_DIR / "checklist_call.json"]:
            if not seed_file.exists():
                continue
            data = json.loads(seed_file.read_text(encoding="utf-8"))
            channel = data["channel"]
            name = data["name"]

            existing = conn.execute(
                "SELECT id FROM checklists WHERE channel = ?", (channel,)
            ).fetchone()
            if existing:
                continue

            cur = conn.execute(
                "INSERT INTO checklists (name, channel) VALUES (?, ?)",
                (name, channel),
            )
            checklist_id = cur.lastrowid

            version_config = {"criteria": data["criteria"]}
            cur2 = conn.execute(
                """INSERT INTO checklist_versions
                   (checklist_id, version, config, comment, created_at)
                   VALUES (?, 1, ?, 'initial seed', ?)""",
                (checklist_id, json.dumps(version_config, ensure_ascii=False),
                 datetime.datetime.now(datetime.UTC).isoformat()),
            )
            version_id = cur2.lastrowid

            conn.execute(
                "UPDATE checklists SET active_version_id = ? WHERE id = ?",
                (version_id, checklist_id),
            )
        conn.commit()
    finally:
        conn.close()


@router.get("/api/checklists")
def list_checklists():
    conn = get_db()
    try:
        rows = conn.execute("SELECT * FROM checklists").fetchall()
        return [dict(r) for r in rows]
    finally:
        conn.close()


@router.get("/api/checklists/{checklist_id}")
def get_checklist(checklist_id: int):
    conn = get_db()
    try:
        row = conn.execute(
            "SELECT * FROM checklists WHERE id = ?", (checklist_id,)
        ).fetchone()
        if not row:
            raise HTTPException(status_code=404, detail="Checklist not found")
        cl = dict(row)
        ver = conn.execute(
            "SELECT * FROM checklist_versions WHERE id = ?",
            (cl["active_version_id"],)
        ).fetchone()
        if ver:
            cl["active_version"] = dict(ver)
            cl["active_version"]["config"] = json.loads(cl["active_version"]["config"])
        return cl
    finally:
        conn.close()


@router.get("/api/checklists/{checklist_id}/versions")
def list_versions(checklist_id: int):
    conn = get_db()
    try:
        rows = conn.execute(
            "SELECT * FROM checklist_versions WHERE checklist_id = ? ORDER BY version DESC",
            (checklist_id,)
        ).fetchall()
        result = []
        for r in rows:
            d = dict(r)
            d["config"] = json.loads(d["config"])
            result.append(d)
        return result
    finally:
        conn.close()


@router.post("/api/checklists/{checklist_id}/versions")
def create_version(checklist_id: int, body: dict):
    """Create a new checklist version. Body: {config, comment}"""
    conn = get_db()
    try:
        cl = conn.execute(
            "SELECT id FROM checklists WHERE id = ?", (checklist_id,)
        ).fetchone()
        if not cl:
            raise HTTPException(status_code=404, detail="Checklist not found")

        last = conn.execute(
            "SELECT MAX(version) as v FROM checklist_versions WHERE checklist_id = ?",
            (checklist_id,)
        ).fetchone()
        next_version = (last["v"] or 0) + 1

        config = body.get("config")
        if not config:
            raise HTTPException(status_code=400, detail="config required")

        cur = conn.execute(
            """INSERT INTO checklist_versions
               (checklist_id, version, config, comment, created_at)
               VALUES (?, ?, ?, ?, ?)""",
            (checklist_id, next_version,
             json.dumps(config, ensure_ascii=False),
             body.get("comment", ""),
             datetime.datetime.now(datetime.UTC).isoformat()),
        )
        version_id = cur.lastrowid

        conn.execute(
            "UPDATE checklists SET active_version_id = ? WHERE id = ?",
            (version_id, checklist_id),
        )
        conn.commit()
        return {"id": version_id, "version": next_version, "checklist_id": checklist_id}
    finally:
        conn.close()
