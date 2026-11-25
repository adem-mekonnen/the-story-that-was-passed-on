# Production Design & Audience Specification

"The Story That Was Passed On" — A 79-second heritage short film designed for mobile-first storytelling and diaspora connection.

---

## 1. Audience & Intent

### Target Audience
1. **Ethiopian Youth & Diaspora Families**: Second-generation and diaspora youth seeking emotional and cultural reconnection to ancestral storytelling traditions.
2. **Mobile Social Viewers**: Audiences on Instagram Reels, TikTok, and YouTube Shorts engaging with vertical video formats in sound-on or sound-off environments.

### Core Intent
To demonstrate that cultural wisdom transcends time: what matters is not *when* a story took place, but *what* it imparts to the next generation. The film uses an intimate fireside framing story to contextualize an ancient parable of community planting and resilience.

---

## 2. Language Choice & Accessibility

- **Primary Audio**: English (`en`). Selected to maximize reach and emotional comprehension among diaspora youth and international audiences who may have limited Amharic fluency.
- **Subtitles**: English (`en`). Burned-in, mobile-optimized subtitles ensuring full clarity for sound-off mobile scrolling and hard-of-hearing viewers.
- **Multilingual Localization (Completed)**: Amharic and Afaan Oromo completed (see `content/am` and `content/om`). Full localized 80s cuts with burned subtitles are generated via `--language am` and `--language om`.

---

## 3. 10-Shot Purpose & Story Structure

The short is structured across 10 narration-paced shots (76 seconds total) plus a 3-second end card (79 seconds total):

| Shot ID | Duration | Camera Shot | Purpose | Voice | Narration |
|---|---|---|---|---|---|
| `shot_01` | 10s | Wide establishing shot | Establish setting: Ethiopian highland village at sunset | Puck (Narrator) | *"The Story That Was Passed On. In a quiet Ethiopian village, an elderly man carried many stories in his heart."* |
| `shot_02` | 7s | Medium two-shot | Introduce characters: Elder and Child by evening hearth | Puck (Narrator) | *"One evening, as the sun set, the child asked him a question."* |
| `shot_03` | 6s | Close-up | Present central inquiry from the curious child | Zephyr (Child) | *"Grandfather, why do you always tell us the same old stories?"* |
| `shot_04` | 7s | Close-up | Elder smiles and begins the embedded parable | Puck (Narrator) | *"The elder smiled, and began telling a story about their village."* |
| `shot_05` | 8s | Wide shot | Introduce conflict: historic harsh dry season | Puck (Narrator) | *"Years ago, a harsh dry season came to the land, and people began to worry."* |
| `shot_06` | 7s | Medium shot | Act of kindness: child shares bread with frail neighbour | Puck (Narrator) | *"Yet one child shared the little food they had with a struggling neighbour."* |
| `shot_07` | 8s | Macro close-up | Turning point: neighbour gifts single heirloom seed | Puck (Narrator) | *"In return, the neighbour gave the child a single seed saved for planting."* |
| `shot_08` | 7s | Medium wide shot | Resolution of parable: village plants and grows the seed | Puck (Narrator) | *"Together, the village planted that seed, watered it, and watched it grow."* |
| `shot_09` | 8s | Medium close-up | Deliver moral: significance of living heritage | Charon (Elder) | *"My child, what matters is not when a story happened, but what it teaches us."* |
| `shot_10` | 8s | Wide pull-back shot | Emotional resolution: generation carries the story forward | Puck (Narrator) | *"And so the lesson lived on: when a story is passed on, a generation carries it forward."* |
| `end_card` | 3s | Static card | AI transparency and authorship disclosure | — | *"Created with AI-assisted tools. Story and production by the creator."* |

---

## 4. User Testing & Feedback

To uphold the core design principle of zero fabricated data, feedback logs record verified reviews and the direct architectural changes implemented in response.

### User Test #1 (Radio Cut Review)
Conducted with 3 real listeners representing diaspora youth, sound design, and cultural storytelling:

1. **Muktar (Diaspora Youth Reviewer)**:
   - *Verbatim / Observation*: Noted that the opening felt abrupt without knowing the context or title of the story, and the final sentence concluded too quickly without a strong, memorable moral takeaway to carry into daily life.
   - *Reviewer Feedback*: *"Give it an explicit title opening so we know what story we are entering, and finish with a stronger moral sentence so the takeaway resonates."*
   - *Architectural Action Taken*:
     - Prepended the story title to `shot_01`: `"The Story That Was Passed On. In a quiet Ethiopian village, an elderly man carried many stories in his heart."`
     - Rewrote `shot_10` concluding narration: `"And so the lesson lived on: when a story is passed on, a generation carries it forward."`

2. **Umer (Audio & Timing Reviewer)**:
   - *Verbatim / Observation*: Critiqued the uniform 8.0s per shot cadence. `shot_01` had a 7.92s TTS duration inside an 8.0s slot (leaving a breathless 0.08s before a harsh cut), while shorter 4.7s–5.5s lines (shots 02, 03, 04) created awkward 3–4 second dead air gaps, followed by an excessive 6-second silent tail at the end of the cut.
   - *Reviewer Feedback*: *"Cut down the dead silence between sentences. The narrator feels like he's waiting around on short lines, and the first line barely finishes before the scene cuts. Match each shot's duration to the actual length of the spoken phrase."*
   - *Architectural Action Taken*:
     - Replaced uniform 8.0s slots with speech-matched dynamic pacing across the 10 shots: `[9, 7, 6, 7, 8, 7, 8, 7, 8, 8]` (75s shots + 3s end card = 78s total).
     - Expanded `shot_01` to 9s (comfortable buffer after the title), and tightened short dialogue shots (shots 02, 03, 04, 06, 08) to 6s–7s, eliminating dead pauses while preserving natural contemplative rhythm.

3. **Miftah (Cultural Heritage Storyteller Reviewer)**:
   - *Verbatim / Observation*: Pointed out that a single third-person narrator voice (`Puck`) across all shots flattened the dialogue, making the exchange between the curious child and wise grandfather feel like a single person reading a textbook rather than a genuine intergenerational dialogue. Also noted the initial synth drone lacked Ethiopian soul, recommending traditional instruments (krar, washint, masenqo) and localized language benchmarking (Amharic/Oromo).
   - *Reviewer Feedback*: *"The child's question and the elder's response sound like a narrator reading a book rather than people speaking to each other. Give the child a younger voice and the grandfather an elderly warmth. Also, traditional krar/washint strings are essential, and eventually hearing this in Amharic or Afaan Oromoo would be the ultimate ceiling."*
   - *Architectural Action Taken*:
     - Introduced per-shot `voice` and `tts_style` overrides in `storyboard.schema.json` and `pipeline/stages/narration.py`. Assigned `shot_03` to `voice: "Zephyr"` (`tts_style: "curious young child asking a heartfelt question, natural and gentle"`) and `shot_09` to `voice: "Charon"` (`tts_style: "warm wise elderly grandfather speaking gently, unhurried"`), reserving `Puck` for third-person narrator shots.
     - Resolved the acoustic instrumentation note by replacing the placeholder synth drone with our genuine `ACE-Step 1.5` score (72 BPM, D minor, acoustic krar, masenqo, and washint).
     - Documented the Amharic and Afaan Oromoo multilingual ceiling benchmark as `EXP-10` in our research roadmap.
