# UI Redesign Phase 1 — Three-Column Shell — Design

**Date:** 2026-06-28
**Status:** Approved (user reviews all phases together after implementation)
**Part of:** the 3-phase ElevenLabs-style UI redesign. Phase 1 of 3.
**Follow-ups:** Phase 2 (project modes + language) and Phase 3 (adaptive samples).

## Problem / goal

Voice Studio's UI was built as a VibeVoice-only podcast editor: a left sidebar mixing **speakers + voices**, a top action bar, a scrolling segment list, and a bottom player footer. It's now a multi-engine app. We're moving to a 3-column ElevenLabs-style layout: **voice library (left) · content (middle) · controls (right)**.

Phase 1 is a **pure structural reorganization** — relocate and reshape the existing components into three columns with **zero behavior change and zero restyle**. The design language (teal accents, zinc dark palette, rounded cards, existing Tailwind tokens) stays exactly as-is. Phases 2–3 add the adaptive project modes and samples on top of this foundation.

## Hard constraints (apply to every phase)

- **Structural only.** Reuse existing components and Tailwind classes. Do not change colors, spacing scale, fonts, or the design language. Containers move and reshape; styling is copied verbatim.
- **Playwright verification after the phase** (see Testing).

## Scope

**In scope:**
- New 3-column layout scaffold in `App.tsx` replacing the current fixed-sidebar + fixed-top-bar + fixed-footer arrangement.
- Extract the left sidebar's **voice library** (built-in voices, my voices, upload) into a `VoiceLibrary` component. The header (logo + model id) stays at the top of the left column.
- Move the **speaker roster** (the `SPEAKERS` section incl. the OmniVoice Clone/Design/Auto toggle and voice select) out of the left sidebar to the **top of the middle column**, as a `SpeakerRoster` component.
- Middle column **toolbar** at top: `Add Segment`, `Generate All`, `Samples ▾`, `Import/Export` (the content-oriented actions).
- Move the **player** (`Full podcast · Download Audio · Play Podcast`) from the bottom-spanning footer to the bottom of the **middle column** (inline, sticky to the column bottom).
- New **right control panel** (`ControlPanel`), persistent on wide screens and collapsible on narrow ones, containing: the `EngineSelector`, the `Settings` content (CFG / exaggeration sliders, inline — not a popover), the theme toggle, and the `device · dtype · sr` info line.

**Out of scope (Phase 2/3):**
- The Text-to-Voice / Podcast project-mode chooser and persistence.
- The big-textarea TTS view, character/word/duration counts, language dropdown.
- Any sample content changes.
- Any backend change. Phase 1 is frontend-only.

## Architecture

```
┌──────────────────┬─────────────────────────────────┬───────────────────┐
│ LEFT (w-80)      │ MIDDLE (flex-1)                 │ RIGHT (w-80,      │
│ VoiceLibrary     │                                 │ collapsible)      │
│                  │ Toolbar: [Add][GenAll][Samples] │ ControlPanel      │
│ • header (logo)  │          [Import/Export]        │ • EngineSelector  │
│ • Built-in voices│ SpeakerRoster (podcast)         │ • Settings (CFG,  │
│ • My voices (+)  │ Segment cards…                  │   exaggeration)   │
│                  │ ─ inline Player ─               │ • ThemeToggle     │
│                  │                                 │ • device/dtype/sr │
└──────────────────┴─────────────────────────────────┴───────────────────┘
```

### Layout mechanics

- Replace the current `fixed`-positioned sidebar/top-bar/footer with a **flex row** filling the viewport: `<div class="flex h-screen">` → `LeftSidebar` (fixed `w-80`, own scroll), `MiddleColumn` (`flex-1`, own scroll + sticky toolbar/player), `RightPanel` (`w-80` when open).
- The middle column is itself a vertical flex: a sticky top toolbar, a scrollable body (roster + segments), and a sticky bottom player. This removes the `ResizeObserver` height-measuring hack in the current `ActionBar`/`PlayerFooter` (the bars were `fixed` and overlapped content; in a flex column they don't need measured padding).
- **Right panel collapse:** a `collapsed` boolean (default open on wide). When collapsed, the panel is replaced by a thin vertical strip with a gear/`PanelRight` icon button to reopen. A `useIsNarrow`-style hook auto-collapses below ~1200px on mount; the user can still toggle. Collapsed/open state persists to `localStorage` (`vs.controlPanel.open`).

### Components (new + changed)

- **`VoiceLibrary`** (new, extracted from `Sidebar.tsx`): the header, built-in voices list, my-voices list + upload button, and the `UploadVoiceDialog`/`VoiceMetaDialog` wiring. Props are the voice-related subset of today's `Sidebar` props. Styling copied verbatim from the current sidebar sections.
- **`SpeakerRoster`** (new, extracted from `Sidebar.tsx`'s `SpeakerRow` + the SPEAKERS section): renders the speaker list with add/remove/rename, the voice `<select>`, and the OmniVoice Clone/Design/Auto toggle + design chips. Same `SpeakerRow` internals, just relocated and wrapped in a middle-column container. Shown in Phase 1 always (podcast is the only mode yet).
- **`MiddleToolbar`** (new, from `ActionBar.tsx`): the `Add Segment` / `Generate All` buttons + `SampleMenu` + `ImportExportMenu`. Drops the `EngineSelector` and `SettingsMenu` (those move right). Drops the `ResizeObserver` height plumbing.
- **`ControlPanel`** (new): hosts `EngineSelector`, the CFG/exaggeration sliders (reuse `CfgScaleControl` + the exaggeration control currently inside `SettingsMenu`, rendered inline), `ThemeToggle`, and the device/dtype/sr line. Collapsible.
- **`App.tsx`**: rewires the three columns; keeps ALL existing state and handlers (generation, playback, export, import, samples, engine switching, install/download dialogs) unchanged — only the JSX tree that places them moves.

### What is deliberately NOT refactored

- `SegmentCard`, `EngineSelector`, `SampleMenu`, `ImportExportMenu`, `CfgScaleControl`, `UploadVoiceDialog`, `VoiceMetaDialog`, `InstallEngineDialog`, `DownloadModelDialog`, the `store.ts` reducer, all hooks, and `lib/api.ts` are reused as-is. `Sidebar.tsx`, `ActionBar.tsx`, `PlayerFooter.tsx` are superseded by the new components and removed once nothing imports them. `SettingsMenu.tsx`'s slider bodies are reused inside `ControlPanel` (the popover shell is dropped).

## Data flow

No data-flow change. The same `useProject`/`useEngine`/`useVoices`/`useConfig` state feeds the same handlers; only their placement in the DOM changes. `displayedVoices` filtering, `isSegmentCached`, generation/playback/export logic are untouched.

## Error handling

Unchanged: the existing toast, install/download dialogs, and degraded-mode banners are reused. The `configError`/loading states render the same fallback screens.

## Testing

- **Type/build:** `cd frontend && npm run typecheck && npm run build` must pass.
- **Playwright** (run the dev server, drive a real browser):
  1. App loads; assert three columns are present: voice library on the left (built-in + my voices headings visible), the toolbar + a segment in the middle, the control panel on the right (engine selector + a settings slider visible).
  2. The speaker roster renders at the top of the middle column (not in the left sidebar).
  3. Right panel collapse: click the collapse control → panel hides → click reopen → panel returns; reload → state persisted.
  4. Smoke a generate+play on the active engine (VibeVoice or whatever is loaded) — the segment shows Ready and Play works (or, if no GPU in the test env, assert the request is issued and the busy state toggles).
  5. Visual check: take a screenshot and confirm the palette/cards match the pre-change design (no restyle).
- **No backend tests** (frontend-only phase); the existing `cd backend && pytest` suite must still pass untouched (sanity, not expected to change).

## Out of scope / non-goals

- No project-mode selection (Phase 2).
- No visual redesign — structural only.
- No backend changes.
