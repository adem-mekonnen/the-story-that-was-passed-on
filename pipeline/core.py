"""Core primitives for hashing, caching, atomic I/O, logging, and retry logic."""

from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
from typing import Any, Callable

import httpx
from tenacity import retry, retry_if_exception, stop_after_attempt, wait_exponential

__all__ = [
    "sha256_inputs",
    "atomic_write_bytes",
    "write_sidecar_hash",
    "read_sidecar_hash",
    "is_cache_hit",
    "append_run_log",
    "retry_transient",
]


def sha256_inputs(fields: dict[str, Any]) -> str:
    """Compute deterministic SHA-256 hash of input dictionary."""
    serialized = json.dumps(fields, sort_keys=True, ensure_ascii=True, default=str)
    return hashlib.sha256(serialized.encode("utf-8")).hexdigest()


def atomic_write_bytes(path: Path, data: bytes) -> None:
    """Write bytes atomically to target path using a temporary file."""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp_path = path.with_name(f"{path.name}.tmp")
    try:
        with open(tmp_path, "wb") as f:
            f.write(data)
            f.flush()
            os.fsync(f.fileno())
        tmp_path.replace(path)
    except Exception:
        if tmp_path.exists():
            tmp_path.unlink()
        raise


def write_sidecar_hash(path: Path, hash_hex: str) -> None:
    """Write sidecar .hash file for an asset."""
    sidecar_path = Path(f"{path}.hash")
    atomic_write_bytes(sidecar_path, hash_hex.strip().encode("utf-8"))


def read_sidecar_hash(path: Path) -> str | None:
    """Read SHA-256 hash from sidecar file, returning None if missing."""
    sidecar_path = Path(f"{path}.hash")
    if not sidecar_path.is_file():
        return None
    return sidecar_path.read_text(encoding="utf-8").strip()


def is_cache_hit(path: Path, expected_hash: str) -> bool:
    """Check if output asset exists and its sidecar hash matches expected hash."""
    path = Path(path)
    if not path.is_file():
        return False
    cached_hash = read_sidecar_hash(path)
    if cached_hash is None:
        return False
    return cached_hash.strip().lower() == expected_hash.strip().lower()


def append_run_log(entry: dict[str, Any], log_path: Path = Path("runs.jsonl")) -> None:
    """Append one structured JSON line to runs.jsonl."""
    log_path = Path(log_path)
    log_path.parent.mkdir(parents=True, exist_ok=True)
    line = json.dumps(entry, default=str) + "\n"
    with open(log_path, "a", encoding="utf-8") as f:
        f.write(line)


def retry_transient(max_attempts: int = 3) -> Callable[[Any], Any]:
    """Tenacity retry decorator for transient HTTP errors with exponential backoff.

    Retries ONLY on:
      - httpx.HTTPStatusError with status 429 or >= 500
      - httpx.TimeoutException
      - httpx.ConnectError
    Fails immediately on 400, 401, 403, 404, or any non-transient error.
    """
    def _is_transient(exc: BaseException) -> bool:
        if isinstance(exc, (httpx.TimeoutException, httpx.NetworkError, httpx.TransportError, ConnectionResetError, OSError)):
            return True
        if isinstance(exc, httpx.HTTPStatusError):
            code = exc.response.status_code
            return code == 429 or code >= 500
        return False

    return retry(
        reraise=True,
        stop=stop_after_attempt(max_attempts),
        wait=wait_exponential(multiplier=0.1, min=0.1, max=2.0),
        retry=retry_if_exception(_is_transient),
    )
