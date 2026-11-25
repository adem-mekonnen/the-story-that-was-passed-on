# Final Submission Report: The Story That Was Passed On
**Course / Challenge**: AI-Content Generation Assignment (10 Academy TRP2)  
**Author**: Production Team  
**Repository**: [https://github.com/adem-mekonnen/the-story-that-was-passed-on.git](https://github.com/adem-mekonnen/the-story-that-was-passed-on.git)  

---

### Section 1: What I Set Out to Make

I set out to produce a 79-second cultural heritage short film titled *"The Story That Was Passed On"*, comprising exactly 76 seconds of narrative shots and a 3-second transparent AI disclosure end card (`DESIGN.md`, Section 3). The film addresses Ethiopian youth and diaspora families who seek emotional reconnection with intergenerational storytelling (`DESIGN.md`, Section 1). It portrays a fireside conversation between an elderly storyteller and his curious grandchild about why ancestral stories endure across generations, framing an ancient parable of community resilience during drought.

To serve both traditional cinematic viewing and mobile-first platforms (Instagram Reels, TikTok, YouTube Shorts), I architected the project to export dual aspect ratios: 16:9 widescreen (`outputs/final/heritage_short_horizontal_16x9.mp4`, 1920x1080) and 9:16 vertical (`outputs/final/heritage_short_vertical_9x16.mp4`, 1080x1920). My overarching engineering objective was establishing a contract-driven, deterministic, and fully reproducible pipeline where every visual cue, narration line, audio parameter, and shot duration is governed strictly by a single validated JSON file: `storyboard.json` (`schema/storyboard.schema.json`).

---

### Section 2: What My Audience Taught Me

Testing work-in-progress iterations with real listeners provided essential course corrections that transformed an initial mechanical draft into an emotionally engaging film (`DESIGN.md`, Section 4).

#### User Test #1 (Radio Cut Review)
I conducted User Test #1 on the audio-only "Radio Cut" (`outputs/radio_cut/radio_cut.mp4`) with three target reviewers:
1. **Muktar (Diaspora Youth Reviewer)**: Muktar noted that the opening felt disorienting without establishing the story context, and that the ending felt abrupt. In response, I prepended an explicit story title opening to `shot_01` (*"The Story That Was Passed On. In a quiet Ethiopian village..."*) and rewrote `shot_10` to deliver a stronger, memorable concluding takeaway (*"And so the lesson lived on: when a story is passed on, a generation carries it forward."*).
2. **Umer (Audio & Timing Reviewer)**: Umer criticized the rigid 8.0-second uniform shot cadence. In `shot_01`, the 7.92s spoken narration was cut off almost immediately by the visual cut (0.08s buffer), whereas shorter lines in shots 02 and 03 left 3 to 4 seconds of dead silence. In response, I dismantled uniform timing and instituted speech-matched pacing. `shot_01` was expanded first to 9.0s and subsequently to 10.0s after speech synthesis timing, resulting in the final calibrated duration array: `[10, 7, 6, 7, 8, 7, 8, 7, 8, 8]` seconds (`storyboard.json`).
3. **Miftah (Cultural Heritage Storyteller Reviewer)**: Miftah observed that relying on a single third-person voice (`Puck`) flattened the dialogue into a dry textbook reading, and noted that the synthetic placeholder drone lacked Ethiopian cultural identity. In response, I introduced per-shot voice overrides in `storyboard.json`: assigning `shot_03` to `Zephyr` (child) and `shot_09` to `Charon` (elder grandfather). I also replaced the synth drone with a genuine 72 BPM D minor acoustic score generated via ACE-Step 1.5 (`outputs/music/music_master_83s.wav`), incorporating traditional krar, masenqo, and washint motifs.

#### User Test #2 (Near-Final Cut Review)
- [TODO]
- Action taken because of Test #2: [TODO]

---

### Section 3: Hardest Problem and How I Solved It

The most difficult engineering hurdle was overcoming cloud GPU hardware constraints during video generation (`FAILURES.md`, Failure #11). 

I attempted to deploy the open-weight video diffusion model `Wan-AI/Wan2.2-TI2V-5B-Diffusers` on a Kaggle T4 cloud GPU instance (`notebooks/wan22_kaggle.ipynb`). However, Kaggle T4 instances provide only 16GB of host system RAM. When initializing diffusers with `enable_model_cpu_offload()` to stage the 5-billion-parameter model weights between system RAM and GPU VRAM, host memory consumption exceeded the physical 16GB ceiling, triggering the Linux kernel OOM killer (`Kernel died: Out of Memory`). Attempts to downscale the generation profile—reducing resolution to 640x384, dropping duration to 9 frames, and testing 4-bit quantization via `bitsandbytes`—failed due to precompiled CUDA container library incompatibilities.

**The Pivot**: Rather than halting production or introducing non-reproducible manual clips, I accepted the assignment-sanctioned fallback: programmatic FFmpeg Ken Burns camera motion (`pipeline/stages/shots.py`). Operating directly on 1280x704 center-composed FLUX.2 Klein 4B keyframes (`outputs/keyframes/`), the engine applies high-definition 24fps pans and zooms (`zoompan`). 

**Quality Trade-off**: I must honestly acknowledge the quality cost of this pivot. The final film features smooth, disciplined camera movement and framing rather than dynamic, full-body character and cloth physics. However, it achieved 100% CPU reproducibility, allowing any evaluator to clone the repository and assemble the film in under 30 seconds without hardware dependency (`README.md`).

Simultaneously, I resolved cloud music synthesis limitations (`FAILURES.md`, Failure #10). Google Colab upgraded its default environment to Python 3.13, which broke `ace-step` dependencies (`requires-python <3.13,>=3.11`), and free Colab runtimes denied GPU access. I solved this by migrating to Kaggle T4, using `uv` to instantiate an isolated Python 3.11 runtime, and successfully generated our 48kHz stereo master score (`outputs/music/music_master_83s.wav`, seeds 8301/8302) in 10.9 seconds of GPU compute.

---

### Section 4: Suggested Practices Tested Honestly

- **One practice that beat my instinct:** [TODO]
- **One practice that did not:** [TODO]

---

### Section 5: Ceiling Work (Multilingual Localization)

For my ceiling exploration, I upgraded beyond short audio snippets to synthesize complete, standalone localized 9:16 vertical motion pictures for **Amharic (`am`)** and **Afaan Oromo (`om`)** using the `--language` CLI flag (`EXPERIMENTS.md`, `EXP-10`).

```bash
python -m pipeline.run --no-gpu --language am
python -m pipeline.run --no-gpu --language om
```

This produced two full video masters: `outputs/final/heritage_short_am_9x16.mp4` (80.90s, 23.92 MB) and `outputs/final/heritage_short_om_9x16.mp4` (80.10s, 23.74 MB), leaving the English master cuts untouched.

**Linguistic & Timing Findings (`EXP-10`)**:
1. **Translation Accuracy**: In the automated LLM translation step (`gemini-2.5-flash`), the system initially translated "Grandfather" into Afaan Oromo as *"Akkoo"* (grandmother) instead of the accurate term *"Akaakayyuu"*, and generated repetitive phrases (*"sana sana"*). I caught this in audit and amended the system prompt with strict cultural lexicon instructions.
2. **Agglutinative Speech Expansion**: Regional oral cadences expanded beyond the English storyboard timing slots. In Afaan Oromo, `shot_01` speech expanded to 10.26s (overrunning the 10.0s slot), and `shot_06` expanded to 7.15s (overrunning 7.0s). In Amharic, elder dialogue in `shot_08` expanded to 7.56s (overrunning 7.0s) and `shot_09` reached 8.66s (overrunning 8.0s).
3. **Dynamic Frame Clamping**: To avoid cutting off spoken words without distorting playback pitch, I implemented dynamic slot expansion in `assemble.py` using FFmpeg `tpad=stop_mode=clone:stop=-1 -t {effective_slot}`. This freezes the final keyframe cleanly until speech concludes.
4. **Native Speaker Assessment**: Formal community rating status is currently **pending** (`EXPERIMENTS.md`, `EXP-10`).

---

### Section 6: Limitations and Next Steps

To maintain strict academic honesty, I document the following project limitations:
1. **Motion Model Limitation**: The final visual delivery relies entirely on FFmpeg Ken Burns camera motion (`shots.py`). Because Kaggle T4 system RAM limits prevented Wan 2.2 model offload, zero AI video diffusion clips were logged in `runs.jsonl`.
2. **Absence of Frontier Benchmarks**: As documented in `COSTS.md` (Section 6), commercial frontier models (such as Google DeepMind Lyria 3.5 audio, Gemini Omni video, or Runway Gen-3 Alpha) were omitted. Cohort billing credentials for paid cloud APIs were unavailable, and the architecture intentionally prioritized zero-cost reproducibility ($0.00 out-of-pocket spend).
3. **Linguistic Verification**: While Amharic and Afaan Oromo texts were generated with cultural guardrails and render cleanly with Ebrima typography (`outputs/experiments/am_subtitle_check.png`), full native-speaker field evaluation remains pending.

**Next Steps**:
My immediate post-challenge goal is developing a lightweight web interface where diaspora families can submit written generational memories. The application will validate the input against `storyboard.schema.json`, automatically steer local keyframe and TTS engines, and output customized, localized heritage shorts to keep ancestral stories alive.
