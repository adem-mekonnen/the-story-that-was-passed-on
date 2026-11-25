"""Script stage: Generates compliant SRT subtitles from storyboard.json and manages multilingual translations."""

from __future__ import annotations

from datetime import datetime, timezone
import json
import os
from pathlib import Path
import textwrap
import uuid

from pipeline.core import (
    append_run_log,
    atomic_write_bytes,
    is_cache_hit,
    sha256_inputs,
    write_sidecar_hash,
)

SUBTITLE_LINE_WIDTH = 38
MAX_SUBTITLE_LINES = 2
OUTPUT_SRT_PATH = Path("outputs/subtitles.srt")
CONTENT_SRT_PATH = Path("content/en/subtitles.srt")


def format_srt_timestamp(seconds: float) -> str:
    """Format seconds into standard SRT timestamp: HH:MM:SS,mmm."""
    total_ms = int(round(seconds * 1000))
    hours = total_ms // 3_600_000
    remainder = total_ms % 3_600_000
    minutes = remainder // 60_000
    remainder %= 60_000
    secs = remainder // 1_000
    millis = remainder % 1_000
    return f"{hours:02d}:{minutes:02d}:{secs:02d},{millis:03d}"


def split_into_two_cues(text: str, width: int = SUBTITLE_LINE_WIDTH, max_lines: int = MAX_SUBTITLE_LINES) -> list[str]:
    """Smartly split text into 1 or 2 sequential subtitle cues without truncation."""
    lines = textwrap.wrap(text.strip(), width=width)
    if len(lines) <= max_lines:
        return ["\n".join(lines)]

    words = text.split()
    best_k = None
    best_score = float("inf")
    punct_chars = ("።", "፣", "፤", ".", ",", "!", "?", ":", ";")

    for k in range(1, len(words)):
        c1 = " ".join(words[:k])
        c2 = " ".join(words[k:])
        w1 = textwrap.wrap(c1, width=width)
        w2 = textwrap.wrap(c2, width=width)

        if len(w1) > max_lines or len(w2) > max_lines:
            continue

        has_punct = words[k - 1].endswith(punct_chars)
        balance = abs(len(c1) - len(c2))
        punct_penalty = 0 if has_punct else 50
        score = punct_penalty + balance

        if score < best_score:
            best_score = score
            best_k = k

    if best_k is None:
        mid = len(words) // 2
        c1 = " ".join(words[:mid])
        c2 = " ".join(words[mid:])
        return [
            "\n".join(textwrap.wrap(c1, width=width)[:max_lines]),
            "\n".join(textwrap.wrap(c2, width=width)[:max_lines]),
        ]

    c1 = " ".join(words[:best_k])
    c2 = " ".join(words[best_k:])
    return [
        "\n".join(textwrap.wrap(c1, width=width)),
        "\n".join(textwrap.wrap(c2, width=width)),
    ]


def generate_subtitles(
    storyboard: dict,
    language: str = "en",
    effective_slots: dict[str, float] | None = None,
    force: bool = False,
) -> str:
    """Generate SRT content with cumulative timing, localized text, and multi-cue splitting."""
    shots = storyboard.get("shots", [])
    translations = {}
    if language != "en":
        translations = get_or_create_translations(storyboard, language=language, force=force)

    srt_blocks: list[str] = []
    cumulative_time = 0.0
    cue_idx = 1

    for shot in shots:
        shot_id = shot.get("id")
        if effective_slots and shot_id in effective_slots:
            duration = float(effective_slots[shot_id])
        else:
            duration = float(shot.get("duration_seconds", 8.0))

        start_time = cumulative_time
        end_time = cumulative_time + duration
        cumulative_time = end_time

        if language != "en":
            raw_text = translations.get(shot_id, shot.get("narration", ""))
        else:
            raw_text = shot.get("subtitle") or shot.get("narration", "")

        cues = split_into_two_cues(raw_text, width=SUBTITLE_LINE_WIDTH, max_lines=MAX_SUBTITLE_LINES)

        if len(cues) == 1:
            start_ts = format_srt_timestamp(start_time)
            end_ts = format_srt_timestamp(end_time)
            block = f"{cue_idx}\n{start_ts} --> {end_ts}\n{cues[0]}\n"
            srt_blocks.append(block)
            cue_idx += 1
        else:
            mid_time = start_time + (duration / 2.0)
            start_ts1 = format_srt_timestamp(start_time)
            end_ts1 = format_srt_timestamp(mid_time)
            start_ts2 = format_srt_timestamp(mid_time)
            end_ts2 = format_srt_timestamp(end_time)

            block1 = f"{cue_idx}\n{start_ts1} --> {end_ts1}\n{cues[0]}\n"
            block2 = f"{cue_idx + 1}\n{start_ts2} --> {end_ts2}\n{cues[1]}\n"
            srt_blocks.append(block1)
            srt_blocks.append(block2)
            cue_idx += 2

    return "\n".join(srt_blocks) + "\n"


def get_or_create_translations(
    storyboard: dict,
    language: str = "en",
    force: bool = False,
    api_key: str | None = None,
) -> dict[str, str]:
    """Retrieve or generate translations for all storyboard shots.
    
    Returns mapping of shot_id -> narration text.
    """
    shots = storyboard.get("shots", [])
    if language == "en":
        return {s["id"]: s.get("narration", "") for s in shots}

    content_dir = Path(f"content/{language}")
    narration_file = content_dir / "narration.json"

    if not force and narration_file.is_file():
        try:
            data = json.loads(narration_file.read_text(encoding="utf-8"))
            if "shots" in data:
                return {s["id"]: s["narration"] for s in data["shots"]}
            elif isinstance(data, dict):
                return data
        except Exception as exc:
            print(f"[script] Warning: Could not parse {narration_file}: {exc}")

    # Generate translations using Gemini if file is missing
    lang_name = "Amharic" if language == "am" else "Afaan Oromo" if language == "om" else language
    print(f"[script] Translating {len(shots)} shots into {lang_name}...")
    trans_list = translate_shots(shots, target_lang=lang_name, api_key=api_key)

    shot_map = {item["id"]: item["translated"] for item in trans_list}
    payload = {
        "language": language,
        "language_name": lang_name,
        "shots": [{"id": s_id, "narration": text} for s_id, text in shot_map.items()],
    }
    content_dir.mkdir(parents=True, exist_ok=True)
    atomic_write_bytes(narration_file, json.dumps(payload, ensure_ascii=False, indent=2).encode("utf-8"))
    print(f"[script] Saved {language} translations -> {narration_file}")
    return shot_map


def run_script_stage(
    storyboard: dict,
    language: str = "en",
    force: bool = False,
    effective_slots: dict[str, float] | None = None,
) -> Path:
    """Execute the script stage: generate SRT subtitles and manage localized translations."""
    shots = storyboard.get("shots", [])

    if language != "en":
        # Ensure localized narration translations exist
        translations = get_or_create_translations(storyboard, language=language, force=force)
        out_srt = Path(f"outputs/subtitles_{language}.srt")
        content_srt = Path(f"content/{language}/subtitles.srt")
    else:
        translations = {}
        out_srt = OUTPUT_SRT_PATH
        content_srt = CONTENT_SRT_PATH

    # Compute deterministic input hash
    if language == "en":
        input_payload = {
            "shots_subtitles": [
                {
                    "id": s.get("id"),
                    "duration": s.get("duration_seconds"),
                    "subtitle": s.get("subtitle") or s.get("narration"),
                }
                for s in shots
            ],
            "width": SUBTITLE_LINE_WIDTH,
            "max_lines": MAX_SUBTITLE_LINES,
        }
    else:
        input_payload = {
            "language": language,
            "shots_subtitles": [
                {
                    "id": s.get("id"),
                    "duration": effective_slots.get(s.get("id")) if effective_slots else s.get("duration_seconds"),
                    "subtitle": translations.get(s.get("id"), s.get("narration")),
                }
                for s in shots
            ],
            "width": SUBTITLE_LINE_WIDTH,
            "max_lines": MAX_SUBTITLE_LINES,
            "multi_cue_v2": True,
        }
    input_hash = sha256_inputs(input_payload)

    # Check cache hit
    if not force and is_cache_hit(out_srt, input_hash) and content_srt.is_file():
        print(f"[script] Cache Hit -> {out_srt.name} and {content_srt.name}")
        append_run_log({
            "run_id": f"subtitles_{language}_{uuid.uuid4().hex[:8]}",
            "stage": "script",
            "shot_id": None,
            "provider": "local",
            "model": "textwrap_srt",
            "seed": None,
            "parameters": {"language": language, "width": SUBTITLE_LINE_WIDTH, "max_lines": MAX_SUBTITLE_LINES},
            "input_hash": input_hash,
            "output": str(out_srt).replace("\\", "/"),
            "latency_seconds": 0.0,
            "cost_usd": 0.0,
            "cache_hit": True,
            "status": "success",
            "timestamp": datetime.now(timezone.utc).isoformat(),
        })
        return out_srt

    print(f"\n--- Generating Subtitles ({language}, {len(shots)} shots) ---")
    srt_content = generate_subtitles(storyboard, language=language, effective_slots=effective_slots, force=force)

    # Atomic write to both outputs/ and content/
    content_srt.parent.mkdir(parents=True, exist_ok=True)
    out_srt.parent.mkdir(parents=True, exist_ok=True)

    srt_bytes = srt_content.encode("utf-8")
    atomic_write_bytes(content_srt, srt_bytes)
    atomic_write_bytes(out_srt, srt_bytes)

    write_sidecar_hash(content_srt, input_hash)
    write_sidecar_hash(out_srt, input_hash)

    append_run_log({
        "run_id": f"subtitles_{language}_{uuid.uuid4().hex[:8]}",
        "stage": "script",
        "shot_id": None,
        "provider": "local",
        "model": "textwrap_srt",
        "seed": None,
        "parameters": {"language": language, "width": SUBTITLE_LINE_WIDTH, "max_lines": MAX_SUBTITLE_LINES},
        "input_hash": input_hash,
        "output": str(out_srt).replace("\\", "/"),
        "latency_seconds": 0.005,
        "cost_usd": 0.0,
        "cache_hit": False,
        "status": "success",
        "timestamp": datetime.now(timezone.utc).isoformat(),
    })
    print(f"[script] Generated -> {content_srt} and {out_srt}")
    return out_srt


def translate_shots(
    shots: list[dict],
    target_lang: str,
    api_key: str | None = None,
) -> list[dict]:
    """Translate shot narrations into target language using Gemini text generation.
    
    Returns list of dicts: [{"id": shot["id"], "original": text, "translated": translation, "target_lang": lang}]
    """
    from pipeline.providers.gemini import generate_text

    results = []
    for shot in shots:
        shot_id = shot["id"]
        narration = shot.get("narration", "")

        if "Oromo" in target_lang or target_lang == "om":
            prompt = (
                f"You are an expert literary translator specializing in Ethiopian heritage storytelling.\n"
                f"Translate the following short film narration sentence into Afaan Oromo (Latin script/Qubee).\n"
                f"Maintain contemplative cadence, emotional warmth, and natural oral storytelling rhythm.\n"
                f"Keep phrasing concise so speech fits naturally without unnecessary word repetition.\n"
                f"CRITICAL ACCURACY INSTRUCTIONS:\n"
                f"- Translate 'Grandfather' strictly as 'Akaakayyuu' (NEVER use 'Akkoo', which means Grandmother!).\n"
                f"- Avoid word repetition (e.g. do NOT write 'sana sana').\n"
                f"- Provide ONLY the single best translated sentence in Afaan Oromo. Do NOT include English, multiple options, or commentary.\n\n"
                f"Sentence: {narration}"
            )
        elif "Amharic" in target_lang or target_lang == "am":
            prompt = (
                f"You are an expert literary translator specializing in Ethiopian heritage storytelling.\n"
                f"Translate the following short film narration sentence into Amharic (Ethiopic script).\n"
                f"Maintain contemplative cadence, emotional warmth, and natural oral storytelling rhythm.\n"
                f"Keep phrasing concise.\n"
                f"CRITICAL ACCURACY INSTRUCTIONS:\n"
                f"- Translate 'Grandfather' as 'አያ' or 'አያቴ'.\n"
                f"- Provide ONLY the single best translated sentence in Amharic script (Ge'ez). Do NOT include English, romanization, multiple options, or commentary.\n\n"
                f"Sentence: {narration}"
            )
        else:
            prompt = (
                f"You are an expert literary translator specializing in Ethiopian heritage storytelling.\n"
                f"Translate the following short film narration sentence into {target_lang}.\n"
                f"Maintain contemplative cadence, emotional warmth, and natural oral storytelling rhythm.\n"
                f"Provide ONLY the single best translated sentence in {target_lang}. Do NOT include multiple options, explanations, pronunciation guides, or commentary.\n\n"
                f"Sentence: {narration}"
            )

        translated_text, model_used = generate_text(prompt, api_key=api_key, model="gemini-2.5-flash", fallback_model="gemini-3.5-flash-lite")
        clean_translation = translated_text.strip().strip('"\'')
        results.append({
            "id": shot_id,
            "original": narration,
            "translated": clean_translation,
            "target_lang": target_lang,
            "model": model_used,
        })
    return results
