"""Assemble stage: Combines video shots, narration, music ducking, subtitles, and end card into master MP4s."""

from __future__ import annotations

from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import time
import uuid

from PIL import Image, ImageDraw, ImageFont

from pipeline.core import (
    append_run_log,
    is_cache_hit,
    sha256_inputs,
    write_sidecar_hash,
)
from pipeline.providers.kaggle_wan import FFMPEG_BIN, FFPROBE_BIN

OUTPUTS_FINAL_DIR = Path("outputs/final")
OUTPUTS_AUDIO_DIR = Path("outputs/audio")
OUTPUTS_SHOTS_DIR = Path("outputs/shots")
OUTPUTS_NARRATION_DIR = Path("outputs/narration")
OUTPUTS_MUSIC_DIR = Path("outputs/music")
SUBTITLES_SRT_PATH = Path("content/en/subtitles.srt")


def get_media_duration(file_path: Path) -> float:
    """Read duration in seconds using ffprobe."""
    cmd = [
        FFPROBE_BIN,
        "-v", "error",
        "-show_entries", "format=duration",
        "-of", "default=noprint_wrappers=1:nokey=1",
        str(file_path),
    ]
    res = subprocess.run(cmd, capture_output=True, text=True, check=True)
    return float(res.stdout.strip())


def build_full_narration_track(
    storyboard: dict,
    output_wav: Path,
    language: str = "en",
    effective_slots: dict[str, float] | None = None,
) -> Path:
    """Pad each shot's narration to exact slot duration and append 3s end-card silence."""
    output_wav.parent.mkdir(parents=True, exist_ok=True)
    tmp_wav = output_wav.with_name(f"{output_wav.name}.tmp.wav")

    shots = storyboard.get("shots", [])
    padded_parts: list[Path] = []
    narration_dir = OUTPUTS_NARRATION_DIR if language == "en" else Path(f"outputs/narration_{language}")

    for idx, shot in enumerate(shots):
        shot_id = shot["id"]
        if effective_slots and shot_id in effective_slots:
            slot_duration = float(effective_slots[shot_id])
        else:
            slot_duration = float(shot.get("duration_seconds", 8.0))

        raw_wav = narration_dir / f"{shot_id}.wav"
        if not raw_wav.is_file():
            raise FileNotFoundError(f"Narration file {raw_wav} is missing.")

        part_padded = output_wav.parent / f"part_narr_{language}_{idx:02d}.wav"
        # Pad with silence to exact slot duration
        cmd = [
            FFMPEG_BIN,
            "-y",
            "-i", str(raw_wav),
            "-af", f"apad=whole_dur={slot_duration},atrim=0:{slot_duration}",
            "-ar", "44100",
            "-ac", "2",
            "-c:a", "pcm_s16le",
            str(part_padded),
        ]
        subprocess.run(cmd, capture_output=True, text=True, check=True)
        padded_parts.append(part_padded)

    # 3-second silence for end card
    end_silence = output_wav.parent / f"end_silence_{language}.wav"
    cmd_silence = [
        FFMPEG_BIN,
        "-y",
        "-f", "lavfi",
        "-i", "anullsrc=r=44100:cl=stereo",
        "-t", "3.0",
        "-c:a", "pcm_s16le",
        str(end_silence),
    ]
    subprocess.run(cmd_silence, capture_output=True, text=True, check=True)
    padded_parts.append(end_silence)

    # Concat all audio parts
    concat_txt = output_wav.parent / f"narration_concat_{language}.txt"
    lines = [f"file '{p.resolve().as_posix()}'" for p in padded_parts]
    concat_txt.write_text("\n".join(lines), encoding="utf-8")

    cmd_concat = [
        FFMPEG_BIN,
        "-y",
        "-f", "concat",
        "-safe", "0",
        "-i", str(concat_txt),
        "-c:a", "pcm_s16le",
        str(tmp_wav),
    ]
    subprocess.run(cmd_concat, capture_output=True, text=True, check=True)

    if tmp_wav.exists():
        tmp_wav.replace(output_wav)

    # Clean temporary slices
    for p in padded_parts:
        try:
            p.unlink()
        except Exception:
            pass
    try:
        concat_txt.unlink()
    except Exception:
        pass

    return output_wav


def mix_and_loudnorm_audio(
    narration_wav: Path,
    music_wav: Path,
    output_wav: Path,
    target_duration: float = 78.0,
) -> Path:
    """Duck music beneath narration via sidechaincompress and apply 2-pass EBU R128 loudnorm."""
    output_wav.parent.mkdir(parents=True, exist_ok=True)
    ducked_raw = output_wav.parent / f"audio_ducked_raw_{output_wav.stem}.wav"

    fade_out_start = max(0.0, target_duration - 3.0)
    # Step A: Duck music under narration and mix
    filter_duck = (
        f"[1:a]afade=t=out:st={fade_out_start}:d=3[faded_music];"
        f"[faded_music][0:a]sidechaincompress=threshold=0.02:ratio=6:attack=300:release=1500[ducked_music];"
        f"[0:a][ducked_music]amix=inputs=2:duration=first:dropout_transition=2,volume=1.0[mixed]"
    )
    cmd_duck = [
        FFMPEG_BIN,
        "-y",
        "-i", str(narration_wav),
        "-i", str(music_wav),
        "-filter_complex", filter_duck,
        "-map", "[mixed]",
        "-t", str(target_duration),
        "-ar", "44100",
        "-ac", "2",
        "-c:a", "pcm_s16le",
        str(ducked_raw),
    ]
    subprocess.run(cmd_duck, capture_output=True, text=True, check=True)

    # Step B: Loudnorm Pass 1 (measure JSON stats)
    cmd_pass1 = [
        FFMPEG_BIN,
        "-y",
        "-i", str(ducked_raw),
        "-af", "loudnorm=I=-14:TP=-1.0:LRA=11:print_format=json",
        "-f", "null",
        "-",
    ]
    res_pass1 = subprocess.run(cmd_pass1, capture_output=True, text=True, check=True)
    stderr_output = res_pass1.stderr

    json_match = re.search(r"\{[\s\S]*\"input_i\"[\s\S]*\}", stderr_output)
    if not json_match:
        loudnorm_filter = "loudnorm=I=-14:TP=-1.0:LRA=11"
    else:
        stats = json.loads(json_match.group(0))
        loudnorm_filter = (
            f"loudnorm=I=-14:TP=-1.0:LRA=11:"
            f"measured_I={stats['input_i']}:"
            f"measured_TP={stats['input_tp']}:"
            f"measured_LRA={stats['input_lra']}:"
            f"measured_thresh={stats['input_thresh']}:"
            f"offset={stats['target_offset']}:"
            f"linear=true"
        )

    # Step C: Loudnorm Pass 2 (apply linear normalization)
    tmp_out = output_wav.with_name(f"{output_wav.name}.tmp.wav")
    cmd_pass2 = [
        FFMPEG_BIN,
        "-y",
        "-i", str(ducked_raw),
        "-af", loudnorm_filter,
        "-ar", "44100",
        "-ac", "2",
        "-c:a", "pcm_s16le",
        str(tmp_out),
    ]
    subprocess.run(cmd_pass2, capture_output=True, text=True, check=True)

    if tmp_out.exists():
        tmp_out.replace(output_wav)

    try:
        ducked_raw.unlink()
    except Exception:
        pass

    return output_wav


def build_concatenated_video_16x9(
    storyboard: dict,
    output_mp4: Path,
    effective_slots: dict[str, float] | None = None,
    prefix: str = "master",
) -> Path:
    """Concatenate 10 shot clips (1280x704) + 16:9 end card (3s) for horizontal master."""
    output_mp4.parent.mkdir(parents=True, exist_ok=True)
    tmp_mp4 = output_mp4.with_name(f"{output_mp4.name}.tmp.mp4")

    shots = storyboard.get("shots", [])
    temp_extended_clips: list[Path] = []

    # 1. 16:9 End card frame and clip
    end_card_clip = output_mp4.parent / f"end_card_16x9_3s_{prefix}.mp4"
    end_card_img_path = output_mp4.parent / f"end_card_16x9_frame_{prefix}.png"

    img = Image.new("RGB", (1280, 704), color=(0, 0, 0))
    draw = ImageDraw.Draw(img)
    display_text = "Created with AI-assisted tools.\nStory and production by the creator."
    try:
        font = ImageFont.truetype("arial.ttf", 36)
    except Exception:
        font = ImageFont.load_default()

    bbox = draw.multiline_textbbox((0, 0), display_text, font=font, align="center", spacing=14)
    tw = bbox[2] - bbox[0]
    th = bbox[3] - bbox[1]
    tx = (1280 - tw) // 2
    ty = (704 - th) // 2
    draw.multiline_text((tx, ty), display_text, fill=(255, 255, 255), font=font, align="center", spacing=14)
    img.save(end_card_img_path)

    cmd_end_card = [
        FFMPEG_BIN,
        "-y",
        "-loop", "1",
        "-i", str(end_card_img_path),
        "-vf", "fade=t=in:st=0:d=0.5,fade=t=out:st=2.5:d=0.5",
        "-t", "3.0",
        "-c:v", "libx264",
        "-pix_fmt", "yuv420p",
        "-r", "24",
        "-f", "mp4",
        str(end_card_clip),
    ]
    subprocess.run(cmd_end_card, capture_output=True, text=True, check=True)

    # 2. Concat 10 shots (extending with tpad if effective_slot > default_dur) + 16:9 end card
    concat_list = output_mp4.parent / f"video_concat_16x9_{prefix}.txt"
    lines = []
    for s in shots:
        shot_id = s["id"]
        shot_file = OUTPUTS_SHOTS_DIR / f"{shot_id}.mp4"
        if not shot_file.is_file():
            raise FileNotFoundError(f"Video shot {shot_file} is missing.")

        default_dur = float(s.get("duration_seconds", 8.0))
        eff_dur = float(effective_slots[shot_id]) if (effective_slots and shot_id in effective_slots) else default_dur

        current_input = shot_file
        if eff_dur > default_dur:
            extended_file = output_mp4.parent / f"extended_16x9_{prefix}_{shot_id}.mp4"
            cmd_extend = [
                FFMPEG_BIN,
                "-y",
                "-i", str(shot_file),
                "-vf", "tpad=stop_mode=clone:stop=-1",
                "-t", str(eff_dur),
                "-c:v", "libx264",
                "-pix_fmt", "yuv420p",
                "-r", "24",
                "-f", "mp4",
                str(extended_file),
            ]
            subprocess.run(cmd_extend, capture_output=True, text=True, check=True)
            current_input = extended_file
            temp_extended_clips.append(extended_file)

        lines.append(f"file '{current_input.resolve().as_posix()}'")

    lines.append(f"file '{end_card_clip.resolve().as_posix()}'")
    concat_list.write_text("\n".join(lines), encoding="utf-8")

    cmd_concat = [
        FFMPEG_BIN,
        "-y",
        "-f", "concat",
        "-safe", "0",
        "-i", str(concat_list),
        "-c:v", "libx264",
        "-pix_fmt", "yuv420p",
        "-r", "24",
        "-f", "mp4",
        str(tmp_mp4),
    ]
    subprocess.run(cmd_concat, capture_output=True, text=True, check=True)

    if tmp_mp4.exists():
        tmp_mp4.replace(output_mp4)

    try:
        concat_list.unlink()
        end_card_clip.unlink()
        end_card_img_path.unlink()
    except Exception:
        pass
    for p in temp_extended_clips:
        try:
            p.unlink()
        except Exception:
            pass

    return output_mp4


def build_concatenated_video_9x16(
    storyboard: dict,
    output_mp4: Path,
    effective_slots: dict[str, float] | None = None,
    prefix: str = "master",
) -> Path:
    """Build 1080x1920 video track with blurred pillarboxes for two-person shots and native 3-line end card."""
    output_mp4.parent.mkdir(parents=True, exist_ok=True)
    tmp_mp4 = output_mp4.with_name(f"{output_mp4.name}.tmp.mp4")

    shots = storyboard.get("shots", [])
    formatted_slices: list[Path] = []
    temp_extended_clips: list[Path] = []

    # 1. Format each shot into 9:16 (extending video if effective_slot > default_slot)
    for idx, s in enumerate(shots):
        shot_id = s["id"]
        shot_file = OUTPUTS_SHOTS_DIR / f"{shot_id}.mp4"
        if not shot_file.is_file():
            raise FileNotFoundError(f"Video shot {shot_file} is missing.")

        default_dur = float(s.get("duration_seconds", 8.0))
        eff_dur = float(effective_slots[shot_id]) if (effective_slots and shot_id in effective_slots) else default_dur

        current_input = shot_file
        if eff_dur > default_dur:
            extended_file = output_mp4.parent / f"extended_9x16_{prefix}_{shot_id}.mp4"
            cmd_extend = [
                FFMPEG_BIN,
                "-y",
                "-i", str(shot_file),
                "-vf", "tpad=stop_mode=clone:stop=-1",
                "-t", str(eff_dur),
                "-c:v", "libx264",
                "-pix_fmt", "yuv420p",
                "-r", "24",
                "-f", "mp4",
                str(extended_file),
            ]
            subprocess.run(cmd_extend, capture_output=True, text=True, check=True)
            current_input = extended_file
            temp_extended_clips.append(extended_file)

        shot_9x16_file = output_mp4.parent / f"shot_9x16_{prefix}_{idx:02d}.mp4"
        chars_in_shot = s.get("characters_in_shot", [])

        # Two-person or group shots: blurred background + centered 16:9 foreground
        if len(chars_in_shot) >= 2 or shot_id == "shot_08":
            filter_str = (
                "[0:v]split[bg_in][fg_in];"
                "[bg_in]scale=1080:1920:force_original_aspect_ratio=increase,crop=1080:1920,boxblur=25:5,eq=brightness=-0.08[bg];"
                "[fg_in]scale=1080:-2[fg];"
                "[bg][fg]overlay=(W-w)/2:(H-h)/2"
            )
            cmd_shot = [
                FFMPEG_BIN,
                "-y",
                "-i", str(current_input),
                "-filter_complex", filter_str,
                "-c:v", "libx264",
                "-pix_fmt", "yuv420p",
                "-r", "24",
                "-f", "mp4",
                str(shot_9x16_file),
            ]
        else:
            # Single-person and landscapes: full-bleed 9:16 center crop
            filter_str = "crop=ih*9/16:ih:(iw-ow)/2:0,scale=1080:1920:flags=lanczos"
            cmd_shot = [
                FFMPEG_BIN,
                "-y",
                "-i", str(current_input),
                "-vf", filter_str,
                "-c:v", "libx264",
                "-pix_fmt", "yuv420p",
                "-r", "24",
                "-f", "mp4",
                str(shot_9x16_file),
            ]
        subprocess.run(cmd_shot, capture_output=True, text=True, check=True)
        formatted_slices.append(shot_9x16_file)

    # 2. Native 9:16 End card frame and clip (1080x1920, 3 lines, fontsize=42)
    end_card_9x16_clip = output_mp4.parent / f"end_card_9x16_3s_{prefix}.mp4"
    end_card_9x16_img = output_mp4.parent / f"end_card_9x16_frame_{prefix}.png"

    img_9x16 = Image.new("RGB", (1080, 1920), color=(0, 0, 0))
    draw_9x16 = ImageDraw.Draw(img_9x16)
    display_text_9x16 = "Created with AI-assisted tools.\nStory and production\nby the creator."
    try:
        font_9x16 = ImageFont.truetype("arial.ttf", 42)
    except Exception:
        font_9x16 = ImageFont.load_default()

    bbox_9x16 = draw_9x16.multiline_textbbox((0, 0), display_text_9x16, font=font_9x16, align="center", spacing=20)
    tw_9x16 = bbox_9x16[2] - bbox_9x16[0]
    th_9x16 = bbox_9x16[3] - bbox_9x16[1]
    tx_9x16 = (1080 - tw_9x16) // 2
    ty_9x16 = (1920 - th_9x16) // 2
    draw_9x16.multiline_text((tx_9x16, ty_9x16), display_text_9x16, fill=(255, 255, 255), font=font_9x16, align="center", spacing=20)
    img_9x16.save(end_card_9x16_img)

    cmd_end_9x16 = [
        FFMPEG_BIN,
        "-y",
        "-loop", "1",
        "-i", str(end_card_9x16_img),
        "-vf", "fade=t=in:st=0:d=0.5,fade=t=out:st=2.5:d=0.5",
        "-t", "3.0",
        "-c:v", "libx264",
        "-pix_fmt", "yuv420p",
        "-r", "24",
        "-f", "mp4",
        str(end_card_9x16_clip),
    ]
    subprocess.run(cmd_end_9x16, capture_output=True, text=True, check=True)
    formatted_slices.append(end_card_9x16_clip)

    # 3. Concat all 9:16 slices
    concat_list = output_mp4.parent / f"video_concat_9x16_{prefix}.txt"
    lines = [f"file '{p.resolve().as_posix()}'" for p in formatted_slices]
    concat_list.write_text("\n".join(lines), encoding="utf-8")

    cmd_concat = [
        FFMPEG_BIN,
        "-y",
        "-f", "concat",
        "-safe", "0",
        "-i", str(concat_list),
        "-c:v", "libx264",
        "-pix_fmt", "yuv420p",
        "-r", "24",
        "-f", "mp4",
        str(tmp_mp4),
    ]
    subprocess.run(cmd_concat, capture_output=True, text=True, check=True)

    if tmp_mp4.exists():
        tmp_mp4.replace(output_mp4)

    # Cleanup intermediate 9:16 slices
    for p in formatted_slices:
        try:
            p.unlink()
        except Exception:
            pass
    for p in temp_extended_clips:
        try:
            p.unlink()
        except Exception:
            pass
    try:
        concat_list.unlink()
        end_card_9x16_img.unlink()
    except Exception:
        pass

    return output_mp4


def render_final_horizontal_16x9(
    video_track: Path,
    audio_track: Path,
    subtitles_srt: Path,
    output_mp4: Path,
    language: str = "en",
) -> Path:
    """Render horizontal 16:9 master MP4 (1920x1080, 24fps, burned subtitles, metadata preserved)."""
    output_mp4.parent.mkdir(parents=True, exist_ok=True)
    tmp_mp4 = output_mp4.with_name(f"{output_mp4.name}.tmp.mp4")

    srt_posix = subtitles_srt.as_posix()
    font_name = "Ebrima" if language == "am" else "Arial"
    sub_style = (
        "subtitles=" + srt_posix + ":"
        f"force_style='FontName={font_name},FontSize=20,PrimaryColour=&H00FFFFFF,OutlineColour=&H00000000,BorderStyle=1,Outline=2,Shadow=1,MarginV=35'"
    )

    vf_chain = f"scale=1920:1080:flags=lanczos,{sub_style}"

    cmd = [
        FFMPEG_BIN,
        "-y",
        "-i", str(video_track),
        "-i", str(audio_track),
        "-vf", vf_chain,
        "-c:v", "libx264",
        "-preset", "medium",
        "-crf", "19",
        "-pix_fmt", "yuv420p",
        "-r", "24",
        "-c:a", "aac",
        "-b:a", "256k",
        "-shortest",
        "-movflags", "+faststart",
        "-f", "mp4",
        str(tmp_mp4),
    ]
    subprocess.run(cmd, capture_output=True, text=True, check=True)

    if tmp_mp4.exists():
        tmp_mp4.replace(output_mp4)

    return output_mp4


def render_final_vertical_9x16(
    video_track: Path,
    audio_track: Path,
    subtitles_srt: Path,
    output_mp4: Path,
    language: str = "en",
) -> Path:
    """Render vertical 9:16 master MP4 (1080x1920, mobile safe-area subtitles MarginV=35, FontSize=12)."""
    output_mp4.parent.mkdir(parents=True, exist_ok=True)
    tmp_mp4 = output_mp4.with_name(f"{output_mp4.name}.tmp.mp4")

    srt_posix = subtitles_srt.as_posix()
    font_name = "Ebrima" if language == "am" else "Arial"
    sub_style = (
        "subtitles=" + srt_posix + ":"
        f"force_style='FontName={font_name},FontSize=12,PrimaryColour=&H00FFFFFF,OutlineColour=&H00000000,BorderStyle=1,Outline=2,Shadow=1,MarginV=35'"
    )

    cmd = [
        FFMPEG_BIN,
        "-y",
        "-i", str(video_track),
        "-i", str(audio_track),
        "-vf", sub_style,
        "-c:v", "libx264",
        "-preset", "medium",
        "-crf", "19",
        "-pix_fmt", "yuv420p",
        "-r", "24",
        "-c:a", "aac",
        "-b:a", "256k",
        "-shortest",
        "-movflags", "+faststart",
        "-f", "mp4",
        str(tmp_mp4),
    ]
    subprocess.run(cmd, capture_output=True, text=True, check=True)

    if tmp_mp4.exists():
        tmp_mp4.replace(output_mp4)

    return output_mp4


def run_assemble_stage(
    storyboard: dict,
    language: str = "en",
    outputs_dir: Path = OUTPUTS_FINAL_DIR,
    force: bool = False,
) -> dict[str, Path]:
    """Execute the assembly stage: produce English master MP4s or localized 16:9 and 9:16 MP4s."""
    outputs_dir.mkdir(parents=True, exist_ok=True)
    OUTPUTS_AUDIO_DIR.mkdir(parents=True, exist_ok=True)

    music_path = OUTPUTS_MUSIC_DIR / "music_master_83s.wav"
    if not music_path.is_file():
        raise FileNotFoundError(f"Music master file {music_path} is required.")

    shots = storyboard.get("shots", [])

    # =========================================================================
    # A. ENGLISH MASTER WORKFLOW (16:9 and 9:16)
    # =========================================================================
    if language == "en":
        target_16x9 = outputs_dir / "heritage_short_horizontal_16x9.mp4"
        target_9x16 = outputs_dir / "heritage_short_vertical_9x16.mp4"

        subtitles_path = SUBTITLES_SRT_PATH
        if not subtitles_path.is_file():
            subtitles_path = Path("outputs/subtitles.srt")

        shot_hashes = {}
        for s in shots:
            shot_file = OUTPUTS_SHOTS_DIR / f"{s['id']}.mp4"
            if shot_file.is_file():
                shot_hashes[s["id"]] = hashlib.sha256(shot_file.read_bytes()).hexdigest()

        music_hash = hashlib.sha256(music_path.read_bytes()).hexdigest() if music_path.is_file() else ""
        total_duration = sum(s.get("duration_seconds", 8.0) for s in shots) + float(storyboard.get("end_card", {}).get("duration_seconds", 3.0))

        assemble_input = {
            "shots_count": len(shots),
            "total_duration": total_duration,
            "end_card": storyboard.get("end_card", {}),
            "subtitles_hash": sha256_inputs({"srt": subtitles_path.read_text(encoding="utf-8") if subtitles_path.is_file() else ""}),
            "shot_hashes": shot_hashes,
            "music_hash": music_hash,
            "layout_version": "v4_78s_narr_pacing_afade75",
        }
        input_hash = sha256_inputs(assemble_input)

        # Check cache hit
        if not force and is_cache_hit(target_16x9, input_hash) and is_cache_hit(target_9x16, input_hash):
            print(f"[assemble] Cache Hit -> {target_16x9.name} & {target_9x16.name}")
            append_run_log({
                "run_id": f"assemble_cache_{uuid.uuid4().hex[:8]}",
                "stage": "assemble",
                "shot_id": None,
                "provider": "ffmpeg",
                "model": "master_mux",
                "seed": None,
                "parameters": {"aspect_ratios": ["16:9", "9:16"], "fps": 24},
                "input_hash": input_hash,
                "output": f"{target_16x9.as_posix()};{target_9x16.as_posix()}",
                "latency_seconds": 0.0,
                "cost_usd": 0.0,
                "cache_hit": True,
                "status": "success",
                "timestamp": datetime.now(timezone.utc).isoformat(),
            })
            return {"horizontal_16x9": target_16x9, "vertical_9x16": target_9x16}

        print("\n--- Assembling Final English Master Media ---")
        start_time = time.perf_counter()

        narration_padded = OUTPUTS_AUDIO_DIR / f"narration_padded_{int(total_duration)}s.wav"
        print(f"[assemble 1/5] Building {int(total_duration)}s padded narration track...")
        build_full_narration_track(storyboard, narration_padded, language="en")

        master_audio = OUTPUTS_AUDIO_DIR / f"master_audio_{int(total_duration)}s.wav"
        print(f"[assemble 2/5] Ducking music beneath narration and applying two-pass loudnorm (I=-14, TP=-1.0, LRA=11)...")
        mix_and_loudnorm_audio(narration_padded, music_path, master_audio, target_duration=total_duration)

        raw_video_16x9 = OUTPUTS_AUDIO_DIR / f"raw_video_16x9_{int(total_duration)}s.mp4"
        print(f"[assemble 3a/5] Concatenating 10 shots + 3s AI disclosure end card (16:9)...")
        build_concatenated_video_16x9(storyboard, raw_video_16x9, prefix="en")

        raw_video_9x16 = OUTPUTS_AUDIO_DIR / f"raw_video_9x16_{int(total_duration)}s.mp4"
        print(f"[assemble 3b/5] Building 9:16 track with blurred pillarbox for multi-person shots & native end card...")
        build_concatenated_video_9x16(storyboard, raw_video_9x16, prefix="en")

        print(f"[assemble 4/5] Rendering horizontal 16:9 -> {target_16x9.name}...")
        render_final_horizontal_16x9(raw_video_16x9, master_audio, subtitles_path, target_16x9, language="en")
        write_sidecar_hash(target_16x9, input_hash)

        print(f"[assemble 5/5] Rendering vertical 9:16 -> {target_9x16.name} (safe-area subtitles)...")
        render_final_vertical_9x16(raw_video_9x16, master_audio, subtitles_path, target_9x16, language="en")
        write_sidecar_hash(target_9x16, input_hash)

        total_latency = round(time.perf_counter() - start_time, 2)
        dur_16x9 = get_media_duration(target_16x9)
        dur_9x16 = get_media_duration(target_9x16)

        print(f"\nAssembly Complete ({total_latency}s):")
        print(f"  - Horizontal 16:9: {target_16x9} ({dur_16x9:.2f}s, {target_16x9.stat().st_size / 1e6:.2f} MB)")
        print(f"  - Vertical 9:16:   {target_9x16} ({dur_9x16:.2f}s, {target_9x16.stat().st_size / 1e6:.2f} MB)")

        append_run_log({
            "run_id": f"assemble_master_{uuid.uuid4().hex[:8]}",
            "stage": "assemble",
            "shot_id": None,
            "provider": "ffmpeg",
            "model": "h264_aac_loudnorm",
            "seed": None,
            "parameters": {
                "aspect_ratios": ["16:9", "9:16"],
                "horizontal_res": "1920x1080",
                "vertical_res": "1080x1920",
                "fps": 24,
                "loudnorm": "I=-14:TP=-1.0:LRA=11",
            },
            "input_hash": input_hash,
            "output": f"{target_16x9.as_posix()};{target_9x16.as_posix()}",
            "latency_seconds": total_latency,
            "cost_usd": 0.0,
            "cache_hit": False,
            "status": "success",
            "timestamp": datetime.now(timezone.utc).isoformat(),
        })

        return {"horizontal_16x9": target_16x9, "vertical_9x16": target_9x16}

    # =========================================================================
    # B. LOCALIZED 16:9 & 9:16 WORKFLOW (Amharic 'am' or Afaan Oromo 'om')
    # =========================================================================
    target_16x9 = outputs_dir / f"heritage_short_{language}_16x9.mp4"
    target_9x16 = outputs_dir / f"heritage_short_{language}_9x16.mp4"
    narration_dir = Path(f"outputs/narration_{language}")

    # 1. Measure localized WAV durations & calculate effective slots
    effective_slots = {}
    for s in shots:
        shot_id = s["id"]
        shot_wav = narration_dir / f"{shot_id}.wav"
        if not shot_wav.is_file():
            raise FileNotFoundError(f"Localized narration {shot_wav} is missing. Run narration stage first.")
        dur = get_media_duration(shot_wav)
        default_slot = float(s.get("duration_seconds", 8.0))
        if dur > default_slot:
            eff_slot = round(dur + 0.35, 1)
        else:
            eff_slot = default_slot
        effective_slots[shot_id] = eff_slot

    end_card_duration = float(storyboard.get("end_card", {}).get("duration_seconds", 3.0))
    total_duration = sum(effective_slots.values()) + end_card_duration
    print(f"\n--- Assembling Localized Short Films ({language.upper()}) ---")
    print(f"Total Localized Duration: {total_duration:.2f}s (Envelope: 60s - 90s)")

    # 2. Generate localized subtitles with multi-cue splitting timed to effective_slots
    from pipeline.stages.script import run_script_stage
    subtitles_path = run_script_stage(storyboard, language=language, effective_slots=effective_slots, force=force)

    # 3. Compute input hash for localization
    shot_hashes = {}
    for s in shots:
        shot_file = OUTPUTS_SHOTS_DIR / f"{s['id']}.mp4"
        if shot_file.is_file():
            shot_hashes[s["id"]] = hashlib.sha256(shot_file.read_bytes()).hexdigest()

    narr_hashes = {}
    for s in shots:
        shot_wav = narration_dir / f"{s['id']}.wav"
        if shot_wav.is_file():
            narr_hashes[s["id"]] = hashlib.sha256(shot_wav.read_bytes()).hexdigest()

    music_hash = hashlib.sha256(music_path.read_bytes()).hexdigest() if music_path.is_file() else ""

    loc_input = {
        "language": language,
        "effective_slots": effective_slots,
        "total_duration": total_duration,
        "subtitles_hash": sha256_inputs({"srt": subtitles_path.read_text(encoding="utf-8") if subtitles_path.is_file() else ""}),
        "shot_hashes": shot_hashes,
        "narr_hashes": narr_hashes,
        "music_hash": music_hash,
        "layout_version": "v2_dual_aspect_ethiopia_ebrima",
    }
    input_hash = sha256_inputs(loc_input)

    # Check cache hit on both 16:9 and 9:16
    if not force and is_cache_hit(target_16x9, input_hash) and is_cache_hit(target_9x16, input_hash):
        print(f"[assemble] Cache Hit -> {target_16x9.name} & {target_9x16.name}")
        append_run_log({
            "run_id": f"assemble_loc_cache_{language}_{uuid.uuid4().hex[:8]}",
            "stage": "assemble",
            "shot_id": None,
            "provider": "ffmpeg",
            "model": "localized_dual_mux",
            "seed": None,
            "parameters": {"language": language, "aspect_ratios": ["16:9", "9:16"], "fps": 24},
            "input_hash": input_hash,
            "output": f"{target_16x9.as_posix()};{target_9x16.as_posix()}",
            "latency_seconds": 0.0,
            "cost_usd": 0.0,
            "cache_hit": True,
            "status": "success",
            "timestamp": datetime.now(timezone.utc).isoformat(),
        })
        return {"horizontal_16x9": target_16x9, "vertical_9x16": target_9x16}

    start_time = time.perf_counter()

    # 4. Build padded narration track
    narration_padded = OUTPUTS_AUDIO_DIR / f"narration_padded_{language}_{int(total_duration)}s.wav"
    print(f"[assemble 1/5] Building {int(total_duration)}s padded narration track ({language})...")
    build_full_narration_track(storyboard, narration_padded, language=language, effective_slots=effective_slots)

    # 5. Mix and loudnorm master audio
    master_audio = OUTPUTS_AUDIO_DIR / f"master_audio_{language}_{int(total_duration)}s.wav"
    print(f"[assemble 2/5] Ducking music beneath {language} narration and applying two-pass loudnorm (I=-14, TP=-1.0)...")
    mix_and_loudnorm_audio(narration_padded, music_path, master_audio, target_duration=total_duration)

    # 6a. Build localized 16:9 video track (with dynamic tpad extensions)
    raw_video_16x9 = OUTPUTS_AUDIO_DIR / f"raw_video_16x9_{language}_{int(total_duration)}s.mp4"
    print(f"[assemble 3a/5] Building 16:9 video track with dynamic tpad extensions ({language})...")
    build_concatenated_video_16x9(storyboard, raw_video_16x9, effective_slots=effective_slots, prefix=language)

    # 6b. Build localized 9:16 video track (with dynamic tpad extensions and blurred pillarboxes)
    raw_video_9x16 = OUTPUTS_AUDIO_DIR / f"raw_video_9x16_{language}_{int(total_duration)}s.mp4"
    print(f"[assemble 3b/5] Building 9:16 video track with dynamic tpad extensions and blurred pillarbox ({language})...")
    build_concatenated_video_9x16(storyboard, raw_video_9x16, effective_slots=effective_slots, prefix=language)

    # 7a. Render final horizontal 16:9 with burned subtitles
    print(f"[assemble 4/5] Rendering horizontal 16:9 -> {target_16x9.name}...")
    render_final_horizontal_16x9(raw_video_16x9, master_audio, subtitles_path, target_16x9, language=language)
    write_sidecar_hash(target_16x9, input_hash)

    # 7b. Render final vertical 9:16 with burned subtitles
    print(f"[assemble 5/5] Rendering vertical 9:16 -> {target_9x16.name} (safe-area subtitles)...")
    render_final_vertical_9x16(raw_video_9x16, master_audio, subtitles_path, target_9x16, language=language)
    write_sidecar_hash(target_9x16, input_hash)

    total_latency = round(time.perf_counter() - start_time, 2)
    dur_16x9 = get_media_duration(target_16x9)
    dur_9x16 = get_media_duration(target_9x16)

    print(f"\nAssembly Complete ({language.upper()}):")
    print(f"  - Horizontal 16:9: {target_16x9} ({dur_16x9:.2f}s, {target_16x9.stat().st_size / 1e6:.2f} MB)")
    print(f"  - Vertical 9:16:   {target_9x16} ({dur_9x16:.2f}s, {target_9x16.stat().st_size / 1e6:.2f} MB)")

    append_run_log({
        "run_id": f"assemble_loc_{language}_{uuid.uuid4().hex[:8]}",
        "stage": "assemble",
        "shot_id": None,
        "provider": "ffmpeg",
        "model": "h264_aac_loudnorm",
        "seed": None,
        "parameters": {
            "language": language,
            "aspect_ratios": ["16:9", "9:16"],
            "horizontal_res": "1920x1080",
            "vertical_res": "1080x1920",
            "fps": 24,
            "loudnorm": "I=-14:TP=-1.0:LRA=11",
        },
        "input_hash": input_hash,
        "output": f"{target_16x9.as_posix()};{target_9x16.as_posix()}",
        "latency_seconds": total_latency,
        "cost_usd": 0.0,
        "cache_hit": False,
        "status": "success",
        "timestamp": datetime.now(timezone.utc).isoformat(),
    })

    return {"horizontal_16x9": target_16x9, "vertical_9x16": target_9x16}
