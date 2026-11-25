# Ethics, Provenance & AI Governance

"The Story That Was Passed On" is an 83-second cultural heritage short film created for the 10 Academy TRP2 challenge. This document outlines the ethical principles, asset provenance, licensing compliance, and disclosure standards applied throughout production.

---

## 1. Fictional Character Composites & Identity Protection

All characters depicted in this film are **100% fictional composite characters**. No likeness, portraiture, biometric data, or voice clone of any living or deceased individual was utilized.

- **`elder_01` ("The Elder")**: A fictional elderly Ethiopian storyteller (approx. 70 years old), created as a visual archetype of village elders and traditional storytellers.
- **`child_01` ("The Child")**: A fictional Ethiopian child (approx. 10 years old), representing curious youth in the diaspora and rural communities.
- **`neighbour_01` ("The Neighbour")**: A fictional elderly villager, symbolizing community resilience and generosity during dry seasons.

**Voice & likeness policy**:
- Voiceover is synthesized exclusively using synthetic base voices provided through Gemini TTS (`voice: "Puck"`, directed via stylistic prompt metadata). No personal voice recordings or cloned voices of family members or actors were used.
- Character visuals were generated purely from text prompts and stylistic descriptors ("Ethiopian heritage realism, 35mm film aesthetic") without referencing private individuals.

---

## 2. Model Licensing & Commercial Permissibility

Every generative model incorporated in this pipeline was vetted for open, commercially permissible licensing:

| Stage | Model / Service | License / Terms | Architectural Rationale |
|---|---|---|---|
| **Keyframes / Image** | `@cf/black-forest-labs/flux-2-klein-4b` via Cloudflare Workers AI | **Apache 2.0** | Fully open and commercially usable. Deliberately chose the 4B Klein variant over 9B non-commercial variants to guarantee open licensing and rapid inference. |
| **Video Shots** | `Wan 2.2 TI2V-5B` (Text/Image-to-Video) | **Apache 2.0** | Open weight model under Apache 2.0, providing high-fidelity video generation without proprietary lock-in. |
| **Heritage Music** | `ACE-Step 1.5` | **MIT License** | Open-source music synthesis model permissible for commercial, research, and creative media use. |
| **Script & Narration** | `Gemini 3.8 Flash` & `Gemini 3.8 Flash TTS` via Google AI Studio | **Google AI Studio Terms** | Cloud API used within standard terms. Strictly non-private, fictional creative text submitted; zero proprietary or personal family data transmitted. |

---

## 3. Provenance Retention & Auditability

To prevent non-reproducible "hallucinated" outputs and ensure absolute auditability:
1. **Deterministic Input Hashes**: Every asset generation calculates a deterministic SHA-256 hash (`sha256_inputs`) over prompt, seed, model, parameters, and referenced assets, saved in a persistent `.hash` sidecar file.
2. **Immutable Telemetry**: All model calls append an immutable JSON line to `runs.jsonl` recording:
   - `run_id`, `stage`, `shot_id`, `provider`, `model`, `seed`, `parameters`, `input_hash`, `output`, `latency_seconds`, `cost_usd`, `cache_hit`, `status`, and `timestamp`.
3. **Atomic File I/O**: Outputs are written via atomic temporary replacement (`.tmp` -> rename), preventing partial writes or corrupted media states.

---

## 4. AI Disclosure & End-Card Transparency

In accordance with responsible AI practices and challenge guidelines, AI usage is disclosed both within the media container and on public channels:

1. **3-Second End Card**:
   - Duration: 3.0 seconds (timestamp 80.0s to 83.0s).
   - Text: `"Created with AI-assisted tools. Story and production by the creator."`
   - Background: Solid black with clean typography.
2. **Platform & Social Disclosure**:
   - Any distribution of the final film will include explicit tags (`#AIContent`, `#AIArt`, `Generated with AI`) and full descriptions crediting the pipeline architecture, models used, and creative authorship.
