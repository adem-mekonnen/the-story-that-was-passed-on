"""Tests for deterministic hashing, caching, atomic I/O, and retry logic."""

from __future__ import annotations

import json
from pathlib import Path

import httpx
import pytest

from pipeline.core import (
    append_run_log,
    atomic_write_bytes,
    is_cache_hit,
    read_sidecar_hash,
    retry_transient,
    sha256_inputs,
    write_sidecar_hash,
)


def test_cache_hit_when_hash_matches(tmp_path: Path):
    """Cache hit is true when asset exists and sidecar hash matches input hash."""
    asset_file = tmp_path / "shot_01.png"
    atomic_write_bytes(asset_file, b"sample image content")

    inputs = {"prompt": "Ethiopian highland village at sunset", "seed": 1001, "model": "imagen-3"}
    expected_hash = sha256_inputs(inputs)
    write_sidecar_hash(asset_file, expected_hash)

    assert is_cache_hit(asset_file, expected_hash) is True


def test_cache_miss_when_prompt_changes(tmp_path: Path):
    """Cache hit is false when inputs change resulting in different hash."""
    asset_file = tmp_path / "shot_01.png"
    atomic_write_bytes(asset_file, b"sample image content")

    original_inputs = {"prompt": "Ethiopian highland village at sunset", "seed": 1001}
    original_hash = sha256_inputs(original_inputs)
    write_sidecar_hash(asset_file, original_hash)

    changed_inputs = {"prompt": "Ethiopian highland village during rainstorm", "seed": 1001}
    changed_hash = sha256_inputs(changed_inputs)

    assert is_cache_hit(asset_file, changed_hash) is False


def test_cache_miss_when_asset_missing(tmp_path: Path):
    """Cache hit is false when the output asset file does not exist."""
    asset_file = tmp_path / "nonexistent.mp4"
    sidecar_hash = sha256_inputs({"seed": 1001})
    write_sidecar_hash(asset_file, sidecar_hash)

    assert is_cache_hit(asset_file, sidecar_hash) is False


def test_atomic_write_leaves_no_tmp(tmp_path: Path):
    """Atomic write creates the target file cleanly and leaves no .tmp artifact."""
    target_file = tmp_path / "test_artifact.bin"
    payload = b"deterministic binary payload"

    atomic_write_bytes(target_file, payload)

    assert target_file.is_file()
    assert target_file.read_bytes() == payload
    tmp_marker = tmp_path / f"{target_file.name}.tmp"
    assert not tmp_marker.exists()


def test_retry_succeeds_on_503_then_200():
    """Retry transient decorator retries on 503 and succeeds on subsequent 200."""
    call_count = 0
    request = httpx.Request("POST", "https://api.example.com/generate")

    @retry_transient(max_attempts=3)
    def flaky_service() -> dict:
        nonlocal call_count
        call_count += 1
        if call_count == 1:
            response = httpx.Response(503, request=request)
            raise httpx.HTTPStatusError("Service Unavailable", request=request, response=response)
        return {"status": "success"}

    result = flaky_service()
    assert result == {"status": "success"}
    assert call_count == 2


def test_retry_succeeds_on_timeout_then_success():
    """Retry transient decorator retries on httpx.TimeoutException."""
    call_count = 0
    request = httpx.Request("POST", "https://api.example.com/generate")

    @retry_transient(max_attempts=3)
    def timing_out_service() -> str:
        nonlocal call_count
        call_count += 1
        if call_count == 1:
            raise httpx.ConnectTimeout("Connection timed out", request=request)
        return "recovered"

    result = timing_out_service()
    assert result == "recovered"
    assert call_count == 2


def test_no_retry_on_401_called_once():
    """Client errors like 401 must fail immediately with no retry (call count == 1)."""
    call_count = 0
    request = httpx.Request("POST", "https://api.example.com/generate")

    @retry_transient(max_attempts=3)
    def unauthorized_service():
        nonlocal call_count
        call_count += 1
        response = httpx.Response(401, request=request)
        raise httpx.HTTPStatusError("Unauthorized", request=request, response=response)

    with pytest.raises(httpx.HTTPStatusError) as exc_info:
        unauthorized_service()

    assert exc_info.value.response.status_code == 401
    assert call_count == 1


def test_no_retry_on_404_called_once():
    """Client errors like 404 must fail immediately with no retry (call count == 1)."""
    call_count = 0
    request = httpx.Request("GET", "https://api.example.com/asset")

    @retry_transient(max_attempts=3)
    def missing_resource():
        nonlocal call_count
        call_count += 1
        response = httpx.Response(404, request=request)
        raise httpx.HTTPStatusError("Not Found", request=request, response=response)

    with pytest.raises(httpx.HTTPStatusError) as exc_info:
        missing_resource()

    assert exc_info.value.response.status_code == 404
    assert call_count == 1


def test_append_run_log_records_valid_json(tmp_path: Path):
    """Appending run logs writes valid structured JSON lines."""
    log_file = tmp_path / "runs.jsonl"
    entry = {
        "run_id": "run_001",
        "stage": "keyframes",
        "shot_id": "shot_01",
        "provider": "gemini",
        "model": "imagen-3.0-generate-002",
        "seed": 1001,
        "parameters": {"aspect_ratio": "16:9"},
        "input_hash": "a" * 64,
        "output": "outputs/keyframes/shot_01.png",
        "latency_seconds": 2.45,
        "cost_usd": 0.03,
        "cache_hit": False,
        "status": "success",
        "timestamp": "2026-11-24T19:00:00Z",
    }

    append_run_log(entry, log_path=log_file)
    assert log_file.is_file()

    with open(log_file, "r", encoding="utf-8") as f:
        lines = f.readlines()
    assert len(lines) == 1
    parsed = json.loads(lines[0])
    assert parsed["run_id"] == "run_001"
    assert parsed["status"] == "success"
