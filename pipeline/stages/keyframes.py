"""Keyframe stage: Character reference generation and shot keyframe synthesis."""

from __future__ import annotations

from datetime import datetime, timezone
import hashlib
import os
from pathlib import Path
import shutil
import time
import uuid

from pipeline.core import (
    append_run_log,
    atomic_write_bytes,
    is_cache_hit,
    read_sidecar_hash,
    sha256_inputs,
    write_sidecar_hash,
)
from pipeline.providers.cloudflare import FLUX_MODEL, generate_image

OUTPUTS_REFS_DIR = Path("outputs/references")
OUTPUTS_CANDIDATES_DIR = Path("outputs/references/candidates")
OUTPUTS_KEYFRAMES_DIR = Path("outputs/keyframes")

BASE_SEEDS = {
    "elder_01": 2000,
    "child_01": 3000,
    "neighbour_01": 4000,
}


def generate_reference_candidates(
    storyboard: dict,
    outputs_dir: Path = OUTPUTS_REFS_DIR,
    force: bool = False,
) -> dict[str, list[Path]]:
    """Generate 3 candidate portrait reference images per character at 768x768.

    Also sets outputs/references/{char_id}.png to default to _v1.png if not already chosen.
    """
    candidates_dir = outputs_dir / "candidates"
    candidates_dir.mkdir(parents=True, exist_ok=True)
    outputs_dir.mkdir(parents=True, exist_ok=True)

    style_block = storyboard.get("style_block", "")
    characters = storyboard.get("characters", {})

    cf_account_id = os.getenv("CF_ACCOUNT_ID", "").strip()
    cf_api_token = os.getenv("CF_API_TOKEN", "").strip()
    if not cf_account_id or not cf_api_token:
        raise ValueError("CF_ACCOUNT_ID and CF_API_TOKEN are required for image generation.")

    results: dict[str, list[Path]] = {}

    print(f"\n--- Generating Character Reference Candidates ({len(characters)} characters x 3 candidates) ---")

    for char_id, char_info in characters.items():
        results[char_id] = []
        base_seed = BASE_SEEDS.get(char_id, 1000)
        desc = char_info.get("description", "")
        portrait_prompt = (
            f"{style_block}, {desc}, character reference portrait, "
            f"front-facing three-quarter view, neutral warm lighting, "
            f"plain earthen background, clear face and hands, no text"
        )

        for version in (1, 2, 3):
            seed = base_seed + version
            out_file = candidates_dir / f"{char_id}_v{version}.png"
            results[char_id].append(out_file)

            input_fields = {
                "char_id": char_id,
                "version": version,
                "prompt": portrait_prompt,
                "seed": seed,
                "width": 768,
                "height": 768,
                "model": FLUX_MODEL,
                "steps": 4,
            }
            input_hash = sha256_inputs(input_fields)

            # Check cache
            if not force and is_cache_hit(out_file, input_hash):
                print(f"[{char_id}_v{version}] Cache Hit -> {out_file.name}")
                append_run_log({
                    "run_id": f"ref_{char_id}_v{version}_{uuid.uuid4().hex[:8]}",
                    "stage": "references",
                    "shot_id": None,
                    "provider": "cloudflare",
                    "model": FLUX_MODEL,
                    "seed": seed,
                    "parameters": {"width": 768, "height": 768, "steps": 4, "version": version},
                    "input_hash": input_hash,
                    "output": str(out_file).replace("\\", "/"),
                    "latency_seconds": 0.0,
                    "cost_usd": 0.0,
                    "cache_hit": True,
                    "status": "success",
                    "timestamp": datetime.now(timezone.utc).isoformat(),
                })
                continue

            # Generate candidate image via Cloudflare FLUX
            start_time = time.perf_counter()
            img_bytes = generate_image(
                prompt=portrait_prompt,
                width=768,
                height=768,
                steps=4,
                seed=seed,
                model=FLUX_MODEL,
                account_id=cf_account_id,
                api_token=cf_api_token,
            )
            latency_seconds = round(time.perf_counter() - start_time, 3)

            atomic_write_bytes(out_file, img_bytes)
            write_sidecar_hash(out_file, input_hash)

            print(f"[{char_id}_v{version}] Generated -> {out_file.name} ({latency_seconds}s)")

            append_run_log({
                "run_id": f"ref_{char_id}_v{version}_{uuid.uuid4().hex[:8]}",
                "stage": "references",
                "shot_id": None,
                "provider": "cloudflare",
                "model": FLUX_MODEL,
                "seed": seed,
                "parameters": {"width": 768, "height": 768, "steps": 4, "version": version},
                "input_hash": input_hash,
                "output": str(out_file).replace("\\", "/"),
                "latency_seconds": latency_seconds,
                "cost_usd": 0.0,
                "cache_hit": False,
                "status": "success",
                "timestamp": datetime.now(timezone.utc).isoformat(),
            })

        # Set default active reference to _v1.png ONLY if not already chosen
        active_ref = outputs_dir / f"{char_id}.png"
        if not active_ref.exists():
            v1_path = candidates_dir / f"{char_id}_v1.png"
            if v1_path.exists():
                shutil.copy2(v1_path, active_ref)
                v1_hash = read_sidecar_hash(v1_path)
                if v1_hash:
                    write_sidecar_hash(active_ref, v1_hash)
                print(f"[{char_id}] Set active reference -> {active_ref.name} (default: v1)")

    return results


def run_keyframes(
    storyboard: dict,
    target_shot_id: str | None = None,
    outputs_dir: Path = OUTPUTS_KEYFRAMES_DIR,
    force: bool = False,
) -> dict[str, Path]:
    """Generate 1280x704 16:9 keyframe images using FLUX.2 Klein 4B with character references."""
    outputs_dir.mkdir(parents=True, exist_ok=True)
    style_block = storyboard.get("style_block", "")
    shots = storyboard.get("shots", [])

    cf_account_id = os.getenv("CF_ACCOUNT_ID", "").strip()
    cf_api_token = os.getenv("CF_API_TOKEN", "").strip()
    if not cf_account_id or not cf_api_token:
        raise ValueError("CF_ACCOUNT_ID and CF_API_TOKEN are required for keyframe generation.")

    results: dict[str, Path] = {}

    print(f"\n--- Generating Keyframes (1280x704, 16:9) ---")

    for shot in shots:
        shot_id = shot["id"]
        if target_shot_id and shot_id != target_shot_id:
            continue

        out_path = outputs_dir / f"{shot_id}.png"
        results[shot_id] = out_path

        # Resolve character descriptions and reference images
        char_refs = shot.get("character_refs", [])
        ref_image_paths = []
        ref_hashes: dict[str, str] = {}

        for cid in char_refs:
            ref_path = OUTPUTS_REFS_DIR / f"{cid}.png"
            if ref_path.is_file():
                ref_image_paths.append(ref_path)
                ref_bytes = ref_path.read_bytes()
                ref_hashes[cid] = hashlib.sha256(ref_bytes).hexdigest()

        char_descs_list = []
        for cid in shot.get("characters_in_shot", []):
            cd = storyboard.get("characters", {}).get(cid, {}).get("description")
            if cd:
                char_descs_list.append(cd)
        char_descs = " ".join(char_descs_list)

        full_prompt = (
            f"{style_block}. {char_descs} {shot['image_prompt']} "
            f"Subject centered in middle of frame for vertical 9:16 crop compatibility, "
            f"realistic hands and proportions, no text or watermarks."
        )

        input_fields = {
            "model": FLUX_MODEL,
            "width": 1280,
            "height": 704,
            "seed": shot.get("seed", 1001),
            "style_block": style_block,
            "characters": char_descs,
            "image_prompt": shot["image_prompt"],
            "ref_hashes": ref_hashes,
            "steps": 4,
        }
        input_hash = sha256_inputs(input_fields)

        # Check incremental cache
        if not force and is_cache_hit(out_path, input_hash):
            print(f"[{shot_id}] Cache Hit -> {out_path.name}")
            append_run_log({
                "run_id": f"keyframe_{shot_id}_{uuid.uuid4().hex[:8]}",
                "stage": "keyframes",
                "shot_id": shot_id,
                "provider": "cloudflare",
                "model": FLUX_MODEL,
                "seed": shot.get("seed", 1001),
                "parameters": {"width": 1280, "height": 704, "steps": 4, "ref_chars": char_refs},
                "input_hash": input_hash,
                "output": str(out_path).replace("\\", "/"),
                "latency_seconds": 0.0,
                "cost_usd": 0.0,
                "cache_hit": True,
                "status": "success",
                "timestamp": datetime.now(timezone.utc).isoformat(),
            })
            continue

        # Generate keyframe via Cloudflare FLUX
        start_time = time.perf_counter()
        img_bytes = generate_image(
            prompt=full_prompt,
            width=1280,
            height=704,
            steps=4,
            seed=shot.get("seed", 1001),
            ref_image_paths=ref_image_paths,
            model=FLUX_MODEL,
            account_id=cf_account_id,
            api_token=cf_api_token,
        )
        latency_seconds = round(time.perf_counter() - start_time, 3)

        atomic_write_bytes(out_path, img_bytes)
        write_sidecar_hash(out_path, input_hash)

        print(f"[{shot_id}] Generated -> {out_path.name} ({latency_seconds}s)")

        append_run_log({
            "run_id": f"keyframe_{shot_id}_{uuid.uuid4().hex[:8]}",
            "stage": "keyframes",
            "shot_id": shot_id,
            "provider": "cloudflare",
            "model": FLUX_MODEL,
            "seed": shot.get("seed", 1001),
            "parameters": {"width": 1280, "height": 704, "steps": 4, "ref_chars": char_refs},
            "input_hash": input_hash,
            "output": str(out_path).replace("\\", "/"),
            "latency_seconds": latency_seconds,
            "cost_usd": 0.0,
            "cache_hit": False,
            "status": "success",
            "timestamp": datetime.now(timezone.utc).isoformat(),
        })

    return results
