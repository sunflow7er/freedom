"""Evaluation pipeline: prompt → LLM → validate → score → store."""
import json
import datetime
import hashlib
from typing import Optional

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from .db import get_db
from .prompt import build_prompt
from .validator import validate_llm_response, ValidationError
from .scoring import points_for_result, compute_total
from .llm.anthropic_provider import get_provider

router = APIRouter()

MAX_RETRIES = 2


class EvaluateRequest(BaseModel):
    conversation_id: str
    checklist_version_id: Optional[int] = None  # None = use active version for channel


def _get_checklist_version(conn, conversation_id: str, checklist_version_id: Optional[int]):
    if checklist_version_id:
        row = conn.execute(
            "SELECT cv.*, c.channel FROM checklist_versions cv "
            "JOIN checklists c ON c.id = cv.checklist_id "
            "WHERE cv.id = ?",
            (checklist_version_id,)
        ).fetchone()
        if not row:
            raise HTTPException(404, f"Checklist version {checklist_version_id} not found")
        return dict(row)

    conv = conn.execute(
        "SELECT channel FROM conversations WHERE id = ?", (conversation_id,)
    ).fetchone()
    if not conv:
        raise HTTPException(404, f"Conversation {conversation_id!r} not found")
    channel = conv["channel"]

    row = conn.execute(
        """SELECT cv.*, c.channel FROM checklist_versions cv
           JOIN checklists c ON c.id = cv.checklist_id
           WHERE c.channel = ? AND c.active_version_id = cv.id""",
        (channel,)
    ).fetchone()
    if not row:
        raise HTTPException(404, f"No active checklist for channel {channel!r}")
    return dict(row)


@router.post("/api/evaluations")
async def evaluate_conversation(req: EvaluateRequest):
    conn = get_db()
    try:
        # Load conversation
        conv_row = conn.execute(
            "SELECT * FROM conversations WHERE id = ?", (req.conversation_id,)
        ).fetchone()
        if not conv_row:
            raise HTTPException(404, f"Conversation {req.conversation_id!r} not found")
        conv = dict(conv_row)
        transcript = json.loads(conv["transcript"])
        audio_metrics = json.loads(conv["audio_analysis"]) if conv.get("audio_analysis") else None

        # Load checklist version
        cv = _get_checklist_version(conn, req.conversation_id, req.checklist_version_id)
        checklist_config = json.loads(cv["config"])
        criteria = checklist_config.get("criteria", [])
        criteria_map = {c["id"]: c for c in criteria}
        cv_id = cv["id"]

        # Build prompt (include audio metrics for voice calls if analyzed)
        system_prompt, user_prompt = build_prompt(checklist_config, transcript, audio_metrics)
        prompt_hash = hashlib.sha256((system_prompt + user_prompt).encode()).hexdigest()

        # Check if already evaluated with same prompt
        existing = conn.execute(
            "SELECT id FROM evaluations WHERE conversation_id = ? AND checklist_version_id = ? AND prompt_hash = ?",
            (req.conversation_id, cv_id, prompt_hash)
        ).fetchone()
        if existing:
            eval_id = existing["id"]
            return _load_evaluation(conn, eval_id)

        # Create evaluation record (status=running)
        created_at = datetime.datetime.now(datetime.UTC).isoformat()
        cur = conn.execute(
            """INSERT INTO evaluations
               (conversation_id, checklist_version_id, model, status, prompt_hash, created_at)
               VALUES (?, ?, ?, 'running', ?, ?)""",
            (req.conversation_id, cv_id, "claude-sonnet-4-5", prompt_hash, created_at)
        )
        eval_id = cur.lastrowid
        conn.commit()
    finally:
        conn.close()

    # Call LLM (outside DB connection)
    provider = get_provider()
    raw_response = None
    validated = None
    llm_error = None

    for attempt in range(MAX_RETRIES + 1):
        try:
            llm_resp = await provider.complete(system_prompt, user_prompt, temperature=0)
            raw_response = llm_resp.content
            validated = validate_llm_response(raw_response, criteria, transcript)
            break
        except ValidationError as e:
            llm_error = str(e)
            if attempt == MAX_RETRIES:
                break
        except Exception as e:
            llm_error = str(e)
            break

    conn = get_db()
    try:
        if validated is None:
            conn.execute(
                "UPDATE evaluations SET status = 'error', raw_response = ? WHERE id = ?",
                (f"ERROR: {llm_error}\n\nRaw:\n{raw_response}", eval_id)
            )
            conn.commit()
            raise HTTPException(500, f"LLM evaluation failed: {llm_error}")

        # Compute points and gross error flag
        criterion_results_to_store = []
        gross_error = False
        for r in validated:
            cid = r["criterion_id"]
            cfg = criteria_map.get(cid, {})
            pts = points_for_result(r["answer"], r.get("scale_value"), cfg)
            r["points"] = str(pts) if pts is not None else None
            if cid == "c08" and r["answer"] == "yes":
                gross_error = True
            criterion_results_to_store.append(r)

        total = compute_total(criterion_results_to_store, criteria)

        # Store criterion results
        for r in criterion_results_to_store:
            conn.execute(
                """INSERT INTO criterion_results
                   (evaluation_id, criterion_id, answer, scale_value, points,
                    explanation, evidence, checked_range, confidence, needs_review)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (
                    eval_id,
                    r["criterion_id"],
                    r["answer"],
                    r.get("scale_value"),
                    r.get("points"),
                    r.get("explanation", ""),
                    json.dumps(r.get("evidence", []), ensure_ascii=False),
                    json.dumps(r.get("checked_range", [0, 0])),
                    r.get("confidence", "high"),
                    1 if r.get("needs_review") else 0,
                )
            )

        # Update evaluation record
        cost = llm_resp.cost_usd if hasattr(llm_resp, "cost_usd") else None
        conn.execute(
            """UPDATE evaluations
               SET status = 'done', total = ?, gross_error = ?, raw_response = ?,
                   cost_usd = ?
               WHERE id = ?""",
            (total, 1 if gross_error else 0, raw_response, cost, eval_id)
        )
        conn.commit()

        return _load_evaluation(conn, eval_id)
    finally:
        conn.close()


def _load_evaluation(conn, eval_id: int) -> dict:
    """Load full evaluation with criterion results."""
    ev = conn.execute("SELECT * FROM evaluations WHERE id = ?", (eval_id,)).fetchone()
    if not ev:
        raise HTTPException(404, "Evaluation not found")
    result = dict(ev)

    rows = conn.execute(
        "SELECT * FROM criterion_results WHERE evaluation_id = ? ORDER BY rowid",
        (eval_id,)
    ).fetchall()
    result["criteria"] = []
    for row in rows:
        r = dict(row)
        r["evidence"] = json.loads(r["evidence"]) if r["evidence"] else []
        r["checked_range"] = json.loads(r["checked_range"]) if r["checked_range"] else []
        result["criteria"].append(r)

    return result


@router.get("/api/evaluations/{eval_id}")
def get_evaluation(eval_id: int):
    conn = get_db()
    try:
        return _load_evaluation(conn, eval_id)
    finally:
        conn.close()


@router.get("/api/conversations/{conv_id}/evaluations")
def list_conversation_evaluations(conv_id: str):
    conn = get_db()
    try:
        rows = conn.execute(
            "SELECT * FROM evaluations WHERE conversation_id = ? ORDER BY id DESC",
            (conv_id,)
        ).fetchall()
        return [dict(r) for r in rows]
    finally:
        conn.close()
