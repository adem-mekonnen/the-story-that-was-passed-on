"""Milestone 2: API Smoke Test.

Validates API credentials, endpoints, and request specifications for:
1. Gemini 3.8 Flash (Text generation with thinkingBudget=0 and 503 fallback to lite)
2. Gemini 3.8 Flash TTS (Interactions API with speech_metadata.style and 503 fallback to lite)
3. Cloudflare Workers AI FLUX (Image generation via multipart/form-data)
"""

from __future__ import annotations

import sys
from pathlib import Path

# Ensure project root is on sys.path so script works without PYTHONPATH=.
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import base64
from datetime import datetime, timezone
import os
import time
import uuid

from dotenv import load_dotenv
import httpx

from pipeline.core import (
    append_run_log,
    atomic_write_bytes,
    retry_transient,
    sha256_inputs,
)
from pipeline.providers.gemini import generate_text, generate_tts

# Load credentials from .env
load_dotenv()

GEMINI_API_KEY = os.getenv("GEMINI_API_KEY", "").strip()
CF_ACCOUNT_ID = os.getenv("CF_ACCOUNT_ID", "").strip()
CF_API_TOKEN = os.getenv("CF_API_TOKEN", "").strip()

OUTPUTS_DIR = Path("outputs")


def test_gemini_text() -> tuple[str, str]:
    """Test Gemini text generation with thinkingBudget=0 and 503 fallback."""
    if not GEMINI_API_KEY:
        raise ValueError("Missing GEMINI_API_KEY in environment or .env file.")

    prompt = "Say 'Smoke test passed' and nothing else."
    start_time = time.perf_counter()
    text_output, model_used = generate_text(prompt, api_key=GEMINI_API_KEY)
    latency_seconds = round(time.perf_counter() - start_time, 3)

    append_run_log({
        "run_id": f"smoke_text_{uuid.uuid4().hex[:8]}",
        "stage": "smoke_test",
        "shot_id": None,
        "provider": "gemini",
        "model": model_used,
        "seed": None,
        "parameters": {"prompt": prompt},
        "input_hash": sha256_inputs({"prompt": prompt, "model": model_used}),
        "output": text_output,
        "latency_seconds": latency_seconds,
        "cost_usd": 0.0,
        "cache_hit": False,
        "status": "success",
        "timestamp": datetime.now(timezone.utc).isoformat(),
    })

    return text_output, model_used


def test_gemini_tts() -> tuple[Path, str]:
    """Test Gemini TTS via Interactions API with speech_metadata style and 503 fallback."""
    if not GEMINI_API_KEY:
        raise ValueError("Missing GEMINI_API_KEY in environment or .env file.")

    text = "In a quiet Ethiopian village."
    style = "warm, calm, unhurried storyteller"
    voice = "Puck"

    start_time = time.perf_counter()
    audio_bytes, model_used = generate_tts(
        text=text,
        style=style,
        voice=voice,
        api_key=GEMINI_API_KEY,
    )
    latency_seconds = round(time.perf_counter() - start_time, 3)

    output_path = OUTPUTS_DIR / "smoke_test.wav"
    atomic_write_bytes(output_path, audio_bytes)

    append_run_log({
        "run_id": f"smoke_tts_{uuid.uuid4().hex[:8]}",
        "stage": "smoke_test",
        "shot_id": None,
        "provider": "gemini",
        "model": model_used,
        "seed": None,
        "parameters": {"text": text, "style": style, "voice": voice},
        "input_hash": sha256_inputs({"text": text, "style": style, "voice": voice, "model": model_used}),
        "output": str(output_path).replace("\\", "/"),
        "latency_seconds": latency_seconds,
        "cost_usd": 0.0,
        "cache_hit": False,
        "status": "success",
        "timestamp": datetime.now(timezone.utc).isoformat(),
    })

    return output_path, model_used


@retry_transient(max_attempts=3)
def test_cloudflare_flux() -> Path:
    """Make one real call to Cloudflare Workers AI FLUX using multipart/form-data."""
    if not CF_ACCOUNT_ID or not CF_API_TOKEN:
        raise ValueError("Missing CF_ACCOUNT_ID or CF_API_TOKEN in environment or .env file.")

    model = "@cf/black-forest-labs/flux-2-klein-4b"
    url = f"https://api.cloudflare.com/client/v4/accounts/{CF_ACCOUNT_ID}/ai/run/{model}"
    prompt = "A peaceful Ethiopian village at sunset."
    steps = 4

    headers = {
        "Authorization": f"Bearer {CF_API_TOKEN}",
    }

    # CRITICAL: multipart/form-data with steps strictly equal to 4
    files = {
        "prompt": (None, prompt),
        "steps": (None, str(steps)),
    }

    start_time = time.perf_counter()
    with httpx.Client(timeout=60.0) as client:
        response = client.post(url, headers=headers, files=files)
        response.raise_for_status()

        if response.headers.get("content-type", "").startswith("image/"):
            image_bytes = response.content
        else:
            data = response.json()
            image_b64 = data.get("image") or data.get("result", {}).get("image")
            if not image_b64:
                raise ValueError(f"No image found in Cloudflare response: {data}")
            image_bytes = base64.b64decode(image_b64)

    latency_seconds = round(time.perf_counter() - start_time, 3)

    output_path = OUTPUTS_DIR / "smoke_test.png"
    atomic_write_bytes(output_path, image_bytes)

    append_run_log({
        "run_id": f"smoke_flux_{uuid.uuid4().hex[:8]}",
        "stage": "smoke_test",
        "shot_id": None,
        "provider": "cloudflare",
        "model": model,
        "seed": None,
        "parameters": {"prompt": prompt, "steps": steps},
        "input_hash": sha256_inputs({"prompt": prompt, "steps": steps, "model": model}),
        "output": str(output_path).replace("\\", "/"),
        "latency_seconds": latency_seconds,
        "cost_usd": 0.0,
        "cache_hit": False,
        "status": "success",
        "timestamp": datetime.now(timezone.utc).isoformat(),
    })

    return output_path


def main() -> None:
    print("=== Milestone 2: API Smoke Test ===")

    # [1/3] Gemini Text
    print("\n[1/3] Testing Gemini 3.8 Flash (Text)...")
    start_time_text = time.perf_counter()
    try:
        text_result, model_used = test_gemini_text()
        print(f" -> SUCCESS ({model_used}): Gemini text response: {text_result!r}")
    except Exception as exc:
        latency_text = round(time.perf_counter() - start_time_text, 3)
        print(f" -> ERROR: Gemini text test failed: {exc}")
        if isinstance(exc, httpx.HTTPStatusError):
            print(f"    Status code: {exc.response.status_code}")
            print(f"    Response body: {exc.response.text}")
        prompt = "Say 'Smoke test passed' and nothing else."
        err_body = exc.response.text if isinstance(exc, httpx.HTTPStatusError) else str(exc)
        append_run_log({
            "run_id": f"smoke_text_{uuid.uuid4().hex[:8]}",
            "stage": "smoke_test",
            "shot_id": None,
            "provider": "gemini",
            "model": "gemini-3.8-flash",
            "seed": None,
            "parameters": {"prompt": prompt},
            "input_hash": sha256_inputs({"prompt": prompt, "model": "gemini-3.8-flash"}),
            "output": err_body,
            "latency_seconds": latency_text,
            "cost_usd": 0.0,
            "cache_hit": False,
            "status": "error",
            "timestamp": datetime.now(timezone.utc).isoformat(),
        })

    # [2/3] Gemini TTS
    print("\n[2/3] Testing Gemini 3.8 Flash TTS (Audio)...")
    start_time_tts = time.perf_counter()
    try:
        tts_result, model_used = test_gemini_tts()
        print(f" -> SUCCESS ({model_used}): Gemini TTS audio saved to {tts_result}")
    except Exception as exc:
        latency_tts = round(time.perf_counter() - start_time_tts, 3)
        print(f" -> ERROR: Gemini TTS test failed: {exc}")
        if isinstance(exc, httpx.HTTPStatusError):
            print(f"    Status code: {exc.response.status_code}")
            print(f"    Response body: {exc.response.text}")
        text = "In a quiet Ethiopian village."
        style = "warm, calm, unhurried storyteller"
        err_body = exc.response.text if isinstance(exc, httpx.HTTPStatusError) else str(exc)
        append_run_log({
            "run_id": f"smoke_tts_{uuid.uuid4().hex[:8]}",
            "stage": "smoke_test",
            "shot_id": None,
            "provider": "gemini",
            "model": "gemini-3.8-flash-tts",
            "seed": None,
            "parameters": {"text": text, "style": style},
            "input_hash": sha256_inputs({"text": text, "style": style, "model": "gemini-3.8-flash-tts"}),
            "output": err_body,
            "latency_seconds": latency_tts,
            "cost_usd": 0.0,
            "cache_hit": False,
            "status": "error",
            "timestamp": datetime.now(timezone.utc).isoformat(),
        })

    # [3/3] Cloudflare FLUX
    print("\n[3/3] Testing Cloudflare Workers AI FLUX (Image)...")
    start_time_flux = time.perf_counter()
    try:
        flux_result = test_cloudflare_flux()
        print(f" -> SUCCESS: Cloudflare FLUX image saved to {flux_result}")
    except Exception as exc:
        latency_flux = round(time.perf_counter() - start_time_flux, 3)
        print(f" -> ERROR: Cloudflare FLUX test failed: {exc}")
        if isinstance(exc, httpx.HTTPStatusError):
            print(f"    Status code: {exc.response.status_code}")
            print(f"    Response body: {exc.response.text}")
        prompt = "A peaceful Ethiopian village at sunset."
        steps = 4
        model = "@cf/black-forest-labs/flux-2-klein-4b"
        err_body = exc.response.text if isinstance(exc, httpx.HTTPStatusError) else str(exc)
        append_run_log({
            "run_id": f"smoke_flux_{uuid.uuid4().hex[:8]}",
            "stage": "smoke_test",
            "shot_id": None,
            "provider": "cloudflare",
            "model": model,
            "seed": None,
            "parameters": {"prompt": prompt, "steps": steps},
            "input_hash": sha256_inputs({"prompt": prompt, "steps": steps, "model": model}),
            "output": err_body,
            "latency_seconds": latency_flux,
            "cost_usd": 0.0,
            "cache_hit": False,
            "status": "error",
            "timestamp": datetime.now(timezone.utc).isoformat(),
        })

    print("\n=== Smoke Test Execution Finished ===")


if __name__ == "__main__":
    main()
