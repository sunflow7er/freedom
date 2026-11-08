from decimal import Decimal, ROUND_HALF_UP
from typing import Optional


def scale_points(weight: int, step: int, max_step: int) -> Decimal:
    """Convert a scale step to weighted points."""
    return (Decimal(weight) * Decimal(step) / Decimal(max_step)).quantize(
        Decimal("0.01"), rounding=ROUND_HALF_UP
    )


def compute_total(
    criterion_results: list[dict],
    criteria_config: list[dict],
) -> Optional[str]:
    """
    Compute the final score (0-100) from criterion results.

    criterion_results: list of dicts with keys:
        criterion_id, answer (yes/no/na), scale_value (int or None), points (Decimal str or None)
    criteria_config: list of dicts with keys:
        id, weight (int), type, scale_steps (list[int] or None)

    Returns the score as a string (Decimal) rounded ROUND_HALF_UP to 2 places,
    or None if there are no applicable criteria with weight > 0.
    """
    config_map = {c["id"]: c for c in criteria_config}

    total_points = Decimal("0")
    total_weight = Decimal("0")

    for result in criterion_results:
        cid = result["criterion_id"]
        answer = result["answer"]
        cfg = config_map.get(cid)
        if cfg is None:
            continue

        weight = cfg["weight"]
        if weight == 0:
            continue

        if answer == "na":
            continue

        total_weight += Decimal(weight)

        # Always use pre-computed points when available (handles scale partial credit)
        pts = result.get("points")
        if pts is not None:
            total_points += Decimal(str(pts))
        elif answer == "yes":
            total_points += Decimal(weight)
        # answer == "no" → 0 points, nothing to add

    if total_weight == 0:
        return None

    raw = total_points / total_weight * Decimal("100")
    return str(raw.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP))


def points_for_result(answer: str, scale_value: Optional[int], cfg: dict) -> Optional[Decimal]:
    """
    Compute points for a single criterion result.
    Returns None for N/A or zero-weight criteria.
    """
    if cfg["weight"] == 0 or answer == "na":
        return None
    if answer == "no":
        return Decimal("0")
    if answer == "yes":
        # For scale criteria, use scale_value to compute partial credit
        if cfg.get("type") == "scale" and scale_value is not None and cfg.get("scale_steps"):
            max_step = max(cfg["scale_steps"])
            return scale_points(cfg["weight"], scale_value, max_step)
        return Decimal(cfg["weight"])
    # Legacy path: scale answer returned as numeric string (not used currently)
    if scale_value is None:
        return Decimal("0")
    max_step = max(cfg["scale_steps"])
    return scale_points(cfg["weight"], scale_value, max_step)
