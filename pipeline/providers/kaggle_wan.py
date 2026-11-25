"""Kaggle Wan 2.2 Video provider helper and telemetry ingestion."""

from __future__ import annotations

import json
from pathlib import Path
import subprocess
import shutil

from pipeline.core import append_run_log

FFMPEG_BIN = "ffmpeg"
FFPROBE_BIN = "ffprobe"

# Locate FFmpeg/FFprobe in virtualenv or PATH
for candidate in (
    Path(".venv/Scripts/ffmpeg.exe"),
    Path(".venv/bin/ffmpeg"),
    Path("ffmpeg"),
):
    if candidate.is_file():
        FFMPEG_BIN = str(candidate.resolve())
        break

for candidate in (
    Path(".venv/Scripts/ffprobe.exe"),
    Path(".venv/bin/ffprobe"),
    Path("ffprobe"),
):
    if candidate.is_file():
        FFPROBE_BIN = str(candidate.resolve())
        break


def find_wan_clip(shot_id: str, shots_dir: Path = Path("outputs/shots")) -> Path | None:
    """Check if a downloaded Wan 2.2 video clip exists for the given shot."""
    candidates = [
        shots_dir / f"wan_{shot_id}.mp4",
        shots_dir / f"{shot_id}_wan.mp4",
    ]
    for c in candidates:
        if c.is_file() and c.stat().st_size > 0:
            return c
    return None


def get_video_duration(video_path: Path) -> float:
    """Measure video duration in seconds via ffprobe."""
    cmd = [
        FFPROBE_BIN,
        "-v", "error",
        "-show_entries", "format=duration",
        "-of", "default=noprint_wrappers=1:nokey=1",
        str(video_path),
    ]
    res = subprocess.run(cmd, capture_output=True, text=True, check=True)
    return float(res.stdout.strip())


def process_wan_clip(
    wan_path: Path,
    output_path: Path,
    target_duration: float,
    fps: int = 24,
) -> None:
    """Trim weak boundary frames and adjust speed/hold cleanly to match target duration at constant 24fps."""
    output_path.parent.mkdir(parents=True, exist_ok=True)
    tmp_path = output_path.with_name(f"{output_path.name}.tmp.mp4")

    raw_duration = get_video_duration(wan_path)

    # Trim first/last 0.25s if duration > 4.0s
    trim_start = 0.25 if raw_duration > 4.0 else 0.0
    effective_duration = raw_duration - (0.50 if raw_duration > 4.0 else 0.0)

    # Speed ratio or tpad hold
    # Filter graph: trim, scale to 1280x704, set constant fps, pad end if needed
    vf_chain = [
        f"trim=start={trim_start}:duration={effective_duration}",
        "setpts=PTS-STARTPTS",
        "scale=1280:704:force_original_aspect_ratio=decrease,pad=1280:704:(ow-iw)/2:(oh-ih)/2",
        f"fps={fps}",
        f"tpad=stop_mode=clone:stop_duration={max(0.0, target_duration - effective_duration + 0.1)}",
        f"trim=duration={target_duration}",
        "setpts=PTS-STARTPTS",
    ]

    cmd = [
        FFMPEG_BIN,
        "-y",
        "-i", str(wan_path),
        "-vf", ",".join(vf_chain),
        "-t", str(target_duration),
        "-c:v", "libx264",
        "-pix_fmt", "yuv420p",
        "-r", str(fps),
        "-f", "mp4",
        str(tmp_path),
    ]

    try:
        subprocess.run(cmd, capture_output=True, text=True, check=True)
        if tmp_path.exists():
            tmp_path.replace(output_path)
    except Exception as exc:
        if tmp_path.exists():
            tmp_path.unlink()
        raise RuntimeError(f"FFmpeg processing failed for {wan_path}: {exc}") from exc


def import_kaggle_telemetry(
    kaggle_log_path: Path = Path("outputs/shots/kaggle_runs.jsonl"),
    runs_log_path: Path = Path("runs.jsonl"),
) -> int:
    """Import runs from kaggle_runs.jsonl into runs.jsonl if not already present."""
    if not kaggle_log_path.is_file():
        return 0

    existing_run_ids = set()
    if runs_log_path.is_file():
        with open(runs_log_path, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if line:
                    try:
                        existing_run_ids.add(json.loads(line).get("run_id"))
                    except Exception:
                        pass

    imported_count = 0
    with open(kaggle_log_path, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                entry = json.loads(line)
                run_id = entry.get("run_id")
                if run_id and run_id not in existing_run_ids:
                    append_run_log(entry, log_path=runs_log_path)
                    existing_run_ids.add(run_id)
                    imported_count += 1
            except Exception:
                pass

    if imported_count > 0:
        print(f"[telemetry] Imported {imported_count} runs from {kaggle_log_path.name}")
    return imported_count
