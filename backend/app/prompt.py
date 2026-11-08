"""Builds evaluation prompts from checklist config + transcript."""
import json
from typing import Any


SYSTEM_PROMPT = """You are a Quality Assurance expert evaluating customer support operator performance.
You will receive a support conversation transcript and a list of evaluation criteria.

Your task: evaluate each criterion based ONLY on what is explicitly present in the transcript.
Do NOT invent or assume information not present. If evidence is insufficient, say so honestly.

Rules:
- Evaluate ONLY the operator's actions. Bot/system messages provide context only.
- For N/A: use it ONLY when the criterion explicitly allows it AND the N/A condition is met.
- For scale criteria: choose the step value that best matches the evidence.
- Evidence quotes must be SHORT (under 15 words) and from OPERATOR messages only when evaluating operator actions.
- msg_index refers to the 0-based index in the numbered transcript lines.
- Think step by step before giving your final answer.

Output: a JSON array ONLY. No extra text before or after. No markdown fences. No ```json. Start your response with [ and end with ].
IMPORTANT: "answer" field must always be "yes", "no", or "na" — NEVER null. For scale criteria use "yes" + scale_value for partial credit.
Each object:
{
  "criterion_id": "<id>",
  "answer": "yes" | "no" | "na",
  "scale_value": null | <number from allowed steps>,
  "explanation": "<brief reasoning in Russian, 1-3 sentences>",
  "evidence": [{"msg_index": <int>, "quote": "<short quote>"}],
  "checked_range": [<first_msg_index_checked>, <last_msg_index_checked>],
  "confidence": "high" | "low",
  "needs_review": false | true
}"""


def format_transcript(transcript: list[dict]) -> str:
    """Format transcript as numbered lines for the prompt."""
    lines = []
    for i, msg in enumerate(transcript):
        speaker = msg.get("speaker", "unknown")
        ts = msg.get("timestamp", "")
        text = msg.get("text", "")
        lines.append(f"[{i}] {speaker} {ts}: {text}")
    return "\n".join(lines)


def format_criterion(crit: dict[str, Any]) -> str:
    """Format a single criterion for the prompt."""
    parts = [f"ID: {crit['id']}"]
    parts.append(f"Description: {crit.get('title') or crit.get('description', '')}")
    parts.append(f"Type: {crit['type']}")
    parts.append(f"Weight: {crit['weight']}")

    if crit.get("na_condition"):
        parts.append(f"N/A allowed when: {crit['na_condition']}")
    else:
        parts.append("N/A: not allowed")

    if crit["type"] == "scale" and crit.get("scale_steps"):
        steps = crit["scale_steps"]
        parts.append(f"Scale steps: {steps}")
        if crit.get("scale_descriptions"):
            for step, desc in zip(steps, crit["scale_descriptions"]):
                parts.append(f"  {step}: {desc}")

    if crit.get("notes"):
        parts.append(f"Notes: {crit['notes']}")

    return "\n".join(parts)


def build_prompt(checklist_config: dict, transcript: list[dict], audio_metrics: dict | None = None) -> tuple[str, str]:
    """
    Build system + user prompts for evaluation.
    Returns (system_prompt, user_prompt).
    """
    criteria = checklist_config.get("criteria", [])
    channel = checklist_config.get("channel", "unknown")

    transcript_text = format_transcript(transcript)

    criteria_text = "\n\n".join(format_criterion(c) for c in criteria)

    audio_block = ""
    if audio_metrics and channel == "voice call":
        from .audio_analysis import build_audio_context
        audio_block = build_audio_context(audio_metrics) + "\n"

    user_prompt = f"""Channel: {channel}
{audio_block}Transcript ({len(transcript)} messages):
{transcript_text}

---
Evaluate the following {len(criteria)} criteria:

{criteria_text}

---
Respond with a JSON array of {len(criteria)} objects, one per criterion above.
Think through each criterion carefully. Use N/A only when explicitly allowed and the condition is clearly met."""

    return SYSTEM_PROMPT, user_prompt
