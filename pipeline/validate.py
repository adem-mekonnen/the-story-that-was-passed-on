"""Storyboard schema and business rule validation."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import jsonschema

__all__ = [
    "load_storyboard",
    "validate_schema",
    "validate_business_rules",
    "validate_all",
]


def load_storyboard(path: Path) -> dict[str, Any]:
    """Load and parse the storyboard JSON contract."""
    path = Path(path)
    if not path.is_file():
        raise FileNotFoundError(f"Storyboard file not found: {path}")
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def validate_schema(storyboard: dict[str, Any], schema_path: Path) -> None:
    """Validate storyboard structure against strict JSON schema."""
    schema_path = Path(schema_path)
    if not schema_path.is_file():
        raise FileNotFoundError(f"Schema file not found: {schema_path}")
    with open(schema_path, "r", encoding="utf-8") as f:
        schema = json.load(f)
    jsonschema.validate(instance=storyboard, schema=schema)


def validate_business_rules(storyboard: dict[str, Any]) -> None:
    """Validate business rules: unique shot IDs, duration constraints, valid characters, and aspect ratios."""
    shots = storyboard.get("shots", [])
    end_card = storyboard.get("end_card", {})
    characters = storyboard.get("characters", {})
    aspect_ratios = storyboard.get("aspect_ratios", [])

    # 1. Unique shot IDs
    shot_ids = [s.get("id") for s in shots]
    seen_ids = set()
    duplicates = set()
    for sid in shot_ids:
        if sid in seen_ids:
            duplicates.add(sid)
        seen_ids.add(sid)
    if duplicates:
        raise ValueError(f"Duplicate shot IDs found: {sorted(duplicates)}")

    # 2. Duration constraint: 60 <= total <= 90
    shots_duration = sum(s.get("duration_seconds", 0) for s in shots)
    end_card_duration = end_card.get("duration_seconds", 0)
    total_duration = shots_duration + end_card_duration
    if not (60 <= total_duration <= 90):
        raise ValueError(
            f"Total duration ({total_duration}s) must be between 60 and 90 seconds inclusive. "
            f"(shots={shots_duration}s, end_card={end_card_duration}s)"
        )

    # 3. All character_refs and characters_in_shot exist in characters
    known_chars = set(characters.keys())
    for shot in shots:
        shot_id = shot.get("id", "unknown")
        for ref in shot.get("character_refs", []):
            if ref not in known_chars:
                raise ValueError(
                    f"Unknown character_ref '{ref}' in {shot_id}. Declared characters: {sorted(known_chars)}"
                )
        for char in shot.get("characters_in_shot", []):
            if char not in known_chars:
                raise ValueError(
                    f"Unknown characters_in_shot '{char}' in {shot_id}. Declared characters: {sorted(known_chars)}"
                )

    # 4. aspect_ratios contains both "9:16" and "16:9"
    required_ratios = {"9:16", "16:9"}
    ratios_set = set(aspect_ratios)
    if not required_ratios.issubset(ratios_set):
        raise ValueError(
            f"aspect_ratios must contain both '9:16' and '16:9', found: {aspect_ratios}"
        )


def validate_all(storyboard_path: Path, schema_path: Path) -> dict[str, Any]:
    """Run full validation pipeline: load, schema check, and business rules check."""
    storyboard = load_storyboard(storyboard_path)
    validate_schema(storyboard, schema_path)
    validate_business_rules(storyboard)
    return storyboard
