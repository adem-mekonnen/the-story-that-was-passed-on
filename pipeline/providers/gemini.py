"""Gemini provider client for text, vision, and speech generation."""

from __future__ import annotations

import base64
import os
import time
from typing import Any

import httpx

from pipeline.core import retry_transient

DEFAULT_TIMEOUT = 60.0


def _extract_audio_base64(data: dict[str, Any]) -> str:
    """Extract base64 audio data from Google Interactions or GenerateContent response."""
    # 1. Search in steps[].content[]
    for step in data.get("steps", []):
        for item in step.get("content", []):
            if isinstance(item, dict):
                if "data" in item and isinstance(item["data"], str):
                    return item["data"]
                if "inlineData" in item and "data" in item["inlineData"]:
                    return item["inlineData"]["data"]
                if "audio" in item and isinstance(item["audio"], str):
                    return item["audio"]

    # 2. Search in outputs
    outputs = data.get("outputs")
    if isinstance(outputs, list):
        for out in outputs:
            if isinstance(out, dict):
                if "data" in out and isinstance(out["data"], str):
                    return out["data"]
                content = out.get("content")
                if isinstance(content, list):
                    for c in content:
                        if isinstance(c, dict) and "data" in c:
                            return c["data"]
                elif isinstance(content, dict) and "data" in content:
                    return content["data"]
    elif isinstance(outputs, dict):
        if "data" in outputs and isinstance(outputs["data"], str):
            return outputs["data"]

    # 3. Search in candidates (generateContent fallback)
    for candidate in data.get("candidates", []):
        content = candidate.get("content", {})
        for part in content.get("parts", []):
            if isinstance(part, dict):
                inline_data = part.get("inlineData") or part.get("inline_data")
                if inline_data and "data" in inline_data:
                    return inline_data["data"]

    # 4. Recursive search for any dict key 'data' containing base64 string
    def _search(obj: Any) -> str | None:
        if isinstance(obj, dict):
            if "data" in obj and isinstance(obj["data"], str) and len(obj["data"]) > 100:
                return obj["data"]
            for v in obj.values():
                res = _search(v)
                if res:
                    return res
        elif isinstance(obj, list):
            for item in obj:
                res = _search(item)
                if res:
                    return res
        return None

    res = _search(data)
    if res:
        return res

    raise ValueError(f"Could not find audio bytes in response: {data}")


@retry_transient(max_attempts=3)
def _call_text_api(model: str, prompt: str, api_key: str) -> str:
    """Internal caller for Gemini text generation with retry."""
    url = f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent"
    headers = {
        "x-goog-api-key": api_key,
        "Content-Type": "application/json",
    }
    payload: dict[str, Any] = {
        "contents": [
            {
                "parts": [
                    {"text": prompt}
                ]
            }
        ]
    }
    # thinkingConfig is only valid for thinking-capable models (gemini-3.8-flash).
    # Non-thinking models (flash-lite, 2.5-flash) reject it with 400 INVALID_ARGUMENT.
    if "flash-lite" not in model and "2.5-flash" not in model:
        payload["generationConfig"] = {
            "thinkingConfig": {
                "thinkingBudget": 0
            }
        }

    with httpx.Client(timeout=60.0) as client:
        response = client.post(url, headers=headers, json=payload)
        response.raise_for_status()
        data = response.json()
    return data["candidates"][0]["content"]["parts"][0]["text"].strip()


def generate_text(
    prompt: str,
    api_key: str | None = None,
    model: str = "gemini-3.8-flash",
    fallback_model: str = "gemini-2.5-flash",
) -> tuple[str, str]:
    """Generate text using Gemini with thinkingBudget=0 and automatic fallback on 503/timeout."""
    key = api_key or os.getenv("GEMINI_API_KEY", "").strip()
    if not key:
        raise ValueError("Missing GEMINI_API_KEY in environment or argument.")

    try:
        text = _call_text_api(model, prompt, key)
        return text, model
    except (httpx.HTTPStatusError, httpx.TimeoutException) as exc:
        is_transient = isinstance(exc, httpx.TimeoutException) or (
            isinstance(exc, httpx.HTTPStatusError) and exc.response.status_code in (429, 503)
        )
        if is_transient and fallback_model:
            status_desc = exc.response.status_code if isinstance(exc, httpx.HTTPStatusError) else type(exc).__name__
            print(f"Warning: Primary model '{model}' encountered {status_desc}. Falling back to '{fallback_model}'...")
            time.sleep(1.0)
            try:
                text = _call_text_api(fallback_model, prompt, key)
                return text, fallback_model
            except (httpx.HTTPStatusError, httpx.TimeoutException) as fb_exc:
                if fallback_model != "gemini-3.5-flash-lite":
                    print(f"Warning: Model '{fallback_model}' hit {fb_exc}. Trying 'gemini-3.5-flash-lite'...")
                    time.sleep(1.0)
                    text = _call_text_api("gemini-3.5-flash-lite", prompt, key)
                    return text, "gemini-3.5-flash-lite"
                raise
        raise


@retry_transient(max_attempts=3)
def _call_tts_interactions_api(
    model: str,
    text: str,
    style: str,
    voice: str,
    api_key: str,
) -> bytes:
    """Internal caller for Gemini TTS via Interactions API with retry."""
    import io
    import wave

    url = "https://generativelanguage.googleapis.com/v1beta/interactions"
    headers = {
        "x-goog-api-key": api_key,
        "Content-Type": "application/json",
    }
    
    # Speech metadata annotations are strictly supported on 3.8-tier models
    content_dict: dict[str, Any] = {"type": "text", "text": text}
    if "3.8" in model:
        content_dict["annotations"] = [{"type": "speech_metadata", "style": style}]

    payload = {
        "model": model,
        "input": [
            {
                "type": "user_input",
                "content": [content_dict]
            }
        ],
        "response_format": {"type": "audio"},
        "generation_config": {
            "speech_config": [{"voice": voice}]
        }
    }

    with httpx.Client(timeout=90.0) as client:
        response = client.post(url, headers=headers, json=payload)
        if response.status_code in (400, 404):
            print(f"Interactions API returned {response.status_code}:\n{response.text}")
        response.raise_for_status()
        data = response.json()

    b64_data = _extract_audio_base64(data)
    audio_bytes = base64.b64decode(b64_data)

    if not audio_bytes.startswith(b"RIFF"):
        # Wrap raw 24kHz 16-bit mono PCM into standard WAV container
        buf = io.BytesIO()
        with wave.open(buf, "wb") as w:
            w.setnchannels(1)
            w.setsampwidth(2)
            w.setframerate(24000)
            w.writeframes(audio_bytes)
        audio_bytes = buf.getvalue()

    return audio_bytes


def generate_tts(
    text: str,
    style: str,
    voice: str = "Puck",
    api_key: str | None = None,
    model: str = "gemini-3.8-flash-tts",
    fallback_model: str = "gemini-3.1-flash-tts-preview",
) -> tuple[bytes, str]:
    """Generate speech using Gemini TTS Interactions API with multi-tier quota fallback."""
    key = api_key or os.getenv("GEMINI_API_KEY", "").strip()
    if not key:
        raise ValueError("Missing GEMINI_API_KEY in environment or argument.")

    max_attempts = 5
    for attempt in range(1, max_attempts + 1):
        try:
            audio = _call_tts_interactions_api(model, text, style, voice, key)
            return audio, model
        except (httpx.HTTPStatusError, httpx.TimeoutException, httpx.NetworkError, httpx.TransportError, ConnectionResetError, OSError) as exc:
            is_429 = isinstance(exc, httpx.HTTPStatusError) and exc.response.status_code == 429
            if is_429:
                if fallback_model:
                    try:
                        print(f"Warning: Primary '{model}' hit 429. Routing request to fallback '{fallback_model}'...")
                        audio = _call_tts_interactions_api(fallback_model, text, style, voice, key)
                        return audio, fallback_model
                    except Exception as fb_exc:
                        print(f"Notice: Fallback '{fallback_model}' hit {fb_exc}.")
                wait_time = 15.0 + (10.0 * attempt)
                print(f"Notice: Rate limit (429) across models (attempt {attempt}/{max_attempts}). Backing off {wait_time:.0f}s...")
                time.sleep(wait_time)
                continue

            if attempt < max_attempts:
                print(f"Notice: Transient error ({exc}) on attempt {attempt}/{max_attempts}. Waiting 10s...")
                time.sleep(10.0)
                continue
            raise

    raise RuntimeError(f"Failed to generate TTS after {max_attempts} attempts due to repeated rate limits.")


class GeminiProvider:
    """Client for Google Gemini multimodal API endpoints."""

    def __init__(self, api_key: str | None = None, timeout: float = DEFAULT_TIMEOUT):
        self.api_key = api_key or os.getenv("GEMINI_API_KEY", "").strip()
        self.timeout = timeout

    def generate_text(
        self,
        prompt: str,
        model: str = "gemini-3.8-flash",
        fallback_model: str = "gemini-3.5-flash-lite",
    ) -> tuple[str, str]:
        return generate_text(prompt, api_key=self.api_key, model=model, fallback_model=fallback_model)

    def generate_tts(
        self,
        text: str,
        style: str,
        voice: str = "Puck",
        model: str = "gemini-3.8-flash-tts",
        fallback_model: str = "gemini-3.1-flash-tts-preview",
    ) -> tuple[bytes, str]:
        return generate_tts(text, style, voice=voice, api_key=self.api_key, model=model, fallback_model=fallback_model)
