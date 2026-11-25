# Cost & Telemetry Ledger: The Story That Was Passed On

This document presents the complete, verified cost and telemetry ledger computed directly from the 676 structured entries in [runs.jsonl](file:///c:/Users/HP/Documents/the-story-that-was-passed-on/runs.jsonl) and Kaggle GPU execution logs.

---

## 1. Executive Summary

- **Total Pipeline Operations Logged**: 676 operations
- **Cache Hits**: 523 operations (**77.4% overall cache hit rate**)
- **Cold Computations**: 153 operations
- **Cumulative Measured Latency**: 4,501.61 seconds (**75.03 minutes**)
- **Actual Out-of-Pocket Expense**: **$0.00 USD** (100% covered by free-tier quotas)
- **Estimated Commercial List-Price Equivalent**: **$0.26 USD**

---

## 2. Operation & Cache Telemetry by Stage

Data computed directly from `runs.jsonl`:

| Stage | Total Calls | Cache Hits | Hit Rate | Cold Calls | Measured Latency | Providers / Engines |
|:---|:---:|:---:|:---:|:---:|:---:|:---|
| `assemble` | 11 | 3 | 27.3% | 8 | 2,628.00s | `ffmpeg` (master mux, 2-pass loudnorm) |
| `experiments` | 18 | 0 | 0.0% | 18 | 82.89s | `cloudflare`, `gemini`, `ffmpeg`, `local` |
| `keyframes` | 131 | 117 | **89.3%** | 14 | 127.47s | `cloudflare` (FLUX.2 Klein 4B) |
| `music` | 14 | 10 | **71.4%** | 4 | 11.88s | `kaggle_t4` (ACE-Step 1.5), `ffmpeg_fallback` |
| `narration` | 190 | 156 | **82.1%** | 34 | 689.12s | `gemini` (Gemini 3.8 & 3.1 Flash TTS) |
| `references` | 135 | 126 | **93.3%** | 9 | 84.95s | `cloudflare` (FLUX.2 Klein 4B portraits) |
| `script` | 21 | 12 | **57.1%** | 9 | 0.04s | `local` (textwrap, cumulative SRT timing) |
| `shots` | 120 | 99 | **82.5%** | 21 | 59.42s | `ffmpeg_kenburns` (24fps camera choreography) |
| `smoke_test` | 36 | 0 | 0.0% | 36 | 817.84s | `cloudflare`, `gemini` (baseline verification) |
| **TOTAL** | **676** | **523** | **77.4%** | **153** | **4,501.61s** | |

---

## 3. Telemetry by Compute Provider

| Provider | Operations | Cache Hits | Hit Rate | Cold Calls | Measured Latency | Model / Tool Identifiers |
|:---|:---:|:---:|:---:|:---:|:---:|:---|
| `cloudflare` | 279 | 243 | **87.1%** | 36 | 338.93s | `@cf/black-forest-labs/flux-2-klein-4b` |
| `gemini` | 222 | 156 | **70.3%** | 66 | 1,459.44s | `gemini-3.8-flash`, `gemini-2.5-flash`, `gemini-3.8-flash-tts`, `gemini-3.1-flash-tts-preview` |
| `ffmpeg` | 11 | 3 | 27.3% | 8 | 2,628.00s | `h264_aac_loudnorm`, `master_mux` |
| `ffmpeg_kenburns` | 120 | 99 | **82.5%** | 21 | 59.42s | `zoompan` (24fps Ken Burns camera choreography) |
| `kaggle_t4` | 8 | 5 | **62.5%** | 3 | 10.91s | `ACE-Step-1.5`, `ACE-Step-1.5-turbo` |
| `ffmpeg_fallback` | 6 | 5 | 83.3% | 1 | 0.97s | `ACE-Step-1.5` hash verify, `aevalsrc` chord pad |
| `local` | 21 | 12 | 57.1% | 9 | 0.04s | `textwrap_srt` (SRT generation) |
| `local_experiments` | 9 | 0 | 0.0% | 9 | 3.90s | `ffmpeg_sidechaincompress`, `ffmpeg_volumedetect`, `local_libass`, `local_telemetry` |
| **TOTAL** | **676** | **523** | **77.4%** | **153** | **4,501.61s** | |

---

## 4. Kaggle T4 GPU Telemetry

Logged in [outputs/music/kaggle_runs.jsonl](file:///c:/Users/HP/Documents/the-story-that-was-passed-on/outputs/music/kaggle_runs.jsonl):

- **ACE-Step 1.5 Music Generation**:
  - `music_partA_8301`: Part A (seed 8301, 43s) -> Latency: **6.986s** (Status: `success`)
  - `music_partB_8302`: Part B (seed 8302, 43s) -> Latency: **3.929s** (Status: `success`)
  - **Total Active Audio Synthesis GPU Time**: **10.915 seconds**
- **Wan 2.2 TI2V-5B Exploration**:
  - Two initialization attempts on Kaggle standard environment (~15 minutes total GPU runtime) before Linux kernel OOM killer terminated the process at $>30\text{ GB}$ system RAM allocation (Failure #11 in [FAILURES.md](file:///c:/Users/HP/Documents/the-story-that-was-passed-on/FAILURES.md)).
  - Bypassed without financial cost under Kaggle's 30 free GPU hours/week allowance.

---

## 5. Commercial List-Price USD Valuation

While our actual out-of-pocket expenditure was **$0.00**, standard public cloud developer pricing yields the following list-price valuation:

| Resource / Stage | Units Consumed | Commercial Rate | List-Price Equivalent | Actual Paid |
|:---|:---:|:---:|:---:|:---:|
| **Gemini Text Generation** (Scripting, translations) | ~25k input / ~3k output tokens | $0.075 / 1M in, $0.30 / 1M out | $0.003 | **$0.00** (Free Tier) |
| **Gemini TTS Synthesis** (3 languages x 10 shots) | 40 cold calls (~4,000 characters) | $0.015 / 1,000 characters | $0.060 | **$0.00** (Free Tier) |
| **Cloudflare Workers AI** (FLUX.2 Klein 4B) | 36 cold calls (~9,000 Neurons) | $0.011 / 1,000 Neurons | $0.099 | **$0.00** (10k Free Daily Neurons) |
| **Kaggle T4 GPU Compute** (Music & Wan exploration) | ~0.25 GPU-hours | $0.40 / T4 GPU-hour | $0.100 | **$0.00** (30h Free Weekly GPU) |
| **Local CPU & Storage** (FFmpeg, assembly) | ~75 minutes compute | Workstation hardware | $0.000 | **$0.00** |
| **TOTAL** | | | **~$0.26 USD** | **$0.00 USD** |

---

## 6. Frontier Model Omission Note

In accordance with strict zero-fabrication principles, this repository does not include comparative evaluation benchmarks against proprietary frontier models (e.g. Google DeepMind Lyria 3.5, Gemini Omni Flash video, or Runway Gen-3 Alpha):
1. **Access Restrictions**: Cohort access keys or paid Google Cloud project billing accounts for non-public preview endpoints were not available in this challenge environment.
2. **Reproducibility Guarantee**: The entire pipeline was deliberately architected to run on open-access, zero-cost endpoints (Cloudflare Workers AI free tier, Google AI Studio free tier, Kaggle T4, and local CPU FFmpeg). This ensures any stranger or evaluator can clone the repository and reproduce identical assets without entering a credit card or incurring API charges.
