"""Narration stage: TTS audio synthesis, duration validation, and radio cut assembly."""

from __future__ import annotations

from datetime import datetime, timezone
import os
from pathlib import Path
import shutil
import subprocess
import time
import uuid
import wave

from pipeline.core import (
    append_run_log,
    atomic_write_bytes,
    is_cache_hit,
    sha256_inputs,
    write_sidecar_hash,
)
from pipeline.providers.gemini import generate_tts

OUTPUTS_NARRATION_DIR = Path("outputs/narration")
OUTPUTS_RADIO_CUT_DIR = Path("outputs/radio_cut")


def get_media_duration_ffprobe(path: Path) -> float:
    """Measure media duration in seconds using ffprobe (with wave fallback for WAV)."""
    ffprobe_bin = shutil.which("ffprobe")
    if not ffprobe_bin:
        c = Path(".venv/Scripts/ffprobe.exe")
        if c.exists():
            ffprobe_bin = str(c)

    if ffprobe_bin:
        cmd = [
            ffprobe_bin,
            "-v", "error",
            "-show_entries", "format=duration",
            "-of", "default=noprint_wrappers=1:nokey=1",
            str(path),
        ]
        try:
            res = subprocess.run(cmd, capture_output=True, text=True, check=True)
            return round(float(res.stdout.strip()), 3)
        except Exception:
            pass

    # Fallback to python wave library if audio is a WAV file
    if path.suffix.lower() == ".wav":
        try:
            with wave.open(str(path), "rb") as w:
                frames = w.getnframes()
                rate = w.getframerate()
                return round(frames / float(rate), 3)
        except Exception:
            pass

    return 0.0


def get_ffmpeg_binary() -> str:
    """Locate ffmpeg executable."""
    ffmpeg_bin = shutil.which("ffmpeg")
    if not ffmpeg_bin:
        c = Path(".venv/Scripts/ffmpeg.exe")
        if c.exists():
            ffmpeg_bin = str(c)
    if not ffmpeg_bin:
        raise FileNotFoundError("ffmpeg binary could not be found on PATH or standard locations.")
    return ffmpeg_bin


def generate_shot_narration(
    shot: dict,
    api_key: str,
    narration_override: str | None = None,
    language: str = "en",
    default_voice: str = "Puck",
    default_style: str = "warm, calm, unhurried storyteller",
    model: str = "gemini-3.8-flash-tts",
    outputs_dir: Path | None = None,
    force: bool = False,
) -> tuple[Path, float, bool]:
    """Generate or retrieve cached narration audio for a single shot."""
    if outputs_dir is None:
        outputs_dir = OUTPUTS_NARRATION_DIR if language == "en" else Path(f"outputs/narration_{language}")

    outputs_dir.mkdir(parents=True, exist_ok=True)
    shot_id = shot["id"]
    narration_text = narration_override if narration_override is not None else shot["narration"]
    voice = shot.get("voice", default_voice)
    style = shot.get("tts_style", default_style)
    target_path = outputs_dir / f"{shot_id}.wav"

    if language == "en":
        input_fields = {
            "narration": narration_text,
            "voice": voice,
            "style": style,
            "model": model,
        }
    else:
        input_fields = {
            "language": language,
            "narration": narration_text,
            "voice": voice,
            "style": style,
            "model": model,
        }
    input_hash = sha256_inputs(input_fields)

    # Check incremental cache
    if not force and is_cache_hit(target_path, input_hash):
        duration = get_media_duration_ffprobe(target_path)
        append_run_log({
            "run_id": f"narration_{language}_{shot_id}_{uuid.uuid4().hex[:8]}",
            "stage": "narration",
            "shot_id": shot_id,
            "provider": "gemini",
            "model": model,
            "seed": shot.get("seed"),
            "parameters": {"language": language, "text": narration_text, "style": style, "voice": voice},
            "input_hash": input_hash,
            "output": str(target_path).replace("\\", "/"),
            "latency_seconds": 0.0,
            "cost_usd": 0.0,
            "cache_hit": True,
            "status": "success",
            "timestamp": datetime.now(timezone.utc).isoformat(),
        })
        return target_path, duration, True

    # Cache miss: generate TTS
    start_time = time.perf_counter()
    audio_bytes, actual_model = generate_tts(
        text=narration_text,
        style=style,
        voice=voice,
        api_key=api_key,
        model=model,
    )
    latency_seconds = round(time.perf_counter() - start_time, 3)

    atomic_write_bytes(target_path, audio_bytes)
    write_sidecar_hash(target_path, input_hash)
    duration = get_media_duration_ffprobe(target_path)

    append_run_log({
        "run_id": f"narration_{language}_{shot_id}_{uuid.uuid4().hex[:8]}",
        "stage": "narration",
        "shot_id": shot_id,
        "provider": "gemini",
        "model": actual_model,
        "seed": shot.get("seed"),
        "parameters": {"language": language, "text": narration_text, "style": style, "voice": voice},
        "input_hash": input_hash,
        "output": str(target_path).replace("\\", "/"),
        "latency_seconds": latency_seconds,
        "cost_usd": 0.0,
        "cache_hit": False,
        "status": "success",
        "timestamp": datetime.now(timezone.utc).isoformat(),
    })

    return target_path, duration, False


def assemble_radio_cut(
    wav_paths: list[Path],
    storyboard: dict,
    effective_slots: dict[str, float] | None = None,
    output_path: Path = OUTPUTS_RADIO_CUT_DIR / "radio_cut.mp4",
) -> Path:
    """Assemble radio cut (black screen + padded shot audio + 3s end-card silence)."""
    ffmpeg_bin = get_ffmpeg_binary()
    output_path.parent.mkdir(parents=True, exist_ok=True)
    temp_dir = output_path.parent / f"temp_{output_path.stem}"
    temp_dir.mkdir(parents=True, exist_ok=True)

    try:
        shots = storyboard.get("shots", [])
        end_card = storyboard.get("end_card", {})
        end_card_duration = float(end_card.get("duration_seconds", 3))

        concat_lines = []

        # 1. Pad each shot audio to its effective duration slot
        for idx, (shot, wav_file) in enumerate(zip(shots, wav_paths), start=1):
            shot_id = shot["id"]
            if effective_slots and shot_id in effective_slots:
                slot_duration = float(effective_slots[shot_id])
            else:
                slot_duration = float(shot.get("duration_seconds", 8))

            padded_wav = temp_dir / f"slot_{idx:02d}.wav"
            cmd_pad = [
                ffmpeg_bin, "-y",
                "-i", str(wav_file.resolve()),
                "-af", f"apad,atrim=0:{slot_duration}",
                "-c:a", "pcm_s16le",
                str(padded_wav.resolve()),
            ]
            subprocess.run(cmd_pad, capture_output=True, check=True)
            concat_lines.append(f"file '{padded_wav.resolve().as_posix()}'")

        # 2. Add quiet silence for the end-card
        end_silence_wav = temp_dir / "end_card_silence.wav"
        cmd_silence = [
            ffmpeg_bin, "-y",
            "-f", "lavfi",
            "-i", "anullsrc=r=24000:cl=mono",
            "-t", str(end_card_duration),
            "-c:a", "pcm_s16le",
            str(end_silence_wav.resolve()),
        ]
        subprocess.run(cmd_silence, capture_output=True, check=True)
        concat_lines.append(f"file '{end_silence_wav.resolve().as_posix()}'")

        # Write concat list with forward slashes
        concat_manifest = temp_dir / "concat_list.txt"
        concat_manifest.write_text("\n".join(concat_lines), encoding="utf-8")

        # 3. Assemble black video screen (1080x1920, 9:16 mobile) + full concat audio
        if effective_slots:
            total_duration = sum(effective_slots.get(s["id"], float(s.get("duration_seconds", 8))) for s in shots) + int(end_card_duration)
        else:
            total_duration = sum(s.get("duration_seconds", 8) for s in shots) + int(end_card_duration)

        tmp_output = output_path.with_name(f"{output_path.stem}.tmp.mp4")

        cmd_assemble = [
            ffmpeg_bin, "-y",
            "-f", "lavfi",
            "-i", f"color=c=black:s=1080x1920:r=24:d={total_duration}",
            "-f", "concat",
            "-safe", "0",
            "-i", concat_manifest.resolve().as_posix(),
            "-map", "0:v",
            "-map", "1:a",
            "-c:v", "libx264",
            "-pix_fmt", "yuv420p",
            "-c:a", "aac",
            "-b:a", "192k",
            "-t", str(total_duration),
            "-f", "mp4",
            tmp_output.resolve().as_posix(),
        ]
        try:
            subprocess.run(cmd_assemble, capture_output=True, text=True, check=True)
        except subprocess.CalledProcessError as exc:
            print(f"FFmpeg assembly error:\n{exc.stderr}")
            raise

        if tmp_output.exists():
            tmp_output.replace(output_path)

        return output_path
    finally:
        shutil.rmtree(temp_dir, ignore_errors=True)


def run_narration_stage(
    storyboard: dict,
    language: str = "en",
    force: bool = False,
) -> dict:
    """Run full narration generation and assemble radio cut."""
    api_key = os.getenv("GEMINI_API_KEY", "").strip()
    if not api_key:
        raise ValueError("GEMINI_API_KEY is required for narration generation.")

    from pipeline.stages.script import get_or_create_translations
    translations = get_or_create_translations(storyboard, language=language, force=force, api_key=api_key)

    shots = storyboard.get("shots", [])
    outputs_dir = OUTPUTS_NARRATION_DIR if language == "en" else Path(f"outputs/narration_{language}")

    print(f"\n--- Generating Narration ({language.upper()}) for {len(shots)} Shots ---")

    wav_paths = []
    durations = []
    effective_slots = {}
    cache_hits = 0

    for shot in shots:
        shot_id = shot["id"]
        text_override = translations.get(shot_id)
        wav_path, dur, hit = generate_shot_narration(
            shot,
            api_key=api_key,
            narration_override=text_override,
            language=language,
            outputs_dir=outputs_dir,
            force=force,
        )
        wav_paths.append(wav_path)
        durations.append(dur)

        default_slot = float(shot.get("duration_seconds", 8.0))
        if dur > default_slot:
            effective_slot = round(dur + 0.35, 1)
        else:
            effective_slot = default_slot
        effective_slots[shot_id] = effective_slot

        if hit:
            cache_hits += 1
            print(f"[{shot_id}] Cache Hit -> {wav_path.name} ({dur:.2f}s)")
        else:
            print(f"[{shot_id}] Generated -> {wav_path.name} ({dur:.2f}s)")
            time.sleep(3.0)

    # Print shot_id | tts_duration | default_slot | effective_slot | status table
    print("\n" + "=" * 76)
    print(f"{'Shot ID':<10} | {'TTS Duration':<14} | {'Default Slot':<14} | {'Effective Slot':<14} | {'Status'}")
    print("-" * 76)
    for shot, dur in zip(shots, durations):
        shot_id = shot["id"]
        default_slot = float(shot.get("duration_seconds", 8.0))
        eff_slot = effective_slots[shot_id]
        if dur <= default_slot:
            status_str = "OK (fits)"
        else:
            status_str = f"EXTENDED (+{eff_slot - default_slot:.1f}s)"
        print(f"{shot_id:<10} | {dur:>6.2f} s        | {default_slot:>6.2f} s       | {eff_slot:>6.2f} s       | {status_str}")
    print("=" * 76)

    end_card_dur = float(storyboard.get("end_card", {}).get("duration_seconds", 3.0))
    total_effective = sum(effective_slots.values()) + end_card_dur
    print(f"Total Effective Duration ({language}): {total_effective:.2f}s (Envelope: 60s - 90s)")

    # Assemble radio cut
    radio_cut_filename = "radio_cut.mp4" if language == "en" else f"radio_cut_{language}.mp4"
    radio_cut_path = OUTPUTS_RADIO_CUT_DIR / radio_cut_filename
    print(f"\n--- Assembling Radio Cut ({radio_cut_path}) ---")
    assembled_path = assemble_radio_cut(wav_paths, storyboard, effective_slots=effective_slots, output_path=radio_cut_path)
    radio_cut_duration = get_media_duration_ffprobe(assembled_path)
    print(f"Radio cut successfully assembled: {assembled_path}")
    print(f"Total ffprobe duration: {radio_cut_duration:.2f}s")

    return {
        "wav_paths": wav_paths,
        "durations": durations,
        "effective_slots": effective_slots,
        "total_duration": total_effective,
        "radio_cut_path": assembled_path,
        "radio_cut_duration": radio_cut_duration,
        "cache_hits": cache_hits,
    }
