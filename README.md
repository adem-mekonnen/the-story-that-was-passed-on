# The Story That Was Passed On

[![Python 3.11+](https://img.shields.io/badge/python-3.11+-blue.svg)](https://www.python.org/downloads/)
[![FFmpeg](https://img.shields.io/badge/FFmpeg-6.0+-green.svg)](https://ffmpeg.org/)
[![License: Apache 2.0](https://img.shields.io/badge/License-Apache_2.0-blue.svg)](https://opensource.org/licenses/Apache-2.0)
[![Test Suite](https://img.shields.io/badge/tests-18%20passed-brightgreen.svg)]()
[![Cost](https://img.shields.io/badge/out--of--pocket-$0.00-success.svg)]()

A contract-driven, deterministic, and fully reproducible AI media production pipeline synthesizing an Ethiopian heritage short film in 16:9 horizontal and 9:16 vertical formats, featuring full multilingual localization into **Amharic (`am`)** and **Afaan Oromo (`om`)**.

---

## 1. Overview & Master Film Outputs

"The Story That Was Passed On" portrays the fireside conversation between an Ethiopian grandfather and his 10-year-old grandchild about why elders repeat the same ancestral stories. The production pipeline is controlled by a single strict contract ([storyboard.json](file:///c:/Users/HP/Documents/the-story-that-was-passed-on/storyboard.json)) and renders four final master short films:

| Film Cut | Language | Aspect Ratio | Resolution | Duration | File Size | Audio Loudness |
|:---|:---:|:---:|:---:|:---:|:---:|:---:|
| [heritage_short_horizontal_16x9.mp4](file:///c:/Users/HP/Documents/the-story-that-was-passed-on/outputs/final/heritage_short_horizontal_16x9.mp4) | English (`en`) | 16:9 | 1920x1080 | 79.00s | 36.96 MB | -14 LUFS (EBU R128) |
| [heritage_short_vertical_9x16.mp4](file:///c:/Users/HP/Documents/the-story-that-was-passed-on/outputs/final/heritage_short_vertical_9x16.mp4) | English (`en`) | 9:16 | 1080x1920 | 79.00s | 23.57 MB | -14 LUFS (EBU R128) |
| [heritage_short_am_9x16.mp4](file:///c:/Users/HP/Documents/the-story-that-was-passed-on/outputs/final/heritage_short_am_9x16.mp4) | Amharic (`am`) | 9:16 | 1080x1920 | 80.90s | 23.92 MB | -14 LUFS (EBU R128) |
| [heritage_short_om_9x16.mp4](file:///c:/Users/HP/Documents/the-story-that-was-passed-on/outputs/final/heritage_short_om_9x16.mp4) | Afaan Oromo (`om`) | 9:16 | 1080x1920 | 80.10s | 23.74 MB | -14 LUFS (EBU R128) |

All vertical 9:16 cuts feature mobile safe-area English subtitles (`MarginV=35, FontSize=12, Outline=2`), blurred pillarboxing for multi-person compositions, dynamic `tpad` video frame extensions, and native 3-second AI disclosure end cards.

---

## 2. Stranger-Ready Clean Clone Guide

Follow these steps to reproduce the entire project on a clean workstation.

### Prerequisites
- **Python**: Version 3.11 or newer (tested on Python 3.11 and Python 3.15.2).
- **FFmpeg & ffprobe**: Installed and available on your system `PATH` (FFmpeg 6.0+ recommended).
- **Git**: Installed.

> [!IMPORTANT]
> **Windows Smart App Control Note**: On Windows 11, execute Python tools through the module flag (e.g. `python -m pip`, `python -m pytest`, `python -m pipeline.run`) rather than calling raw executable wrappers (`pip.exe`, `pytest.exe`) to prevent Smart App Control signature blocks.

### Step 1: Clone Repository & Bootstrap Environment
```bash
git clone https://github.com/example/the-story-that-was-passed-on.git
cd the-story-that-was-passed-on

# Create virtual environment
python -m venv .venv

# Activate environment:
# On Linux / macOS:
source .venv/bin/activate
# On Windows (PowerShell):
.venv\Scripts\Activate.ps1

# Install dependencies via module flag
python -m pip install -r requirements.txt
```

### Step 2: Configure Environment Variables
Create a `.env` file in the project root:
```bash
cp .env.example .env
```
Populate `.env` with your free API credentials:
```env
# Google Gemini API Key (Google AI Studio Free Tier)
GEMINI_API_KEY=your_gemini_api_key_here

# Cloudflare Workers AI (10,000 free Neurons/day)
CF_ACCOUNT_ID=your_cloudflare_account_id_here
CF_API_TOKEN=your_cloudflare_api_token_here
```

### Step 3: Run Validation & Test Suite
Verify that all contracts, schemas, and sidecar caching tests pass (18/18 tests in $< 1$s):
```bash
python -m pytest -v
# or via dry-run contract check:
python -m pipeline.run --dry-run
```

### Step 4: Run the Complete Production Pipeline

To assemble the complete short film suite on any machine without local GPU requirements, execute:

```bash
# English Master Cuts (16:9 and 9:16)
python -m pipeline.run --no-gpu

# Localized Amharic Master Cut (9:16 vertical)
python -m pipeline.run --no-gpu --language am

# Localized Afaan Oromo Master Cut (9:16 vertical)
python -m pipeline.run --no-gpu --language om
```

*(Alternatively, run `make film` on systems with `make` installed).*

---

## 3. Offline & GPU Fallback Bridge

The pipeline is engineered to run seamlessly across local workstations, cloud GPUs, and offline clean clones:
1. **Video Bridge (`--no-gpu`)**: When executing without a CUDA GPU (or after Kaggle's 30 GB host RAM OOM ceiling during Wan 2.2 model offload), `shots.py` automatically synthesizes 24 fps H.264 video clips using programmatic FFmpeg Ken Burns camera choreography (`zoom_in_center`, `pan_right`, `zoom_out_center`, `pan_left`) operating directly on 1280x704 center-composed FLUX.2 Klein 4B keyframes.
2. **Music Bridge**: `music.py` inspects `outputs/music/music_master_83s.wav`. If our authentic 48 kHz ACE-Step 1.5 score is present (from Kaggle T4), it verifies and mixes it. If cloned fresh without the score, it falls back cleanly to an FFmpeg ambient D minor chord pad, guaranteeing zero pipeline crashes.

---

## 4. Repository Structure

```
.
├── .env.example                        # Template for API credentials
├── .gitignore                          # Ignores heavy media, venv, and secrets
├── Makefile                            # Shortcuts for install, test, validate, film
├── README.md                           # Master stranger-ready setup and guide
├── ARCHITECTURE.md                     # Technical DAG, caching, and resilience specs
├── COSTS.md                            # Comprehensive runs.jsonl telemetry and cost ledger
├── DESIGN.md                           # Audience, design rationale, and User Test #1
├── ETHICS.md                           # AI ethics, composite likenesses, and provenance
├── FAILURES.md                         # Authentic production log of Failures 1 through 12
├── EXPERIMENTS.md                      # Systematic scientific experiments (EXP-01 - EXP-10)
├── pytest.ini                          # Pytest configuration (testpaths = tests)
├── requirements.txt                    # Python package dependencies
├── runs.jsonl                          # Structured audit log of all 676 model operations
├── storyboard.json                     # Canonical single contract (10 shots, 79s budget)
├── content/
│   ├── am/                             # Amharic narration.json and subtitles.srt
│   ├── en/                             # English subtitles.srt
│   └── om/                             # Afaan Oromo narration.json and subtitles.srt
├── notebooks/
│   ├── acel_step_colab.ipynb           # Colab ACE-Step audio experimentation
│   └── wan22_kaggle.ipynb              # Kaggle T4 Wan 2.2 video generation bridge
├── outputs/
│   ├── final/                          # 4 Master short film MP4s + .hash sidecars
│   ├── keyframes/                      # 10 Center-composed FLUX.2 Klein 4B PNGs
│   ├── music/                          # 48 kHz ACE-Step 1.5 master WAV + kaggle telemetry
│   ├── narration/                      # English narration WAVs per shot
│   ├── narration_am/                   # Amharic narration WAVs per shot
│   ├── narration_om/                   # Afaan Oromo narration WAVs per shot
│   ├── references/                     # Chosen character candidate portraits (v1, v1, v3)
│   ├── rough_cut/                      # Intermediate rough cuts (16:9 and 9:16)
│   └── shots/                          # 10 Video shot clips (24fps H.264)
├── pipeline/
│   ├── core.py                         # SHA-256 sidecar caching, atomic I/O, tenacity retry
│   ├── run.py                          # Unified CLI entry point (--language, --no-gpu)
│   ├── validate.py                     # Strict JSON Schema and business rule validation
│   ├── providers/
│   │   ├── cloudflare.py               # Cloudflare FLUX.2 Klein 4B image client
│   │   ├── gemini.py                   # Google Gemini text & TTS client with failover
│   │   └── kaggle_wan.py               # Kaggle Wan 2.2 and FFmpeg Ken Burns generator
│   └── stages/
│       ├── assemble.py                 # Ducking, loudnorm, dynamic tpad, master assembly
│       ├── keyframes.py                # Reference portraits & keyframe synthesis
│       ├── music.py                    # Score ingestion and ambient fallback bridge
│       ├── narration.py                # Multi-voice TTS & dynamic slot measurement
│       ├── script.py                   # 40-char wrapped subtitle and translation stage
│       └── shots.py                    # Video shot generation stage
├── schema/
│   └── storyboard.schema.json          # Strict JSON Schema definition
├── scripts/
│   ├── compute_costs.py                # Telemetry parser for runs.jsonl
│   ├── run_experiments.py              # Automated runner for EXP-05 through EXP-10
│   ├── smoke_test.py                   # Provider credential and health check
│   └── verify_localized.py             # ffprobe and volumedetect validation script
└── tests/
    ├── test_cache_retry.py             # Unit tests for hashing, atomic I/O, and retries
    └── test_validate.py                # Unit tests for schema and business rules
```

---

## 5. Cost Summary

| Metric | Measured Value |
|:---|:---:|
| **Total Operations Logged in `runs.jsonl`** | **676 operations** |
| **Cache Hit Rate** | **77.4%** (523 hits / 153 cold calls) |
| **Cumulative Measured Latency** | **4,501.61 seconds** (75.03 minutes) |
| **Actual Out-of-Pocket Expense** | **$0.00 USD** |
| **Commercial List-Price Equivalent** | **~$0.26 USD** |

*(For full per-stage breakdowns and provider telemetry, refer to [COSTS.md](file:///c:/Users/HP/Documents/the-story-that-was-passed-on/COSTS.md)).*

---

## 6. License & AI Model Attributions

- **Code & Pipeline**: Licensed under the [Apache 2.0 License](file:///c:/Users/HP/Documents/the-story-that-was-passed-on/LICENSE).
- **FLUX.2 Klein 4B**: Apache 2.0 (commercial permissible, zero non-commercial encumbrance).
- **Wan 2.2 TI2V-5B**: Apache 2.0.
- **ACE-Step 1.5-turbo**: MIT License.
- **Google Gemini 3.8 / 3.1 / 2.5**: Google AI Studio Terms of Service. No real-person likenesses or private personal data sent.
- **Ethics & Likeness**: Detailed character disclosures and provenance documentation available in [ETHICS.md](file:///c:/Users/HP/Documents/the-story-that-was-passed-on/ETHICS.md).

---

## Troubleshooting (Windows Specific)

If you are running this pipeline on Windows, you might encounter a few system-level security blocks. Here is how to bypass them:

**1. `python` is not recognized**
If `python -m venv .venv` fails, use the Windows Python launcher instead:
```powershell
py -m venv .venv
```
