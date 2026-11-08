from decimal import Decimal
from backend.app.scoring import compute_total, points_for_result, scale_points

# Default chat checklist config (weights only, enough for scoring)
CHAT_CONFIG = [
    {"id": "c01", "weight": 10, "type": "yes_no",    "scale_steps": None},
    {"id": "c02", "weight": 15, "type": "yes_no_na", "scale_steps": None},
    {"id": "c03", "weight": 20, "type": "yes_no_na", "scale_steps": None},
    {"id": "c04", "weight": 20, "type": "scale",     "scale_steps": [0, 5, 10, 15, 20]},
    {"id": "c05", "weight": 15, "type": "yes_no",    "scale_steps": None},
    {"id": "c06", "weight": 15, "type": "scale",     "scale_steps": [0, 4, 7, 10]},
    {"id": "c07", "weight": 5,  "type": "yes_no_na", "scale_steps": None},
    {"id": "c08", "weight": 0,  "type": "flag",      "scale_steps": None},
]


def test_reference_case_69_38():
    """
    From CLAUDE.md spec:
    c03=N/A, c01=yes(10), c02=no(0), c04=scale15(15), c05=yes(15),
    c06=scale7(10.5), c07=yes(5) → 55.5/80*100 = 69.38
    """
    results = [
        {"criterion_id": "c01", "answer": "yes",   "scale_value": None,  "points": "10"},
        {"criterion_id": "c02", "answer": "no",    "scale_value": None,  "points": "0"},
        {"criterion_id": "c03", "answer": "na",    "scale_value": None,  "points": None},
        {"criterion_id": "c04", "answer": "scale", "scale_value": 15,    "points": "15"},
        {"criterion_id": "c05", "answer": "yes",   "scale_value": None,  "points": "15"},
        {"criterion_id": "c06", "answer": "scale", "scale_value": 7,     "points": "10.5"},
        {"criterion_id": "c07", "answer": "yes",   "scale_value": None,  "points": "5"},
        {"criterion_id": "c08", "answer": "no",    "scale_value": None,  "points": None},
    ]
    total = compute_total(results, CHAT_CONFIG)
    assert total == "69.38", f"Expected 69.38, got {total}"


def test_round_half_up_50_625():
    """50.625 must round to 50.63 (ROUND_HALF_UP), not 50.62 (banker's rounding)."""
    # Construct a case that produces exactly 50.625
    # weights sum = 80 (c03=N/A), points = 50.625/100*80 = 40.5
    results = [
        {"criterion_id": "c01", "answer": "yes",   "scale_value": None, "points": "10"},
        {"criterion_id": "c02", "answer": "no",    "scale_value": None, "points": "0"},
        {"criterion_id": "c03", "answer": "na",    "scale_value": None, "points": None},
        {"criterion_id": "c04", "answer": "scale", "scale_value": 5,    "points": "5"},
        {"criterion_id": "c05", "answer": "yes",   "scale_value": None, "points": "15"},
        {"criterion_id": "c06", "answer": "scale", "scale_value": 7,    "points": "10.5"},
        {"criterion_id": "c07", "answer": "yes",   "scale_value": None, "points": "5"},
        {"criterion_id": "c08", "answer": "no",    "scale_value": None, "points": None},
    ]
    # 10+0+5+15+10.5+5 = 45.5 / 80 * 100 = 56.875 → 56.88
    # Need to construct 50.625 exactly: 40.5/80*100 = 50.625
    # points: c01=10, c04=5, c06=10.5, c07=5 → sum=30.5+10=40.5
    # Actually let me just test with known inputs
    results2 = [
        {"criterion_id": "c01", "answer": "yes",   "scale_value": None, "points": "10"},
        {"criterion_id": "c02", "answer": "no",    "scale_value": None, "points": "0"},
        {"criterion_id": "c03", "answer": "na",    "scale_value": None, "points": None},
        {"criterion_id": "c04", "answer": "no",    "scale_value": None, "points": "0"},
        {"criterion_id": "c05", "answer": "yes",   "scale_value": None, "points": "15"},
        {"criterion_id": "c06", "answer": "scale", "scale_value": 7,    "points": "10.5"},
        {"criterion_id": "c07", "answer": "yes",   "scale_value": None, "points": "5"},
        {"criterion_id": "c08", "answer": "no",    "scale_value": None, "points": None},
    ]
    # 10+0+0+15+10.5+5=40.5 / 80 * 100 = 50.625 → ROUND_HALF_UP → 50.63
    total = compute_total(results2, CHAT_CONFIG)
    assert total == "50.63", f"Expected 50.63, got {total}"


def test_all_na_returns_none():
    results = [
        {"criterion_id": "c01", "answer": "na",  "scale_value": None, "points": None},
        {"criterion_id": "c02", "answer": "na",  "scale_value": None, "points": None},
        {"criterion_id": "c03", "answer": "na",  "scale_value": None, "points": None},
        {"criterion_id": "c04", "answer": "na",  "scale_value": None, "points": None},
        {"criterion_id": "c05", "answer": "na",  "scale_value": None, "points": None},
        {"criterion_id": "c06", "answer": "na",  "scale_value": None, "points": None},
        {"criterion_id": "c07", "answer": "na",  "scale_value": None, "points": None},
        {"criterion_id": "c08", "answer": "no",  "scale_value": None, "points": None},
    ]
    total = compute_total(results, CHAT_CONFIG)
    assert total is None


def test_perfect_score():
    results = [
        {"criterion_id": "c01", "answer": "yes",   "scale_value": None, "points": "10"},
        {"criterion_id": "c02", "answer": "yes",   "scale_value": None, "points": "15"},
        {"criterion_id": "c03", "answer": "yes",   "scale_value": None, "points": "20"},
        {"criterion_id": "c04", "answer": "scale", "scale_value": 20,   "points": "20"},
        {"criterion_id": "c05", "answer": "yes",   "scale_value": None, "points": "15"},
        {"criterion_id": "c06", "answer": "scale", "scale_value": 10,   "points": "15"},
        {"criterion_id": "c07", "answer": "yes",   "scale_value": None, "points": "5"},
        {"criterion_id": "c08", "answer": "no",    "scale_value": None, "points": None},
    ]
    total = compute_total(results, CHAT_CONFIG)
    assert total == "100.00"


def test_scale_points_c06():
    # c06 weight=15, max_step=10, step=7 → 15*7/10 = 10.5
    pts = scale_points(15, 7, 10)
    assert pts == Decimal("10.50")


def test_points_for_result_yes():
    cfg = {"id": "c01", "weight": 10, "type": "yes_no", "scale_steps": None}
    pts = points_for_result("yes", None, cfg)
    assert pts == Decimal("10")


def test_points_for_result_na():
    cfg = {"id": "c03", "weight": 20, "type": "yes_no_na", "scale_steps": None}
    pts = points_for_result("na", None, cfg)
    assert pts is None


def test_points_for_result_flag_ignored():
    cfg = {"id": "c08", "weight": 0, "type": "flag", "scale_steps": None}
    pts = points_for_result("yes", None, cfg)
    assert pts is None
