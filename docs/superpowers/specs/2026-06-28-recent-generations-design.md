# Recent Generations (cache → playlist + detail modal) — Design

**Date:** 2026-06-28
**Status:** Approved (design confirmed; user reviews implementation)

## Problem / goal

The right-panel **Cache** section lists opaque hash rows (`4f18fb2a078d… · 4.3s · 201 KB`) with only a delete button. Turn it into a **Recent generations** playlist: each row has play/pause · name + meta · download/delete, names derived from the clip's text, and a click opens a detail modal with the full text, a real waveform visualizer, and a player.

## Key constraint discovered

The on-disk cache stores only `hash, sample_rate, duration_sec, inference_ms, created_at` — **no text, no voice**, and there's **no endpoint to fetch a clip's audio**. Both are required and are added here. Legacy entries (written before this change) have no text → they fall back to a generic name and still play/download/delete.

## Decisions (confirmed)

- **Visualizer:** real waveform — decode the WAV via Web Audio API, draw bars from amplitude peaks, overlay playback progress.
- **Scope:** individual clips only — the list **excludes** `join-` export bundles (full-podcast concatenations have no single text/voice).

## Backend

### `backend/services/synth_cache.py`
- `CacheEntry` gains `text: str | None = None`, `voice: str | None = None`.
- `put(...)` and `put_replace(...)` gain `text: str | None = None, voice: str | None = None`; both are written into the sidecar JSON.
- `_load_index` reads `text`/`voice` from the sidecar (default `None` for legacy entries).

### `backend/services/synthesize.py`
- At the existing `self._cache.put(...)` (and the regenerate `put_replace` path), pass `text=req.text` and `voice=req.speakers[0].voice_id`.

### `backend/api/cache.py`
- `CacheEntryInfo` gains `text: str | None`, `voice: str | None`, `name: str`.
- `name` is derived server-side: `_derive_name(text)` = first ~6 whitespace words of the text, collapsed + trimmed to ≤48 chars; when text is empty/None → `"Generation " + hash[:8]`.
- The list endpoint **filters out** entries whose hash starts with `"join-"`.
- New `GET /api/cache/{hash}/audio` → streams `<hash>.wav` with `media_type="audio/wav"` (404 if missing). Used for playback and download.

### Tests (`backend/tests/test_cache_recent.py`, new)
- `put` with `text`/`voice` round-trips through `_load_index` (reload a fresh `SynthCache` over the same dir).
- `_derive_name`: multi-word text → first-6-words slug; empty → `Generation <hash8>`.
- `GET /api/cache` includes `text`/`voice`/`name` and **omits** a `join-…` entry.
- `GET /api/cache/{hash}/audio` returns 200 + `audio/wav` for a real entry, 404 for a missing hash.

## Frontend

### `lib/api.ts`
- Extend `CacheEntryInfo` with `text: string | null`, `voice: string | null`, `name: string`.
- Add `cacheAudioUrl(hash: string): string` → `/api/cache/${hash}/audio`.

### `components/Waveform.tsx` (new)
- Props: `{ url: string; progress: number; isDark: boolean; onSeek?: (fraction: number) => void; height?: number }`.
- On mount/url-change: `fetch(url)` → `arrayBuffer` → `AudioContext.decodeAudioData` → compute `N` (≈64–96) peak values (max abs sample per bucket of channel 0). Cache peaks in state.
- Render bars (flex row of thin rounded divs) sized by peak; bars left of `progress` tinted teal, the rest zinc/gray. Click on the strip → `onSeek(fractionalX)`.
- Graceful fallback: while decoding or on failure, render a flat baseline row (no crash).

### `components/GenerationDetailModal.tsx` (new)
- Centered modal + backdrop (same pattern as `EngineSelector`). Header: the derived name + a close ✕.
- Body: the **full text** (scrollable), the `Waveform`, and a player bar — play/pause, seek (via waveform + a range), `current / total` time, volume.
- Owns one `<audio src={cacheAudioUrl(hash)}>`; drives `progress = currentTime/duration`; `onSeek` sets `audio.currentTime`.

### `components/CachePanel.tsx` → Recent generations
- Heading text **"Recent generations"** (in `CacheBody` and the `ControlPanel` section `<h3>`).
- Replace each hash row with a playlist row: **▶/⏸ (left)** toggles a single shared `<audio>` (one clip at a time; other rows show ▶) · **name + meta (middle)** (`{name}` over `{duration}s · {size} · {date}`) · **⬇ download + 🗑 delete (right)**. The row background (not the buttons) is clickable → opens `GenerationDetailModal` for that entry.
- Download: fetch `cacheAudioUrl(hash)` → blob → `<a download>` named `slug(name).wav` (fallback `generation-{hash8}.wav`). `slug` = lowercase, non-alphanumerics → `-`, collapse repeats, trim.
- Keep "Clear all" + "Refresh" controls. `useCacheData` polling unchanged.

### `components/ControlPanel.tsx`
- The section `<h3>` "Cache" → "Recent generations".

## Data flow

1. Synthesize → `SynthService` writes the cache entry **with** `text`+`voice`.
2. Right panel polls `/api/cache` → rows show `name` from text, newest first, joins excluded.
3. Row ▶ → shared `<audio src=/api/cache/{hash}/audio>` plays; ⬇ downloads a text-named WAV; 🗑 deletes.
4. Row click → modal with full text + real waveform (decoded from the same URL) + player.

## Error handling

- Missing/[]: "No generations yet." empty state.
- Legacy entries (no text): name = `Generation <hash8>`; everything else works.
- Audio decode failure in `Waveform`: flat baseline, playback still works via `<audio>`.
- `/audio` 404 (entry evicted mid-session): play/download show the existing error toast path; next poll drops the row.

## Out of scope

- Renaming/editing a generation's name.
- Persisting beyond the existing LRU cache; the section reflects the cache as-is.
- Waveform scrubbing precision beyond click-to-seek.
- Showing join/full-podcast bundles (excluded by decision).
