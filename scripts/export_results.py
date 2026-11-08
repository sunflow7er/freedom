#!/usr/bin/env python3
"""
Export evaluation results to the submission JSON format (schema_version 1.0).

Usage:
  python scripts/export_results.py DEV      -> results/dev/results.json
  python scripts/export_results.py FBroker  -> results/prod/results.json
"""
import json
import sys
import sqlite3
from pathlib import Path

DB_PATH = Path(__file__).parent.parent / "data" / "cqa.db"
RESULTS_DIR = Path(__file__).parent.parent / "results"

CRITERION_MAP = {
    "c01": "contact",
    "c02": "discovery",
    "c03": "identification",
    "c04": "consultation",
    "c05": "empathy",
    "c06": "dialogue",
    "c07": "closure",
    "c08": "critical",
}


def convert_value(cid: str, answer: str, scale_value):
    if answer == "na":
        return None
    if cid in ("c04", "c06"):
        # Scale criteria: return numeric step value
        return int(scale_value) if scale_value is not None else None
    # Boolean criteria
    return True if answer == "yes" else False


def export_group(group_id: str, output_path: Path):
    conn = sqlite3.connect(str(DB_PATH))
    conn.row_factory = sqlite3.Row

    convs = conn.execute(
        "SELECT id FROM conversations WHERE group_id = ? ORDER BY id",
        (group_id,),
    ).fetchall()

    if not convs:
        print(f"WARNING: no conversations found for group_id={group_id!r}")

    results = []
    for conv in convs:
        conv_id = conv["id"]

        ev = conn.execute(
            "SELECT * FROM evaluations WHERE conversation_id = ? AND status = 'done' "
            "ORDER BY id DESC LIMIT 1",
            (conv_id,),
        ).fetchone()

        if not ev:
            results.append({
                "conversation_id": conv_id,
                "status": "error",
                "criteria": [],
                "score": None,
                "error": "Диалог не оценён или оценка завершилась с ошибкой",
            })
            continue

        crit_rows = conn.execute(
            "SELECT * FROM criterion_results WHERE evaluation_id = ? ORDER BY rowid",
            (ev["id"],),
        ).fetchall()

        criteria = []
        critical_flag = False

        for r in crit_rows:
            cid = r["criterion_id"]
            export_id = CRITERION_MAP.get(cid, cid)
            value = convert_value(cid, r["answer"], r["scale_value"])

            if cid == "c08" and r["answer"] == "yes":
                critical_flag = True

            evidence_raw = json.loads(r["evidence"]) if r["evidence"] else []
            # PDF says: numbering from 1, including all speakers
            evidence_turns = [e["msg_index"] + 1 for e in evidence_raw if "msg_index" in e]

            criteria.append({
                "criterion_id": export_id,
                "value": value,
                "rationale": r["explanation"] or "",
                "evidence_turns": evidence_turns,
            })

        final_score = round(float(ev["total"]), 2) if ev["total"] is not None else None

        results.append({
            "conversation_id": conv_id,
            "status": "ok",
            "criteria": criteria,
            "score": {
                "final_score": final_score,
                "critical_flag": critical_flag,
            },
        })

    conn.close()

    output = {
        "schema_version": "1.0",
        "team_name": "CQA Team",
        "model": {"mode": "external_api", "name": "claude-sonnet-4-5"},
        "results": results,
    }

    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(
        json.dumps(output, ensure_ascii=False, indent=2), encoding="utf-8"
    )

    ok = sum(1 for r in results if r["status"] == "ok")
    err = sum(1 for r in results if r["status"] == "error")
    print(f"Exported {len(results)} conversations to {output_path}")
    print(f"  ok={ok}  error={err}")
    return len(results)


if __name__ == "__main__":
    group_id = sys.argv[1] if len(sys.argv) > 1 else "DEV"
    out_folder = "prod" if group_id.upper() != "DEV" else "dev"
    output_path = RESULTS_DIR / out_folder / "results.json"
    export_group(group_id, output_path)
