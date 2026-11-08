"""Tests for prompt builder, validator, and evaluation pipeline."""
import json
import pytest
from unittest.mock import patch, AsyncMock, MagicMock

from backend.app.prompt import build_prompt, format_transcript
from backend.app.validator import validate_llm_response, ValidationError
from backend.app.scoring import points_for_result
from decimal import Decimal


SAMPLE_TRANSCRIPT = [
    {"speaker": "bot", "timestamp": "00:00", "text": "Добро пожаловать!"},
    {"speaker": "client", "timestamp": "00:01", "text": "Привет, помогите с картой"},
    {"speaker": "operator", "timestamp": "00:02", "text": "Здравствуйте! Я Алексей, рад помочь."},
    {"speaker": "operator", "timestamp": "00:03", "text": "Уточните, пожалуйста, какая у вас проблема?"},
]

SAMPLE_CRITERIA = [
    {"id": "c01", "title": "Greeting", "type": "bool", "weight": 10, "na_condition": None},
    {"id": "c04", "title": "Quality", "type": "scale", "weight": 20,
     "scale_steps": [0, 5, 10, 15, 20], "na_condition": "chat ended before request"},
    {"id": "c08", "title": "Gross error", "type": "flag", "weight": 0, "na_condition": None},
]

SAMPLE_CONFIG = {"channel": "agent chat", "criteria": SAMPLE_CRITERIA}


# ─── Prompt builder tests ────────────────────────────────────────────────────

def test_format_transcript():
    result = format_transcript(SAMPLE_TRANSCRIPT)
    assert "[0] bot 00:00" in result
    assert "[2] operator 00:02" in result
    assert "Здравствуйте" in result


def test_build_prompt_includes_criteria():
    system, user = build_prompt(SAMPLE_CONFIG, SAMPLE_TRANSCRIPT)
    assert "c01" in user
    assert "c04" in user
    assert "c08" in user
    assert "agent chat" in user
    assert len(system) > 100


def test_build_prompt_includes_transcript():
    system, user = build_prompt(SAMPLE_CONFIG, SAMPLE_TRANSCRIPT)
    assert "Здравствуйте" in user
    assert "Добро пожаловать" in user


# ─── Validator tests ─────────────────────────────────────────────────────────

def _make_valid_response():
    return json.dumps([
        {"criterion_id": "c01", "answer": "yes", "scale_value": None,
         "explanation": "Поздоровался", "evidence": [{"msg_index": 2, "quote": "Здравствуйте!"}],
         "checked_range": [0, 3], "confidence": "high", "needs_review": False},
        {"criterion_id": "c04", "answer": "yes", "scale_value": 15,
         "explanation": "Хороший ответ", "evidence": [],
         "checked_range": [0, 3], "confidence": "high", "needs_review": False},
        {"criterion_id": "c08", "answer": "no", "scale_value": None,
         "explanation": "Нет грубых ошибок", "evidence": [],
         "checked_range": [0, 3], "confidence": "high", "needs_review": False},
    ])


def test_validate_valid_response():
    result = validate_llm_response(_make_valid_response(), SAMPLE_CRITERIA, SAMPLE_TRANSCRIPT)
    assert len(result) == 3
    c01 = next(r for r in result if r["criterion_id"] == "c01")
    assert c01["answer"] == "yes"
    assert c01["evidence"][0]["msg_index"] == 2


def test_validate_invalid_json():
    with pytest.raises(ValidationError, match="Invalid JSON"):
        validate_llm_response("not json", SAMPLE_CRITERIA, SAMPLE_TRANSCRIPT)


def test_validate_missing_criterion():
    partial = json.dumps([
        {"criterion_id": "c01", "answer": "yes", "scale_value": None,
         "explanation": "ok", "evidence": [], "checked_range": [0, 3],
         "confidence": "high", "needs_review": False},
    ])
    with pytest.raises(ValidationError, match="Missing criteria"):
        validate_llm_response(partial, SAMPLE_CRITERIA, SAMPLE_TRANSCRIPT)


def test_validate_na_not_allowed():
    response = json.dumps([
        {"criterion_id": "c01", "answer": "na", "scale_value": None,
         "explanation": "n/a", "evidence": [], "checked_range": [0, 3],
         "confidence": "high", "needs_review": False},
        {"criterion_id": "c04", "answer": "yes", "scale_value": 10,
         "explanation": "ok", "evidence": [], "checked_range": [0, 3],
         "confidence": "high", "needs_review": False},
        {"criterion_id": "c08", "answer": "no", "scale_value": None,
         "explanation": "no", "evidence": [], "checked_range": [0, 3],
         "confidence": "high", "needs_review": False},
    ])
    with pytest.raises(ValidationError):
        validate_llm_response(response, SAMPLE_CRITERIA, SAMPLE_TRANSCRIPT)


def test_validate_bad_scale_value():
    response = json.dumps([
        {"criterion_id": "c01", "answer": "yes", "scale_value": None,
         "explanation": "ok", "evidence": [], "checked_range": [0, 3],
         "confidence": "high", "needs_review": False},
        {"criterion_id": "c04", "answer": "yes", "scale_value": 7,  # 7 not in [0,5,10,15,20]
         "explanation": "bad", "evidence": [], "checked_range": [0, 3],
         "confidence": "high", "needs_review": False},
        {"criterion_id": "c08", "answer": "no", "scale_value": None,
         "explanation": "no", "evidence": [], "checked_range": [0, 3],
         "confidence": "high", "needs_review": False},
    ])
    with pytest.raises(ValidationError, match="scale_value"):
        validate_llm_response(response, SAMPLE_CRITERIA, SAMPLE_TRANSCRIPT)


def test_validate_bad_evidence_index():
    response = json.dumps([
        {"criterion_id": "c01", "answer": "yes", "scale_value": None,
         "explanation": "ok",
         "evidence": [{"msg_index": 99, "quote": "oops"}],  # out of range
         "checked_range": [0, 3], "confidence": "high", "needs_review": False},
        {"criterion_id": "c04", "answer": "yes", "scale_value": 10,
         "explanation": "ok", "evidence": [], "checked_range": [0, 3],
         "confidence": "high", "needs_review": False},
        {"criterion_id": "c08", "answer": "no", "scale_value": None,
         "explanation": "no", "evidence": [], "checked_range": [0, 3],
         "confidence": "high", "needs_review": False},
    ])
    with pytest.raises(ValidationError, match="out of range"):
        validate_llm_response(response, SAMPLE_CRITERIA, SAMPLE_TRANSCRIPT)


def test_validate_na_allowed_for_c04():
    criteria_with_na = [
        {"id": "c01", "title": "Greeting", "type": "bool", "weight": 10, "na_condition": None},
        {"id": "c04", "title": "Quality", "type": "scale", "weight": 20,
         "scale_steps": [0, 5, 10, 15, 20], "na_condition": "chat ended before request"},
        {"id": "c08", "title": "Gross error", "type": "flag", "weight": 0, "na_condition": None},
    ]
    response = json.dumps([
        {"criterion_id": "c01", "answer": "yes", "scale_value": None,
         "explanation": "ok", "evidence": [], "checked_range": [0, 3],
         "confidence": "high", "needs_review": False},
        {"criterion_id": "c04", "answer": "na", "scale_value": None,
         "explanation": "чат оборвался", "evidence": [], "checked_range": [0, 3],
         "confidence": "high", "needs_review": False},
        {"criterion_id": "c08", "answer": "no", "scale_value": None,
         "explanation": "no", "evidence": [], "checked_range": [0, 3],
         "confidence": "high", "needs_review": False},
    ])
    result = validate_llm_response(response, criteria_with_na, SAMPLE_TRANSCRIPT)
    c04 = next(r for r in result if r["criterion_id"] == "c04")
    assert c04["answer"] == "na"
