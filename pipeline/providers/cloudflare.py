"""Cloudflare Workers AI provider client for FLUX.2 image generation."""

from __future__ import annotations

import base64
import io
import os
from pathlib import Path
from typing import Any

import httpx
from PIL import Image

from pipeline.core import retry_transient

DEFAULT_TIMEOUT = 90.0
FLUX_MODEL = "@cf/black-forest-labs/flux-2-klein-4b"


class CloudflareAIProvider:
    """Client for Cloudflare Workers AI FLUX endpoints with transient retries and 90s timeout."""

    def __init__(
        self,
        account_id: str | None = None,
        api_token: str | None = None,
        timeout: float = DEFAULT_TIMEOUT,
    ):
        self.account_id = account_id or os.getenv("CF_ACCOUNT_ID", "").strip()
        self.api_token = api_token or os.getenv("CF_API_TOKEN", "").strip()
        self.timeout = timeout

    @retry_transient(max_attempts=3)
    def generate_image(
        self,
        prompt: str,
        width: int = 1280,
        height: int = 704,
        steps: int = 4,
        seed: int | None = None,
        ref_image_paths: list[Path | str] | None = None,
        model: str = FLUX_MODEL,
    ) -> bytes:
        """Call Cloudflare Workers AI FLUX using multipart/form-data.

        If ref_image_paths are provided (up to 4), resizes each in-memory so both width
        and height are strictly < 512 (e.g., 448x448) and attaches as input_image_0, etc.
        """
        if not self.account_id or not self.api_token:
            raise ValueError("CF_ACCOUNT_ID and CF_API_TOKEN are required.")

        url = f"https://api.cloudflare.com/client/v4/accounts/{self.account_id}/ai/run/{model}"
        headers = {"Authorization": f"Bearer {self.api_token}"}

        # Build multipart form data fields
        files: dict[str, tuple[str | None, Any, str | None] | tuple[str | None, Any]] = {
            "prompt": (None, prompt),
            "steps": (None, str(steps)),
            "width": (None, str(width)),
            "height": (None, str(height)),
        }
        if seed is not None:
            files["seed"] = (None, str(seed))

        # Attach up to 4 resized reference images (< 512px)
        if ref_image_paths:
            for idx, rpath in enumerate(ref_image_paths[:4]):
                p = Path(rpath)
                if p.is_file():
                    with Image.open(p) as img:
                        img = img.convert("RGB")
                        img.thumbnail((448, 448))
                        buf = io.BytesIO()
                        img.save(buf, format="PNG")
                        img_bytes = buf.getvalue()
                        files[f"input_image_{idx}"] = (f"ref_{idx}.png", img_bytes, "image/png")

        with httpx.Client(timeout=self.timeout) as client:
            response = client.post(url, headers=headers, files=files)
            if response.status_code in (400, 404, 429, 500, 503):
                print(f"Cloudflare FLUX API returned {response.status_code}:\n{response.text[:500]}")
            response.raise_for_status()

            if response.headers.get("content-type", "").startswith("image/"):
                return response.content

            data = response.json()
            img_b64 = None
            if isinstance(data, dict):
                if "result" in data and isinstance(data["result"], dict):
                    img_b64 = data["result"].get("image")
                elif "image" in data:
                    img_b64 = data.get("image")

            if not img_b64:
                raise ValueError(f"No image returned from Cloudflare Workers AI: {data}")

            return base64.b64decode(img_b64)


def generate_image(
    prompt: str,
    width: int = 1280,
    height: int = 704,
    steps: int = 4,
    seed: int | None = None,
    ref_image_paths: list[Path | str] | None = None,
    model: str = FLUX_MODEL,
    account_id: str | None = None,
    api_token: str | None = None,
) -> bytes:
    """Convenience module function for Cloudflare FLUX image generation."""
    provider = CloudflareAIProvider(account_id=account_id, api_token=api_token)
    return provider.generate_image(
        prompt=prompt,
        width=width,
        height=height,
        steps=steps,
        seed=seed,
        ref_image_paths=ref_image_paths,
        model=model,
    )
