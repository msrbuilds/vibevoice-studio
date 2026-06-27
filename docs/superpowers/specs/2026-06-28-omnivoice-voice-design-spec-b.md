# OmniVoice Voice Design + Auto (Spec B) — Design

**Date:** 2026-06-28
**Status:** Approved (pending spec review)
**Builds on:** Spec A (`2026-06-27-omnivoice-engine-design.md`), which shipped the OmniVoice isolated-venv engine with **clone-only** synthesis. The worker (`backend/omnivoice_worker.py`) already implements all three generate modes (`clone`/`design`/`auto`); Spec B is the frontend + request-plumbing layer that lets the user reach `design` and `auto`.

## Problem / goal

OmniVoice can produce a voice three ways:
- **clone** — `generate(text, ref_audio, ref_text?)` from a reference clip (Spec A).
- **design** — `generate(text, instruct="female, low pitch, british accent")` from a free-text attribute prompt.
- **auto** — `generate(text)` with no prompt; OmniVoice invents a voice.

Spec A only wired `clone`. Spec B adds a **per-speaker Clone/Design/Auto mode toggle** (shown only when OmniVoice is the active engine) and threads `voice_mode` + `instruct` end-to-end so design and auto work.

## Settled UX decisions (from brainstorming)

- **Explicit per-speaker 3-way toggle** (Clone / Design / Auto), not precedence-based.
- **Default mode** = Clone if the speaker already has a reference voice selected, else Auto. Derived, not eagerly stored.
- **Design input** = a free-text box **plus a row of one-tap attribute chips** that append to the text.
- The toggle and design/auto inputs appear **only when `activeEngine === "omnivoice"`**. Every other engine renders exactly as today.

## Scope

**In scope:**
- `Speaker` model gains `omnivoiceMode` + `voiceDesign`; the SpeakerRow UI (toggle + mode-specific input + chips).
- `voice_mode` + `instruct` plumbed per-speaker through TS → API → service → `EngineSynthRequest` → proxy.
- `OmniVoiceEngine._build_synth_msg` dispatches all three modes (replaces the Spec-A clone-only raise).
- Backend voice-resolution + cache-key changes so design/auto need no voice and never collide across modes/prompts.
- The frontend "No voice assigned" guard fires only for clone mode.

**Out of scope (YAGNI):**
- `num_step`/`duration` UI controls (the engine keeps its configured `num_step` default).
- `ref_text` for clone (still omitted; OmniVoice auto-transcribes).
- Multi-speaker per-voice design routing — OmniVoice is `max_speakers=1`, so each synth call is single-speaker; no change to the multi-speaker join path is needed.
- Persisting chip "selected" state — chips are momentary append buttons, not toggles with state.

## The effective-mode rule

A speaker's mode is **derived** so switching engines never mutates state and an untouched speaker follows the smart default:

```
effectiveMode(speaker) = speaker.omnivoiceMode ?? (speaker.voice ? "clone" : "auto")
```

`omnivoiceMode` is set only when the user explicitly clicks a toggle segment. This rule is used in both the SpeakerRow render and `generateFor`.

## Components

### Frontend

**1. `types/models.ts` — `Speaker`**
Add two optional fields:
```ts
omnivoiceMode?: "clone" | "design" | "auto";
voiceDesign?: string;   // the instruct prompt (design mode)
```
`SynthSpeaker` (the request payload type) gains:
```ts
voice_mode?: "clone" | "design" | "auto";
instruct?: string;
```

**2. `lib/store.ts`**
No new reducer actions: `updateSpeaker(id, patch)` already accepts `Partial<Speaker>`, so `updateSpeaker(id, { omnivoiceMode })` and `updateSpeaker(id, { voiceDesign })` work as-is. (Confirm `INITIAL_SPEAKER`/`addSpeaker` need no change — the new fields are optional.)

**3. `components/Sidebar.tsx` — `SpeakerRow`**
- Thread a new `activeEngine: string | null` prop down from `Sidebar` (which already receives `activeEngine`).
- When `activeEngine !== "omnivoice"`: render today's voice dropdown unchanged.
- When `activeEngine === "omnivoice"`: render a compact 3-segment toggle (Clone / Design / Auto) bound to `effectiveMode(speaker)`; clicking a segment calls `onUpdate({ omnivoiceMode: <mode> })`. Below it, switch on the effective mode:
  - **clone** → the existing voice `<select>`.
  - **design** → a text input bound to `speaker.voiceDesign` (`onUpdate({ voiceDesign })`) with placeholder `"e.g. female, low pitch, british accent, warm"`, plus a wrapped row of chip buttons from a small constant `DESIGN_CHIPS` (e.g. `female, male, low pitch, high pitch, british accent, american accent, whisper, energetic, calm`). Clicking a chip appends `", <chip>"` to `voiceDesign` (or the bare chip if empty), skipping if already present.
  - **auto** → a one-line muted hint: "OmniVoice will invent a voice for this speaker."

**4. `App.tsx` — `generateFor`**
- Compute `mode = effectiveMode(speaker)`.
- Guard: require `speaker.voice` **unless** `activeEngine === "omnivoice" && (mode === "design" || mode === "auto")`. So the relaxation is gated on OmniVoice — a voice-less VibeVoice/Kokoro/Chatterbox speaker still gets today's "No voice assigned" error, and OmniVoice clone mode still requires a voice. Only OmniVoice design/auto skip the guard.
- Build the `SynthSpeaker` with `voice` (empty string allowed for design/auto), `voice_mode: activeEngine === "omnivoice" ? mode : undefined`, and `instruct: mode === "design" ? (speaker.voiceDesign ?? "") : undefined`.

**5. `lib/api.ts` — `synthesizeWav`**
Include `voice_mode` and `instruct` on each speaker object in the POST body when present.

**6. Frontend cache badge** (`isSegmentCached` / `audioCache`)
The per-segment cached-badge comparison currently folds text + voice. Extend it to also fold the speaker's effective mode + `voiceDesign`, so changing the design prompt visibly un-caches the segment. (Backend correctness is already guaranteed by the cache key below; this is just the UI badge.)

### Backend

**7. `api/schemas.py` — `SynthSpeakerModel`**
- Relax `voice` from `min_length=1` to allow empty (`str = Field("", ...)`), since design/auto carry no voice. Clone-mode "voice required" is still enforced downstream (voice resolution raises `VoiceNotFound` for an empty/unknown id).
- Add `voice_mode: Literal["clone", "design", "auto"] | None = None` and `instruct: str | None = None`.

**8. `api/synthesize.py` route → `SynthRequest`/`Speaker`**
- The service `Speaker` dataclass (`services/synthesize.py`) gains `voice_mode: str | None = None` and `instruct: str | None = None`.
- The route that converts `SynthSpeakerModel` → `Speaker` passes the two new fields through.

**9. `core/engines/__init__.py` — `EngineSynthRequest`**
Add `voice_mode: str | None = None` and `instruct: str | None = None` (engines that don't understand them ignore them, like the other optional fields).

**10. `services/synthesize.py` — `_resolve_request_context` + cache key**
- In the speaker loop, resolve `reference_audio` only when the speaker's mode is clone (`sp.voice_mode in (None, "clone")`); for design/auto leave it `None` (skip `self._voices.get`). This prevents the `VoiceNotFound` raise for design/auto.
- Thread `voice_mode` + `instruct` from `req.speakers[0]` into the `EngineSynthRequest` (single-speaker fast path — OmniVoice is always single-speaker).
- Cache key: fold `voice_mode` and `instruct` into the existing `extra` string (e.g. `|vm=design|in=<instruct>`). When there is no `reference_audio` (design/auto), derive `cache_voice_key` from `f"{voice_mode}:{instruct or ''}"` instead of a filename, and pass that (not an empty voice id) into `voice_samples`. Net effect: clone/design/auto and distinct prompts each get their own cache slot; identical design prompts reuse the cache.

**11. `core/engines/omnivoice_engine.py` — `_build_synth_msg`**
Replace the Spec-A clone-only body with mode dispatch:
- `mode = req.voice_mode or ("clone" if req.reference_audio else "auto")` (defensive default mirrors the frontend rule).
- **clone** → require `reference_audio`; send `{mode:"clone", ref_audio, ...}`.
- **design** → send `{mode:"design", instruct: req.instruct or ""}`; if `instruct` is empty, downgrade to `auto` (so an empty design box doesn't error).
- **auto** → send `{mode:"auto", ...}`.
- Always include `text`, `out_wav`, `speed` (if set), `num_step` (if set). The worker already reads exactly these keys.

## Data flow

1. OmniVoice active → SpeakerRow shows the toggle; a fresh speaker with no voice defaults to **Auto**, one with a voice defaults to **Clone**.
2. User picks **Design**, types/chips a prompt → `speaker.voiceDesign` updates; `omnivoiceMode = "design"` stored.
3. Generate → `generateFor` builds a `SynthSpeaker {voice:"", voice_mode:"design", instruct:"female, british accent"}` → POST.
4. Service skips voice resolution (design), builds `EngineSynthRequest(voice_mode="design", instruct=...)`, computes a design-specific cache hash, and on miss calls the engine.
5. Proxy `_build_synth_msg` emits `{op:"synth", mode:"design", instruct, ...}` → worker `generate(text, instruct=...)` → 24 kHz WAV.

## Error handling

- **Clone, no voice** → "No voice assigned" (clone-only), unchanged for other engines.
- **Design, empty prompt** → silently treated as **auto** (both frontend default and the proxy downgrade), so the user never hits a hard error from a blank box.
- **Non-OmniVoice engines** → `voice_mode`/`instruct` are `None`/absent; every existing path runs byte-for-byte as before (regression-safe).
- **Cache** → mode/prompt changes produce a different hash, so stale audio is never returned; the frontend badge update keeps the "cached" indicator honest.

## Testing

- **Backend:**
  - `OmniVoiceEngine._build_synth_msg` for all three modes: clone requires `reference_audio` (raises without), design emits `instruct`, empty design → `auto`, auto emits neither.
  - `SynthService` cache-key divergence: clone vs design vs auto, and two different design prompts, produce different hashes; identical design prompts produce the same hash. Design/auto requests resolve with no `reference_audio` and don't raise `VoiceNotFound` (use a stub engine with `max_speakers=1`, `supports_voice_cloning=True`, and a fake voice registry).
  - `SynthSpeakerModel` accepts `voice=""` with a `voice_mode`.
- **Frontend:** `npm run typecheck` + `npm run build`; a small unit check of the `effectiveMode` helper (clone when voice set, auto when not, explicit override wins) and the chip-append helper (appends, dedupes, handles empty).

## Out of scope / non-goals

- No `num_step`/`duration` UI.
- No multi-speaker per-voice design.
- No persisted chip selection state.
- No change to VibeVoice/Kokoro/Chatterbox behaviour.
