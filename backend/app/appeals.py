"""Appeals and reviewer decisions."""
import datetime
from typing import Optional

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from .db import get_db
from .scoring import points_for_result, compute_total
from .evaluation import _load_evaluation

router = APIRouter()


class AppealCreate(BaseModel):
    evaluation_id: int
    criterion_id: str
    comment: str


class DecisionCreate(BaseModel):
    action: str            # approve | reject
    new_answer: Optional[str] = None
    new_scale_value: Optional[int] = None
    reason: Optional[str] = ""


@router.post("/api/appeals")
def create_appeal(body: AppealCreate):
    conn = get_db()
    try:
        # Verify evaluation exists
        ev = conn.execute("SELECT id FROM evaluations WHERE id = ?", (body.evaluation_id,)).fetchone()
        if not ev:
            raise HTTPException(404, "Evaluation not found")

        # Verify criterion exists in this evaluation
        cr = conn.execute(
            "SELECT * FROM criterion_results WHERE evaluation_id = ? AND criterion_id = ?",
            (body.evaluation_id, body.criterion_id)
        ).fetchone()
        if not cr:
            raise HTTPException(404, f"Criterion {body.criterion_id!r} not in evaluation")

        created_at = datetime.datetime.now(datetime.UTC).isoformat()
        cur = conn.execute(
            "INSERT INTO appeals (evaluation_id, criterion_id, comment, status, created_at) VALUES (?,?,?,?,?)",
            (body.evaluation_id, body.criterion_id, body.comment, 'open', created_at)
        )
        appeal_id = cur.lastrowid
        conn.commit()
        return {"id": appeal_id, "evaluation_id": body.evaluation_id,
                "criterion_id": body.criterion_id, "comment": body.comment,
                "status": "open", "created_at": created_at}
    finally:
        conn.close()


@router.get("/api/appeals")
def list_appeals(status: Optional[str] = None):
    conn = get_db()
    try:
        if status:
            rows = conn.execute(
                "SELECT * FROM appeals WHERE status = ? ORDER BY id DESC", (status,)
            ).fetchall()
        else:
            rows = conn.execute("SELECT * FROM appeals ORDER BY id DESC").fetchall()
        return [dict(r) for r in rows]
    finally:
        conn.close()


@router.get("/api/appeals/{appeal_id}")
def get_appeal(appeal_id: int):
    conn = get_db()
    try:
        row = conn.execute("SELECT * FROM appeals WHERE id = ?", (appeal_id,)).fetchone()
        if not row:
            raise HTTPException(404, "Appeal not found")
        return dict(row)
    finally:
        conn.close()


@router.post("/api/appeals/{appeal_id}/decision")
def create_decision(appeal_id: int, body: DecisionCreate):
    if body.action not in ("approve", "reject"):
        raise HTTPException(400, "action must be 'approve' or 'reject'")

    conn = get_db()
    try:
        appeal = conn.execute("SELECT * FROM appeals WHERE id = ?", (appeal_id,)).fetchone()
        if not appeal:
            raise HTTPException(404, "Appeal not found")
        if appeal["status"] != "open":
            raise HTTPException(400, "Appeal is already resolved")

        appeal = dict(appeal)
        eval_id = appeal["evaluation_id"]
        crit_id = appeal["criterion_id"]

        # Load original criterion result
        cr = dict(conn.execute(
            "SELECT * FROM criterion_results WHERE evaluation_id = ? AND criterion_id = ?",
            (eval_id, crit_id)
        ).fetchone())

        original_points = cr.get("points")
        final_points = original_points

        # If approved with new answer — update criterion result points
        if body.action == "approve" and body.new_answer:
            # Load checklist config to compute new points
            ev_row = conn.execute("SELECT checklist_version_id FROM evaluations WHERE id = ?", (eval_id,)).fetchone()
            if ev_row:
                import json
                cv = conn.execute(
                    "SELECT config FROM checklist_versions WHERE id = ?", (ev_row["checklist_version_id"],)
                ).fetchone()
                if cv:
                    criteria_list = json.loads(cv["config"]).get("criteria", [])
                    cfg = next((c for c in criteria_list if c["id"] == crit_id), {})
                    new_sv = body.new_scale_value
                    pts = points_for_result(body.new_answer, new_sv, cfg)
                    final_points = str(pts) if pts is not None else None

                    # Update criterion result
                    conn.execute(
                        "UPDATE criterion_results SET answer = ?, scale_value = ?, points = ? "
                        "WHERE evaluation_id = ? AND criterion_id = ?",
                        (body.new_answer, new_sv, final_points, eval_id, crit_id)
                    )

        # Recompute total
        all_results = [dict(r) for r in conn.execute(
            "SELECT * FROM criterion_results WHERE evaluation_id = ?", (eval_id,)
        ).fetchall()]
        ev_row2 = conn.execute("SELECT checklist_version_id FROM evaluations WHERE id = ?", (eval_id,)).fetchone()
        if ev_row2:
            import json
            cv2 = conn.execute(
                "SELECT config FROM checklist_versions WHERE id = ?", (ev_row2["checklist_version_id"],)
            ).fetchone()
            if cv2:
                criteria_list2 = json.loads(cv2["config"]).get("criteria", [])
                new_total = compute_total(all_results, criteria_list2)
                conn.execute("UPDATE evaluations SET total = ? WHERE id = ?", (new_total, eval_id))

        # Update appeal status
        new_status = "approved" if body.action == "approve" else "rejected"
        conn.execute("UPDATE appeals SET status = ? WHERE id = ?", (new_status, appeal_id))

        # Insert decision record
        created_at = datetime.datetime.now(datetime.UTC).isoformat()
        cur = conn.execute(
            """INSERT INTO decisions
               (appeal_id, action, new_answer, new_scale_value, reason, original_points, final_points, created_at)
               VALUES (?,?,?,?,?,?,?,?)""",
            (appeal_id, body.action, body.new_answer, body.new_scale_value,
             body.reason or "", original_points, final_points, created_at)
        )
        decision_id = cur.lastrowid
        conn.commit()

        return {"id": decision_id, "appeal_id": appeal_id, "action": body.action,
                "new_answer": body.new_answer, "reason": body.reason,
                "original_points": original_points, "final_points": final_points,
                "created_at": created_at}
    finally:
        conn.close()


@router.get("/api/decisions")
def list_decisions(appeal_id: Optional[int] = None):
    conn = get_db()
    try:
        if appeal_id:
            rows = conn.execute(
                "SELECT * FROM decisions WHERE appeal_id = ? ORDER BY id DESC", (appeal_id,)
            ).fetchall()
        else:
            rows = conn.execute("SELECT * FROM decisions ORDER BY id DESC").fetchall()
        return [dict(r) for r in rows]
    finally:
        conn.close()
