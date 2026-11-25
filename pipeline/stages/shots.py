"""Shots stage: Synthesizes individual video clips via Wan 2.2 clips or FFmpeg Ken Burns."""

from __future__ import annotations

from datetime import datetime, timezone
import hashlib
from pathlib import Path
import subprocess
import time
import uuid

from pipeline.core import (
    append_run_log,
    is_cache_hit,
    sha256_inputs,
    write_sidecar_hash,
)
from pipeline.providers.kaggle_wan import (
    FFMPEG_BIN,
    find_wan_clip,
    import_kaggle_telemetry,
    process_wan_clip,
)

OUTPUTS_SHOTS_DIR = Path("outputs/shots")
OUTPUTS_KEYFRAMES_DIR = Path("outputs/keyframes")


def run_ken_burns(
    keyframe_path: Path,
    output_path: Path,
    duration: float,
    shot_index: int,
    fps: int = 24,
) -> tuple[str, float]:
    """Render a dynamic Ken Burns pan/zoom video clip from a keyframe image."""
    output_path.parent.mkdir(parents=True, exist_ok=True)
    tmp_path = output_path.with_name(f"{output_path.name}.tmp.mp4")

    total_frames = int(round(duration * fps))
    motion_idx = shot_index % 4

    if motion_idx == 0:
        motion_type = "zoom_in_center"
        zoompan_expr = (
            f"zoompan=z='min(zoom+0.0008,1.15)':d={total_frames}:"
            f"x='iw/2-(iw/zoom/2)':y='ih/2-(ih/zoom/2)':s=1280x704:fps={fps}"
        )
    elif motion_idx == 1:
        motion_type = "pan_right"
        zoompan_expr = (
            f"zoompan=z='min(zoom+0.0005,1.10)':d={total_frames}:"
            f"x='if(lte(on,1),(iw-iw/zoom)/4,x+0.3)':y='ih/2-(ih/zoom/2)':s=1280x704:fps={fps}"
        )
    elif motion_idx == 2:
        motion_type = "zoom_out_center"
        zoompan_expr = (
            f"zoompan=z='if(lte(on,1),1.15,max(1.0,zoom-0.0008))':d={total_frames}:"
            f"x='iw/2-(iw/zoom/2)':y='ih/2-(ih/zoom/2)':s=1280x704:fps={fps}"
        )
    else:
        motion_type = "pan_left"
        zoompan_expr = (
            f"zoompan=z='min(zoom+0.0005,1.10)':d={total_frames}:"
            f"x='if(lte(on,1),3*(iw-iw/zoom)/4,x-0.3)':y='ih/2-(ih/zoom/2)':s=1280x704:fps={fps}"
        )

    cmd = [
        FFMPEG_BIN,
        "-y",
        "-loop", "1",
        "-i", str(keyframe_path),
        "-vf", zoompan_expr,
        "-t", str(duration),
        "-c:v", "libx264",
        "-pix_fmt", "yuv420p",
        "-r", str(fps),
        "-f", "mp4",
        str(tmp_path),
    ]

    start_time = time.perf_counter()
    try:
        subprocess.run(cmd, capture_output=True, text=True, check=True)
        if tmp_path.exists():
            tmp_path.replace(output_path)
    except Exception as exc:
        if tmp_path.exists():
            tmp_path.unlink()
        raise RuntimeError(f"FFmpeg Ken Burns failed for {keyframe_path}: {exc}") from exc

    latency = round(time.perf_counter() - start_time, 3)
    return motion_type, latency


def run_shots_stage(
    storyboard: dict,
    target_shot_id: str | None = None,
    outputs_dir: Path = OUTPUTS_SHOTS_DIR,
    no_gpu: bool = False,
    force: bool = False,
) -> dict[str, Path]:
    """Execute the shots stage: synthesize/process clips for all storyboard shots."""
    outputs_dir.mkdir(parents=True, exist_ok=True)
    shots = storyboard.get("shots", [])

    # Import any available Kaggle runs telemetry
    import_kaggle_telemetry()

    results: dict[str, Path] = {}
    print(f"\n--- Processing Video Shots ({len(shots)} shots) ---")

    for idx, shot in enumerate(shots):
        shot_id = shot["id"]
        if target_shot_id and shot_id != target_shot_id:
            continue

        out_path = outputs_dir / f"{shot_id}.mp4"
        results[shot_id] = out_path

        duration = float(shot.get("duration_seconds", 8.0))
        use_video = bool(shot.get("use_video", False))
        motion_prompt = shot.get("motion_prompt", "")
        video_seed = shot.get("video_seed", shot.get("seed", 1001))

        # Read keyframe hash for cache dependency
        kf_path = OUTPUTS_KEYFRAMES_DIR / f"{shot_id}.png"
        kf_hash = ""
        if kf_path.is_file():
            kf_hash = hashlib.sha256(kf_path.read_bytes()).hexdigest()

        # Check if downloaded Wan clip is available
        wan_clip = find_wan_clip(shot_id, outputs_dir) if (use_video and not no_gpu) else None

        input_fields = {
            "shot_id": shot_id,
            "duration": duration,
            "motion_prompt": motion_prompt,
            "use_video": use_video and not no_gpu,
            "video_seed": video_seed,
            "keyframe_hash": kf_hash,
            "wan_source": str(wan_clip.name) if wan_clip else None,
        }
        input_hash = sha256_inputs(input_fields)

        # Check incremental cache
        if not force and is_cache_hit(out_path, input_hash):
            print(f"[{shot_id}] Cache Hit -> {out_path.name}")
            append_run_log({
                "run_id": f"shot_{shot_id}_{uuid.uuid4().hex[:8]}",
                "stage": "shots",
                "shot_id": shot_id,
                "provider": "kaggle_wan" if wan_clip else "ffmpeg_kenburns",
                "model": "Wan2.2-TI2V-5B" if wan_clip else "zoompan",
                "seed": video_seed,
                "parameters": {"duration": duration, "fps": 24, "width": 1280, "height": 704},
                "input_hash": input_hash,
                "output": str(out_path).replace("\\", "/"),
                "latency_seconds": 0.0,
                "cost_usd": 0.0,
                "cache_hit": True,
                "status": "success",
                "timestamp": datetime.now(timezone.utc).isoformat(),
            })
            continue

        # Execute generation: either process Wan clip or Ken Burns fallback
        if wan_clip:
            print(f"[{shot_id}] Ingesting Kaggle Wan 2.2 clip -> {wan_clip.name}")
            start_t = time.perf_counter()
            process_wan_clip(wan_clip, out_path, target_duration=duration, fps=24)
            latency = round(time.perf_counter() - start_t, 3)
            provider_name = "kaggle_wan"
            model_name = "Wan2.2-TI2V-5B"
            param_details = {"mode": "wan_processed", "duration": duration, "source": wan_clip.name}
        else:
            if not kf_path.is_file():
                raise FileNotFoundError(f"Keyframe {kf_path} is required to generate shot {shot_id}.")
            motion_name, latency = run_ken_burns(
                keyframe_path=kf_path,
                output_path=out_path,
                duration=duration,
                shot_index=idx,
                fps=24,
            )
            provider_name = "ffmpeg_kenburns"
            model_name = "zoompan"
            param_details = {"motion": motion_name, "duration": duration, "fps": 24}
            print(f"[{shot_id}] Rendered Ken Burns ({motion_name}) -> {out_path.name} in {latency}s")

        write_sidecar_hash(out_path, input_hash)

        append_run_log({
            "run_id": f"shot_{shot_id}_{uuid.uuid4().hex[:8]}",
            "stage": "shots",
            "shot_id": shot_id,
            "provider": provider_name,
            "model": model_name,
            "seed": video_seed,
            "parameters": param_details,
            "input_hash": input_hash,
            "output": str(out_path).replace("\\", "/"),
            "latency_seconds": latency,
            "cost_usd": 0.0,
            "cache_hit": False,
            "status": "success",
            "timestamp": datetime.now(timezone.utc).isoformat(),
        })

    return results
