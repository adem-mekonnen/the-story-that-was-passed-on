"""Entry point for The Story That Was Passed On production pipeline."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from pipeline.validate import validate_all


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="The Story That Was Passed On - AI Media Production Pipeline"
    )
    parser.add_argument(
        "--storyboard",
        type=Path,
        default=Path("storyboard.json"),
        help="Path to storyboard contract JSON (default: storyboard.json)",
    )
    parser.add_argument(
        "--schema",
        type=Path,
        default=Path("schema/storyboard.schema.json"),
        help="Path to storyboard JSON schema (default: schema/storyboard.schema.json)",
    )
    parser.add_argument(
        "--shot",
        type=str,
        default=None,
        help="Optional shot ID to process (e.g. shot_01)",
    )
    parser.add_argument(
        "--stage",
        type=str,
        choices=["script", "narration", "keyframes", "shots", "music", "assemble", "all"],
        default="all",
        help="Pipeline stage to execute (script, narration, keyframes, shots, music, assemble, or all; default: all)",
    )
    parser.add_argument(
        "--language",
        type=str,
        choices=["en", "am", "om"],
        default="en",
        help="Audio and subtitle localization language: en (English, default), am (Amharic), om (Afaan Oromo)",
    )
    parser.add_argument(
        "--refs-only",
        action="store_true",
        help="Generate character reference candidate portraits only",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Validate storyboard and plan execution without generating assets",
    )
    parser.add_argument(
        "--no-gpu",
        action="store_true",
        help="Bypass GPU stages or use CPU/cloud endpoints only",
    )
    parser.add_argument(
        "--force",
        action="store_true",
        help="Bypass cache checks and regenerate assets",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)

    try:
        storyboard = validate_all(args.storyboard, args.schema)
        shots = storyboard.get("shots", [])
        shots_duration = sum(s.get("duration_seconds", 0) for s in shots)
        end_card_duration = storyboard.get("end_card", {}).get("duration_seconds", 0)
        total_duration = shots_duration + end_card_duration
        print(f"Validation OK: {len(shots)} shots, {total_duration}s total (Language: {args.language})")

        if args.dry_run:
            print("[dry-run] Validation succeeded; skipping media generation.")
            return 0

        # Execute Stages based on CLI arguments
        from dotenv import load_dotenv
        load_dotenv()

        if args.refs_only:
            from pipeline.stages.keyframes import generate_reference_candidates
            generate_reference_candidates(storyboard, force=args.force)
            return 0

        if args.stage in ("script", "all"):
            from pipeline.stages.script import run_script_stage
            run_script_stage(storyboard, language=args.language, force=args.force)

        if args.stage in ("narration", "all"):
            from pipeline.stages.narration import run_narration_stage
            run_narration_stage(storyboard, language=args.language, force=args.force)

        if args.stage in ("keyframes", "all"):
            from pipeline.stages.keyframes import generate_reference_candidates, run_keyframes
            generate_reference_candidates(storyboard, force=args.force)
            run_keyframes(storyboard, target_shot_id=args.shot, force=args.force)

        if args.stage in ("shots", "all"):
            from pipeline.stages.shots import run_shots_stage
            run_shots_stage(storyboard, target_shot_id=args.shot, no_gpu=args.no_gpu, force=args.force)

        if args.stage in ("music", "all"):
            from pipeline.stages.music import run_music_stage
            run_music_stage(storyboard, force=args.force)

        if args.stage in ("assemble", "all"):
            from pipeline.stages.assemble import run_assemble_stage
            run_assemble_stage(storyboard, language=args.language, force=args.force)

        return 0
    except Exception as exc:
        print(f"Validation FAILED: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
