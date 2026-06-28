# UI Redesign Phase 2 — Project Modes + Language Metadata — Design

**Date:** 2026-06-28
**Status:** Approved (user reviews all phases together after implementation)
**Part of:** the 3-phase UI redesign. Phase 2 of 3.
**Builds on:** Phase 1 (the 3-column shell). **Followed by:** Phase 3 (adaptive samples).

## Problem / goal

The app can produce **both** simple single-voice narration and multi-speaker podcasts on **every** engine (the backend splits multi-speaker scripts per line and synthesizes each separately, regardless of `max_speakers`). So the editor style should be a **user-chosen project type**, not derived from the engine.

Phase 2 adds:
1. A persisted **project mode**: **Text-to-Voice** (single big textarea) or **Podcast** (speaker roster + segments). Both work with all engines.
2. A first-run / new-project **mode chooser** in the middle column; the choice persists to `localStorage` and is restored on relaunch (no chooser shown when a saved mode exists).
3. A **mode toggle** (`Text-to-Voice | Podcast`) at the top of the middle column to switch later; each mode keeps its **own content buffer** (switching never loses the other mode's work).
4. The Text-to-Voice view: a large textarea with live **character / word / estimated-duration** counts and a **language dropdown** when the active engine supports languages.
5. Backend **`languages` metadata** per engine so the language dropdown is data-driven.

## Hard constraints

- **Structural/additive only** — keep the existing design language. New controls reuse existing Tailwind tokens and component styling.
- **Playwright verification after the phase.**

## Project-mode model

- Modes: `"tts"` (Text-to-Voice) and `"podcast"`.
- **Separate buffers.** Store holds both a TTS buffer and the existing podcast project simultaneously:
  - `ttsBuffer: { text: string; voiceId: string | null; language: string | null }`
  - `podcast`: the current `{ segments, speakers }` (today's state, unchanged).
  - `mode: "tts" | "podcast"` — the active view.
- **Persistence (`localStorage`):** `vs.mode` (last mode), `vs.tts` (the TTS buffer). The podcast project already persists via the existing store mechanism (if any); if it does not persist today, this phase does NOT add podcast persistence (out of scope) — only `mode` and the TTS buffer persist. On launch: read `vs.mode`; if present, open that mode directly; else show the chooser.
- **Switching** flips `mode` and swaps the middle view; both buffers stay in memory and in `localStorage`. No flatten/merge.

## Middle-column views

### Mode chooser (empty/first-run state)

Shown when `vs.mode` is unset. Two large cards in the middle column, styled like existing panels (rounded, zinc surface, teal accent on hover):
- **Text-to-Voice** — "Type or paste text and generate with a single voice."
- **Podcast** — "Build a multi-speaker conversation from segments."
Selecting a card sets `mode`, persists it, and renders that editor. A small `Text-to-Voice | Podcast` segmented toggle also appears at the top of the middle toolbar thereafter, so the user can switch (and re-reach the other mode).

### Podcast view

Exactly the Phase 1 middle column: `SpeakerRoster` + segment cards + inline player + the existing `Generate All` / `Add Segment` toolbar actions and `Samples`.

### Text-to-Voice view (`TtsEditor`, new)

- A single large **textarea** bound to `ttsBuffer.text` (styled like the segment text box, just taller).
- A **counts row** under it: `N chars · M words · ~Ss`. Word count splits on whitespace; duration estimate uses **~2.5 words/sec (≈150 wpm)**: `ceil(words / 2.5)` seconds, shown as `~12s` / `~1m 04s`.
- The **active voice** is the flat picker: the voice currently selected in the left `VoiceLibrary`. Phase 2 adds a lightweight "selected voice" highlight + an `onSelectVoice` to `VoiceLibrary`, and the store gains `ttsBuffer.voiceId`. For cloning engines the selected voice is the reference; for OmniVoice, design/auto modes are **out of scope here** (TTS uses clone with the selected voice, mirroring today's default) — OmniVoice design/auto stays a podcast-roster feature.
- A **language dropdown** appears only when the active engine reports `languages` (see below).
- The toolbar's `Generate All` becomes a single **Generate** action in TTS mode (one call with the active voice). `Samples` loads a simple-text sample (Phase 3). Player plays the single result.

## Language metadata (backend) + dropdown (frontend)

### Backend

- Add a `languages: list[dict]` to each engine's `info()` (`[{ "code": str, "label": str }]`), surfaced through `EngineInfo.languages` in `api/schemas.py` and the TS type.
- Per engine:
  - **VibeVoice:** `[]` (reference-driven; no selector).
  - **OmniVoice:** `[]` (600+, auto-detected from text; no selector — per the design decision).
  - **Chatterbox:** the 23 `SUPPORTED_LANGUAGE_IDS` from `chatterbox_engine.py`, each with a human label (e.g. `{"code":"en","label":"English"}`). Language is a **synthesis param** (`language_id`, already threaded today).
  - **Kokoro:** the **distinct languages of its built-in voice catalog** — `en-US`, `en-GB`, `ja`, `zh` (derived from `_KOKORO_VOICES`). Language is a **voice filter**, not a param: Kokoro's `lang_code` is already determined by the chosen voice id.
- **Semantics flag:** the frontend decides filter-vs-param from the existing `supports_voice_cloning`:
  - cloning engine (Chatterbox) → language is a request param (`language_id`).
  - built-in-voice engine (Kokoro) → language **filters** the voice list shown in `VoiceLibrary`/roster selects; no new request field.
- No change to synthesis for Kokoro (voice already carries lang); Chatterbox already accepts `language_id`. So this phase threads the TTS-mode language into the existing `language_id` request field for cloning engines, and filters voices for built-in-voice engines.

### Frontend

- `EngineInfo.languages` added to `types/models.ts`.
- A `LanguageSelect` (new) renders when `languages.length > 0`. Its value persists per engine (e.g. `vs.lang.<engine>` in `localStorage`).
- In **TTS mode**: the dropdown sits under the textarea. For a cloning engine it sets `language_id` on the generate call; for Kokoro it filters the selectable voices to the chosen language group.
- In **Podcast mode**: the dropdown lives in the `ControlPanel` (global for the project). Same filter-vs-param rule applies to each segment's synth call.

## Data flow

1. Launch → read `vs.mode`. Unset → chooser; set → that editor with its persisted buffer.
2. TTS generate → build a single-speaker request from `ttsBuffer` (text + active voice + optional `language_id`), reuse the existing `synthesizeWav` path, cache + play the one result.
3. Podcast generate → unchanged from Phase 1, plus the optional project-level `language_id` folded into each segment request for cloning engines.
4. Language change → persist; cloning engines re-generate with new `language_id`; Kokoro re-filters voices.

## Error handling

- TTS generate with no active voice (cloning engine) → existing "No voice" toast.
- Kokoro language filter that empties the voice list (shouldn't happen for the 4 supported groups) → show "No voices for this language."
- All other paths reuse existing toasts/dialogs.

## Testing

- **Backend:** unit-test that each engine's `info()["languages"]` matches the spec (VibeVoice/OmniVoice `[]`; Chatterbox 23 codes; Kokoro `en-US/en-GB/ja/zh`), and that `/api/engines` surfaces it. Existing suite stays green.
- **Frontend:** `npm run typecheck && npm run build`.
- **Playwright:**
  1. Fresh `localStorage` → chooser shows two cards; pick Text-to-Voice → textarea renders; counts update as text is typed (`chars/words/~Ss`).
  2. Reload → chooser is skipped, TTS view restored with the typed text (buffer persisted).
  3. Toggle to Podcast → segments view; toggle back → TTS text still there (separate buffers).
  4. Switch engine to Chatterbox → language dropdown appears; to VibeVoice → dropdown hidden.
  5. Switch engine to Kokoro → language dropdown appears; choosing Japanese filters the voice list to `jf_*/jm_*`.
  6. Generate in TTS mode with the active voice → audio plays.

## Out of scope / non-goals

- Sample content (Phase 3).
- OmniVoice design/auto in TTS mode (stays podcast-roster only).
- Podcast-project persistence beyond what exists today.
- A curated OmniVoice language list (auto-detect only).
