import json
from pathlib import Path

import pytest

from backend.app.models import ChecklistConfig

SEED_DIR = Path(__file__).parent.parent.parent / "seed"
SEED_FILES = ["checklist_chat.json", "checklist_call.json"]


@pytest.mark.parametrize("name", SEED_FILES)
def test_seed_matches_model(name):
    raw = json.loads((SEED_DIR / name).read_text(encoding="utf-8"))
    cfg = ChecklistConfig(**raw)
    assert cfg.general_rules, "general evaluation rules must be present"
    ids = [c.id for c in cfg.criteria]
    assert len(ids) == len(set(ids)), "criterion ids must be unique"


@pytest.mark.parametrize("name", SEED_FILES)
def test_seed_criteria_have_guidance_and_scales(name):
    raw = json.loads((SEED_DIR / name).read_text(encoding="utf-8"))
    cfg = ChecklistConfig(**raw)
    for c in cfg.criteria:
        assert c.guidance, f"{c.id}: guidance is empty"
        if c.type == "scale":
            assert c.scale_steps, f"{c.id}: scale without steps"
            assert set(c.scale_descriptions) == {str(s) for s in c.scale_steps}


def test_guidance_is_optional_for_new_criteria():
    # A criterion added from the UI may have no guidance or general rules yet.
    cfg = ChecklistConfig(criteria=[{
        "id": "c09", "title": "Новый критерий", "type": "yes_no", "weight": 5,
    }])
    assert cfg.criteria[0].guidance is None
    assert cfg.general_rules == []
