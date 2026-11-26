# Final Submission Report: The Story That Was Passed On
**Course / Challenge**: AI-Content Generation Assignment (10 Academy TRP2)  
**Author**: Adem Mekonnen  
**Repository**: [https://github.com/adem-mekonnen/the-story-that-was-passed-on.git](https://github.com/adem-mekonnen/the-story-that-was-passed-on.git)  

---

### Section 1: What I Set Out to Make

I set out to produce a 79-second cultural heritage short film titled *"The Story That Was Passed On"*, consisting of 76 seconds of narrative shots and a 3-second transparent AI disclosure end card (`DESIGN.md`, Section 3). The film addresses Ethiopian youth and diaspora families seeking emotional reconnection with ancestral storytelling (`DESIGN.md`, Section 1). It portrays a fireside dialogue between an elderly storyteller and his curious grandchild about why ancestral stories endure, framing an ancient parable of community planting and resilience during drought.

To serve both traditional cinematic viewing and mobile platforms (Instagram Reels, TikTok, YouTube Shorts), I exported dual aspect ratios: 16:9 widescreen (`outputs/final/heritage_short_horizontal_16x9.mp4`, 1920x1080) and 9:16 vertical (`outputs/final/heritage_short_vertical_9x16.mp4`, 1080x1920). The core engineering objective was building a contract-driven, deterministic, reproducible pipeline governed entirely by a single validated JSON file: `storyboard.json` (`schema/storyboard.schema.json`).

---

### Section 2: What My Audience Taught Me

Testing work-in-progress iterations with real listeners provided essential course corrections that transformed a mechanical draft into an emotionally engaging film (`DESIGN.md`, Section 4).

#### User Test #1 (Radio Cut Review)
I conducted User Test #1 on the audio-only cut (`outputs/radio_cut/radio_cut.mp4`) with three target reviewers:
1. **Muktar (Diaspora Youth Reviewer)**: Found the opening disorienting without story context and the ending abrupt. In response, I prepended an explicit title opening to `shot_01` (*"The Story That Was Passed On. In a quiet Ethiopian village..."*) and rewrote `shot_10` to deliver a stronger moral takeaway (*"And so the lesson lived on: when a story is passed on, a generation carries it forward."*).
2. **Umer (Audio & Timing Reviewer)**: Criticized the uniform 8.0-second cadence. In `shot_01`, 7.92s of speech was cut off by the visual cut (0.08s buffer), while shorter lines in shots 02 and 03 left 3–4 seconds of dead silence. In response, I instituted speech-matched pacing. `shot_01` was raised first to 9.0s and then to 10.0s after TTS timing, establishing the calibrated duration array: `[10, 7, 6, 7, 8, 7, 8, 7, 8, 8]` seconds (`storyboard.json`).
3. **Miftah (Cultural Heritage Storyteller Reviewer)**: Noted a single narrator voice (`Puck`) flattened dialogue into a textbook readout, and observed the synthetic drone lacked Ethiopian identity. In response, I added per-shot voice overrides in `storyboard.json`: assigning `shot_03` to `Zephyr` (child) and `shot_09` to `Charon` (elder). I also replaced the synth drone with a genuine 72 BPM D minor acoustic score via ACE-Step 1.5 (`outputs/music/music_master_83s.wav`), featuring traditional krar, masenqo, and washint.

#### User Test #2 (Near-Final Cut Review)
I conducted User Test #2 with 3 real mobile-phone viewers reviewing the near-final 9:16 vertical cut (`DESIGN.md`, Section 4):
1. **Ahmed**: *"The images for the grandfather should look authentically Ethiopian—dark-skinned/Black, not light-skinned/white."* (Original note: *"the images for the grandfather is should be looks ethiopian culture which is black not white"*).
2. **Hawa**: Evaluated the Afaan Oromo localized cut as a native speaker: *"The Afaan Oromo subtitle is correct, but the pronunciation is not native."* (Original note: *"the afan oromio subttile is correct but the pronunce is not native"*).
3. **Osman**: *"Include more authentic Ethiopian culture in the images and make the narration sound native across all three languages."* (Original note: *"include the ethiopian culture on the images and make native for the three language"*).

**Actions & Decisions Taken**:
I logged Hawa's native-speaker evaluation of Afaan Oromo TTS pronunciation as a verified low-resource model limitation in `EXPERIMENTS.md` (`EXP-10`) and `FAILURES.md` (Failure #13), recorded Ahmed and Osman's cultural-representation and skin-tone prompt constraints for v2 visual iteration, and confirmed the 79s English master cut ready for delivery (`DESIGN.md`, Section 4).

---

### Section 3: Hardest Problem and How I Solved It

The most difficult engineering hurdle was overcoming cloud GPU hardware constraints during video generation (`FAILURES.md`, Failure #11). 

I attempted to deploy `Wan-AI/Wan2.2-TI2V-5B-Diffusers` on a Kaggle T4 GPU instance (`notebooks/wan22_kaggle.ipynb`). However, Kaggle T4 instances provide only 16GB of host system RAM. When initializing diffusers with `enable_model_cpu_offload()` to stage the 5-billion-parameter model weights, host memory consumption exceeded the physical 16GB ceiling, triggering the Linux kernel OOM killer (`Kernel died: Out of Memory`). Reducing resolution to 640x384 at 9 frames and testing 4-bit quantization via `bitsandbytes` failed due to precompiled CUDA library incompatibilities.

**The Pivot**: Rather than halting production, I accepted the assignment-sanctioned fallback: programmatic FFmpeg Ken Burns camera motion (`pipeline/stages/shots.py`). Operating directly on 1280x704 center-composed FLUX.2 Klein 4B keyframes (`outputs/keyframes/`), the engine renders smooth 24fps pans and zooms (`zoompan`). 

**Quality Trade-off**: The final film features disciplined camera choreography rather than full character animation. However, it achieved 100% CPU reproducibility, allowing any evaluator to clone the repo and assemble the film in under 30 seconds without hardware dependency (`README.md`).

Simultaneously, I resolved music synthesis limits (`FAILURES.md`, Failure #10). Colab's upgrade to Python 3.13 broke `ace-step` (`requires-python <3.13,>=3.11`), and free Colab lacked GPU. I solved this by migrating to Kaggle T4, using `uv` to instantiate an isolated Python 3.11 runtime, generating our 48kHz score (`outputs/music/music_master_83s.wav`, seeds 8301/8302) in 10.9 seconds of GPU compute.

---

### Section 4: Suggested Practices Tested Honestly

- **One practice that beat my instinct**: Generating curated character reference sheets before keyframe synthesis (`EXPERIMENTS.md`, `EXP-01` and `EXP-02`). My initial instinct was that detailed descriptive text prompts alone would provide sufficient visual continuity. However, our ablation test on `shot_02` proved this wrong: the unconditioned text-only image (`outputs/experiments/shot_02_noref.png`, input hash `a8356da7...`) drifted severely in facial structure, clothing, and age (rendering an older teen rather than a 10-year-old child). In contrast, attaching in-memory resized (<512px) reference portraits (`outputs/keyframes/shot_02.png`, input hash `83decab8...`) locked character identities, preserving the elder's white cotton `gabi` folds and the child's facial symmetry across shots.
- **One practice that did not**: Applying character reference conditioning uniformly across all shots, and attempting heavy video diffusion offloading on free cloud GPUs. Blindly passing character references caused severe visual leakage in `shot_07` (`FAILURES.md`, Failure #5), where full character portraits hallucinated into an extreme macro insert of elderly hands placing seeds, forcing us to explicitly clear `character_refs` for insert and landscape shots. Furthermore, attempting to run `Wan 2.2 TI2V-5B` with `enable_model_cpu_offload()` on free Kaggle T4 GPUs failed completely (`FAILURES.md`, Failure #11), exhausting the 16 GB host RAM ceiling even at 640x384 / 9 frames. Pivoting to deterministic FFmpeg Ken Burns camera motion proved far superior for reliability, keeping the pipeline 100% CPU-reproducible.

---

### Section 5: Ceiling Work (Multilingual Localization)

For my ceiling exploration, I upgraded beyond short audio snippets to synthesize complete localized 9:16 vertical motion pictures for **Amharic (`am`)** and **Afaan Oromo (`om`)** using `--language` (`EXPERIMENTS.md`, `EXP-10`):

```bash
python -m pipeline.run --no-gpu --language am
python -m pipeline.run --no-gpu --language om
```

This produced two full video masters: `outputs/final/heritage_short_am_9x16.mp4` (80.90s, 23.92 MB) and `outputs/final/heritage_short_om_9x16.mp4` (80.10s, 23.74 MB), leaving English masters untouched.

**Linguistic & Timing Findings (`EXP-10`)**:
1. **Translation Accuracy**: In automated translation (`gemini-2.5-flash`), the model initially translated "Grandfather" into Afaan Oromo as *"Akkoo"* (grandmother) instead of *"Akaakayyuu"*, and generated repetitive phrases (*"sana sana"*). I caught this in audit and amended system prompts with strict cultural lexicon instructions.
2. **Agglutinative Speech Expansion**: Regional oral cadences expanded beyond English timing slots. In Afaan Oromo, `shot_01` speech expanded to 10.26s (overrunning the 10.0s slot) and `shot_06` reached 7.15s (overrunning 7.0s). In Amharic, elder dialogue in `shot_08` expanded to 7.56s (overrunning 7.0s) and `shot_09` reached 8.66s (overrunning 8.0s).
3. **Dynamic Frame Clamping**: To prevent cutting off spoken words, I implemented dynamic slot expansion in `assemble.py` using FFmpeg `tpad=stop_mode=clone:stop=-1 -t {effective_slot}`, freezing the final keyframe until speech concludes.
4. **Native Speaker Assessment**: In User Test #2, native reviewer Hawa validated that Afaan Oromo subtitles were grammatically correct across all 10 shots, but identified that Gemini TTS speech sounded non-native/accented (`EXPERIMENTS.md`, `EXP-10`; `FAILURES.md`, Failure #13). Formal native-speaker assessment for the Amharic cut remains ongoing.

---

### Section 6: Limitations and Next Steps

To maintain strict academic honesty, I document the following project limitations:
1. **Motion Model Limitation**: Visual delivery relies entirely on FFmpeg Ken Burns motion (`shots.py`). Because Kaggle T4 system RAM limits prevented Wan 2.2 model offload, zero AI video diffusion clips were logged in `runs.jsonl`.
2. **Absence of Frontier Benchmarks**: As documented in `COSTS.md` (Section 6), commercial frontier models (Google DeepMind Lyria 3.5, Gemini Omni video, Runway Gen-3) were omitted due to billing access restrictions, prioritizing zero-cost reproducibility ($0.00 out-of-pocket spend).
3. **Linguistic Verification**: While Afaan Oromo subtitles were verified accurate by native reviewer Hawa in User Test #2 (with non-native TTS pronunciation noted as a model limitation), formal native-speaker field evaluation for the Amharic cut remains ongoing.

**Next Steps**:  
My immediate post-challenge goal is developing a lightweight web interface where diaspora families can submit written generational memories. The application will validate input against `storyboard.schema.json`, steer local keyframe and TTS engines, and output customized, localized heritage shorts to keep ancestral stories alive.