"""Validates LLM response against checklist config and transcript."""
import json
from typing import Any


class ValidationError(Exception):
    pass


def validate_llm_response(
    raw: str,
    criteria_config: list[dict[str, Any]],
    transcript: list[dict],
) -> list[dict]:
    """
    Parse and validate LLM JSON response.
    Returns list of validated criterion result dicts.
    Raises ValidationError with description of the problem.
    """
    # Strip markdown code fences if present
    text = raw.strip()
    if text.startswith("```"):
        lines = text.splitlines()
        # remove first line (```json or ```) and last line (```)
        inner = lines[1:] if lines[0].startswith("```") else lines
        if inner and inner[-1].strip() == "```":
            inner = inner[:-1]
        text = "\n".join(inner).strip()

    try:
        data = json.loads(text)
    except json.JSONDecodeError as e:
        raise ValidationError(f"Invalid JSON: {e}") from e

    if not isinstance(data, list):
        raise ValidationError(f"Expected JSON array, got {type(data).__name__}")

    criteria_by_id = {c["id"]: c for c in criteria_config}
    expected_ids = set(criteria_by_id.keys())
    returned_ids = {item.get("criterion_id") for item in data if isinstance(item, dict)}

    missing = expected_ids - returned_ids
    if missing:
        raise ValidationError(f"Missing criteria in response: {missing}")

    operator_indices = {
        i for i, msg in enumerate(transcript) if msg.get("speaker") == "operator"
    }

    validated = []
    for item in data:
        if not isinstance(item, dict):
            raise ValidationError(f"Expected dict, got {type(item).__name__}: {item}")

        cid = item.get("criterion_id")
        if cid not in criteria_by_id:
            raise ValidationError(f"Unknown criterion_id: {cid!r}")

        cfg = criteria_by_id[cid]
        raw_answer = item.get("answer")
        # For scale criteria Claude sometimes returns null answer + scale_value → treat as "yes"
        if raw_answer is None and cfg.get("type") == "scale" and item.get("scale_value") is not None:
            raw_answer = "yes"
        elif raw_answer is None:
            raise ValidationError(f"{cid}: answer is null")
        answer = str(raw_answer).lower()
        scale_value = item.get("scale_value")
        explanation = item.get("explanation", "")
        evidence = item.get("evidence", [])
        confidence = item.get("confidence", "high")

        # Validate answer value
        ctype = cfg.get("type", "bool")
        if ctype == "flag":
            if answer not in ("yes", "no"):
                raise ValidationError(f"{cid}: flag type must be yes/no, got {answer!r}")
        elif ctype == "bool":
            allowed = ["yes", "no"]
            if cfg.get("na_condition"):
                allowed.append("na")
            if answer not in allowed:
                raise ValidationError(f"{cid}: got {answer!r}, allowed: {allowed}")
        elif ctype == "scale":
            allowed_ans = ["na"] if cfg.get("na_condition") else []
            # for scale, answer should be "yes"/"no"/"na" or we just accept any
            if answer not in ("yes", "no", "na"):
                raise ValidationError(f"{cid}: scale answer must be yes/no/na, got {answer!r}")

        # N/A check: only allowed if na_condition defined
        if answer == "na" and not cfg.get("na_condition"):
            raise ValidationError(f"{cid}: N/A not allowed (no na_condition defined)")

        # Scale value check
        if ctype == "scale" and answer != "na":
            steps = cfg.get("scale_steps", [])
            if scale_value is None:
                raise ValidationError(f"{cid}: scale_value required for scale type")
            if scale_value not in steps:
                raise ValidationError(
                    f"{cid}: scale_value {scale_value} not in allowed steps {steps}"
                )
        elif ctype != "scale":
            scale_value = None  # ignore scale_value for non-scale

        # Evidence index validation
        validated_evidence = []
        for ev in evidence:
            if not isinstance(ev, dict):
                continue
            idx = ev.get("msg_index")
            if idx is None:
                continue
            if not isinstance(idx, int) or idx < 0 or idx >= len(transcript):
                raise ValidationError(
                    f"{cid}: evidence msg_index {idx} out of range (transcript has {len(transcript)} messages)"
                )
            validated_evidence.append({"msg_index": idx, "quote": str(ev.get("quote", ""))[:200]})

        # checked_range validation
        checked_range = item.get("checked_range")
        if checked_range and isinstance(checked_range, (list, tuple)) and len(checked_range) == 2:
            cr = [int(checked_range[0]), int(checked_range[1])]
        else:
            cr = [0, len(transcript) - 1] if transcript else [0, 0]

        validated.append({
            "criterion_id": cid,
            "answer": answer,
            "scale_value": scale_value,
            "explanation": str(explanation)[:1000],
            "evidence": validated_evidence,
            "checked_range": cr,
            "confidence": confidence if confidence in ("high", "low") else "high",
            "needs_review": bool(item.get("needs_review", False)),
        })

    return validated
