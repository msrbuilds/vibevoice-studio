# UI Redesign Phase 3 — Mode-Adaptive Samples + Native Scripts — Design

**Date:** 2026-06-28
**Status:** Approved (user reviews all phases together after implementation)
**Part of:** the 3-phase UI redesign. Phase 3 of 3.
**Builds on:** Phase 1 (shell) + Phase 2 (project modes + language).

## Problem / goal

Today's samples (`frontend/src/lib/samples.ts`) are all **podcast-style** multi-segment scripts, and the Urdu/Hindi sample is written in **Roman script** (Latin transliteration). With Phase 2's two project modes, samples must:
1. **Adapt to the selected mode** — show **podcast** samples in Podcast mode and **simple-text** samples in Text-to-Voice mode.
2. Include **true native-script** samples: Urdu in اردو (Nastaʿlīq) and Hindi in हिन्दी (Devanagari), not Roman transliteration.

## Hard constraints

- **Additive/structural only** — keep the existing design language and the existing `SampleMenu` styling.
- **Playwright verification after the phase.**

## Scope

**In scope:**
- Split the sample catalog into **two typed lists**: `PODCAST_SAMPLES` (multi-speaker, today's shape) and `TTS_SAMPLES` (single block of text + a suggested voice).
- A new `TtsSample` type: `{ id, name, description, text, voice? }` (single text, optional suggested voice id).
- `SampleMenu` shows the list matching the **current mode** (`tts` → `TTS_SAMPLES`, `podcast` → `PODCAST_SAMPLES`).
- Loading a TTS sample fills the Phase 2 `ttsBuffer.text` (and `voiceId` if the suggested voice exists); loading a podcast sample loads segments+speakers as today.
- Add **native-script** samples to both lists:
  - Podcast: a Urdu (اردو) two-host chat and a Hindi (हिन्दी) two-host chat, in native script.
  - TTS: a Urdu (اردو) narration block and a Hindi (हिन्दी) narration block, in native script.
- Keep a couple of existing English samples in each list (interview/narrator for podcast; a short narration + a tutorial blurb for TTS).

**Out of scope:**
- Per-engine sample filtering (samples are engine-agnostic text; the active engine just synthesizes them).
- Audio pre-generation for samples.
- Any backend change (frontend-only).

## Architecture / components

- **`lib/samples.ts`**: 
  - Keep `Sample` (podcast) and `loadSample` (podcast loader) — rename the exported array to `PODCAST_SAMPLES`.
  - Add `TtsSample` + `TTS_SAMPLES` + `loadTtsSample(sample): { text, voiceId }`.
  - Native-script string constants for the Urdu/Hindi content (UTF-8; the file is already UTF-8).
- **`SampleMenu.tsx`**: take a `mode` prop; render `PODCAST_SAMPLES` or `TTS_SAMPLES`; call back `onLoadPodcast(sample)` or `onLoadTts(sample)` accordingly. Styling unchanged.
- **`App.tsx`**: wire `onLoadTts` to set the `ttsBuffer`, `onLoadPodcast` to the existing `handleLoadSample`. Pass the current `mode`.

### Native-script content

- Urdu podcast (اردو): a short, natural two-person studio chat (Ayesha/Hamza) about local offline AI voices — the same *topic* as today's Roman sample but written in fluent Urdu script.
- Hindi podcast (हिन्दी): a parallel two-person chat in Devanagari.
- Urdu TTS (اردو): one narration paragraph suitable for single-voice synthesis.
- Hindi TTS (हिन्दी): one narration paragraph in Devanagari.
- Default suggested voices: reuse the existing default voice ids (`en_Amelia`, `en_Mike`, `ur_Hamza` where present); native-script samples suggest `ur_Hamza`/a female default where available, falling back to the first available voice at load time (the loader already guards against missing voices).

## Data flow

1. User in TTS mode opens `Samples ▾` → sees `TTS_SAMPLES` → picks "اردو narration" → `ttsBuffer.text` is filled (+ suggested voice if it exists) → counts update → Generate works.
2. User in Podcast mode opens `Samples ▾` → sees `PODCAST_SAMPLES` → picks "اردو دو میزبان" → segments+speakers load as today.

## Error handling

- A sample's suggested voice id that doesn't exist on this install → fall back to the first available voice (TTS) or the existing per-speaker fallback (podcast). Same guard `loadSample` uses today.
- Empty voice catalog → sample still loads text; Generate then surfaces the existing "No voice" toast.

## Testing

- **Frontend:** `npm run typecheck && npm run build`.
- **Unit (light):** `TTS_SAMPLES` and `PODCAST_SAMPLES` are non-empty; native-script samples contain non-Latin codepoints (e.g. assert the Urdu sample matches `/[؀-ۿ]/` and the Hindi sample `/[ऀ-ॿ]/`); `loadTtsSample` returns the sample's text.
- **Playwright:**
  1. Podcast mode → `Samples ▾` lists podcast samples incl. the Urdu/Hindi native ones; loading the Urdu one populates segments whose text renders in Arabic script.
  2. Text-to-Voice mode → `Samples ▾` lists TTS samples; loading the Hindi one fills the textarea with Devanagari text and the counts update.
  3. Generate a native-script TTS sample on an engine that handles it (OmniVoice/Chatterbox) → audio plays (or request issues in a GPU-less test env).

## Out of scope / non-goals

- Engine-specific sample curation.
- Pre-rendered sample audio.
- Backend changes.
