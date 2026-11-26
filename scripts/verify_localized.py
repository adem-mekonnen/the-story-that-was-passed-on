"""Verification script for all 6 master film cuts and volume levels."""

import json
from pathlib import Path
import shutil
import subprocess

FILES = [
    Path("outputs/final/heritage_short_am_9x16.mp4"),
    Path("outputs/final/heritage_short_am_16x9.mp4"),
    Path("outputs/final/heritage_short_om_9x16.mp4"),
    Path("outputs/final/heritage_short_om_16x9.mp4"),
    Path("outputs/final/heritage_short_vertical_9x16.mp4"),
    Path("outputs/final/heritage_short_horizontal_16x9.mp4"),
]

FFMPEG = shutil.which("ffmpeg") or "ffmpeg"
FFPROBE = shutil.which("ffprobe") or "ffprobe"

print("=" * 95)
print(f"{'Film Cut':<42} | {'Duration':<9} | {'Size':<9} | {'Resolution':<11} | {'FPS':<6} | {'Audio'}")
print("-" * 95)

for p in FILES:
    if not p.is_file():
        print(f"MISSING: {p}")
        continue
    cmd = [
        FFPROBE,
        "-v", "error",
        "-show_entries", "format=duration,size:stream=codec_name,width,height,r_frame_rate",
        "-of", "json",
        str(p),
    ]
    res = subprocess.run(cmd, capture_output=True, text=True, check=True)
    data = json.loads(res.stdout)
    v_stream = next((s for s in data["streams"] if s.get("width")), {})
    a_stream = next((s for s in data["streams"] if s["codec_name"] in ("aac", "pcm_s16le")), {})
    dur = float(data["format"]["duration"])
    size_mb = int(data["format"]["size"]) / 1e6
    res_str = f"{v_stream.get('width', 0)}x{v_stream.get('height', 0)}"
    fps = eval(v_stream.get("r_frame_rate", "24/1"))
    a_codec = a_stream.get("codec_name", "none")
    print(f"{p.name:<42} | {dur:>7.2f}s | {size_mb:>6.2f} MB | {res_str:<11} | {fps:>4.0f}fps | {a_codec}")

print("=" * 95)

print("\n--- Volume Detection (EBU R128 compliance) ---")
for p in FILES[:4]:
    cmd_vol = [
        FFMPEG,
        "-i", str(p),
        "-af", "volumedetect",
        "-f", "null",
        "-",
    ]
    res_vol = subprocess.run(cmd_vol, capture_output=True, text=True)
    mean_vol = "N/A"
    max_vol = "N/A"
    for line in res_vol.stderr.splitlines():
        if "mean_volume:" in line:
            mean_vol = line.split("mean_volume:")[1].strip()
        elif "max_volume:" in line:
            max_vol = line.split("max_volume:")[1].strip()
    print(f"{p.name}: mean_volume = {mean_vol}, max_volume = {max_vol}")
