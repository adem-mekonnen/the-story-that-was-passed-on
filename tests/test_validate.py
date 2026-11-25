"""Tests for storyboard schema and business rule validation."""

from __future__ import annotations

import copy
from pathlib import Path

import jsonschema
import pytest

from pipeline.validate import (
    load_storyboard,
    validate_all,
    validate_business_rules,
    validate_schema,
)

SCHEMA_PATH = Path("schema/storyboard.schema.json")
STORYBOARD_PATH = Path("storyboard.json")


@pytest.fixture
def base_storyboard() -> dict:
    return load_storyboard(STORYBOARD_PATH)


def test_valid_storyboard_passes():
    """Valid storyboard passes complete validation pipeline."""
    storyboard = validate_all(STORYBOARD_PATH, SCHEMA_PATH)
    assert storyboard["project_title"] == "The Story That Was Passed On"
    assert len(storyboard["shots"]) == 10
    assert storyboard["target_duration_seconds"] == 79


def test_duplicate_shot_id_fails(base_storyboard: dict):
    """Duplicate shot IDs must fail business rule validation."""
    data = copy.deepcopy(base_storyboard)
    data["shots"][1]["id"] = "shot_01"
    with pytest.raises(ValueError, match="Duplicate shot IDs found"):
        validate_business_rules(data)


def test_total_duration_59s_fails(base_storyboard: dict):
    """Total duration of 59s (< 60s) must fail business rule validation."""
    data = copy.deepcopy(base_storyboard)
    for s in data["shots"]:
        s["duration_seconds"] = 8
    # Set 7 shots of 8s = 56s + 3s end card = 59s
    data["shots"] = data["shots"][:7]
    with pytest.raises(ValueError, match=r"Total duration \(59s\) must be between 60 and 90 seconds"):
        validate_business_rules(data)


def test_total_duration_91s_fails(base_storyboard: dict):
    """Total duration of 91s (> 90s) must fail business rule validation."""
    data = copy.deepcopy(base_storyboard)
    for s in data["shots"]:
        s["duration_seconds"] = 8
    # 10 shots of 8s = 80s + end card of 11s = 91s
    data["end_card"]["duration_seconds"] = 11
    with pytest.raises(ValueError, match=r"Total duration \(91s\) must be between 60 and 90 seconds"):
        validate_business_rules(data)


def test_unknown_character_ref_fails(base_storyboard: dict):
    """Unknown character reference in character_refs must fail business rules."""
    data = copy.deepcopy(base_storyboard)
    data["shots"][0]["character_refs"] = ["fictional_ghost_01"]
    with pytest.raises(ValueError, match="Unknown character_ref 'fictional_ghost_01'"):
        validate_business_rules(data)


def test_unknown_characters_in_shot_fails(base_storyboard: dict):
    """Unknown character in characters_in_shot must fail business rules."""
    data = copy.deepcopy(base_storyboard)
    data["shots"][0]["characters_in_shot"] = ["fictional_ghost_01"]
    with pytest.raises(ValueError, match="Unknown characters_in_shot 'fictional_ghost_01'"):
        validate_business_rules(data)


def test_missing_required_top_level_field_fails(base_storyboard: dict):
    """Missing top-level required field must fail schema validation."""
    data = copy.deepcopy(base_storyboard)
    del data["style_block"]
    with pytest.raises(jsonschema.ValidationError):
        validate_schema(data, SCHEMA_PATH)


def test_missing_required_shot_field_fails(base_storyboard: dict):
    """Missing required shot field must fail schema validation."""
    data = copy.deepcopy(base_storyboard)
    del data["shots"][0]["camera_shot"]
    with pytest.raises(jsonschema.ValidationError):
        validate_schema(data, SCHEMA_PATH)


def test_missing_required_aspect_ratio_fails(base_storyboard: dict):
    """Aspect ratios missing either 9:16 or 16:9 must fail business rules."""
    data = copy.deepcopy(base_storyboard)
    data["aspect_ratios"] = ["16:9"]
    with pytest.raises(ValueError, match="aspect_ratios must contain both '9:16' and '16:9'"):
        validate_business_rules(data)
