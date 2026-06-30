# UI Accessibility & Responsive Enhancements — Design

**Date:** 2026-06-29
**Status:** Approved (pending spec review)
**Scope:** Frontend only (`frontend/`). No backend or API changes.

## Goal

Three related polish enhancements to the Voice Studio UI:

1. **WCAG audit + fixes** for both color schemes (light/dark), targeting **AAA where feasible**.
2. **Custom confirmation dialogs** replacing the browser `confirm()` for data-loss actions.
3. **Better responsive handling** so the layout scales cleanly from 1024px (tablet landscape) upward, instead of wrapping the action bar and starving the middle column.

All three preserve the existing **design language** (zinc/teal palette, ElevenLabs-style 3-column shell). Changes are structural + contrast-driven, not a visual redesign.

## Decisions locked during brainstorming

| Question | Decision |
| --- | --- |
| WCAG target | **AAA where feasible.** Text → 7:1 where practical; accent buttons → at least AA (4.5:1) where 7:1 would break the brand color (each such exception flagged in the audit). |
| Confirmation scope | **Data-loss actions only:** clear cache, delete a generation, delete a voice. Segment/speaker removal stays instant. |
| Responsive strategy | **Shrink + auto-collapse.** Both side panels narrow and auto-collapse to icon rails; content stays inline (no overlay drawers). |
| Minimum supported width | **1024px (tablet landscape).** Below 1024px renders but shows a dismissible "optimized for ≥1024px" banner. |
| WCAG application (fork A) | **Lightweight semantic-token module** (`lib/theme.ts`) for the most-repeated roles; migrate failing/repeated usages; leave one-offs in place. |
| Toolbar non-wrap (fork B) | **CSS container queries** via `@tailwindcss/container-queries`, keyed on the middle column's width. |

## Architecture overview

The frontend is React 18 + TS + Vite + Tailwind. Colors today are inline `isDark ? "darkClass" : "lightClass"` ternaries repeated across ~20 components. The three features share two new foundations:

- **`frontend/src/lib/theme.ts`** — semantic role → AAA-tuned Tailwind class strings, the single source of truth for the colors that currently fail contrast.
- **A shared focus-ring convention** — `focus-visible:ring-2 focus-visible:ring-teal-500 focus-visible:ring-offset-2` (offset color themed), applied to interactive elements that currently have no visible focus indicator (WCAG 2.4.7).

Everything else builds on those.

---

## Feature 1 — WCAG AAA audit + fixes

### 1.1 Semantic token module (`lib/theme.ts`)

A small module of pure helper functions returning class strings, keyed by `isDark`. These are the roles that repeat most and/or fail contrast today:

```ts
// frontend/src/lib/theme.ts
export const theme = {
  // Body / primary text
  text:        (d: boolean) => (d ? "text-zinc-100" : "text-gray-900"),
  // Secondary / label text
  textMuted:   (d: boolean) => (d ? "text-zinc-300" : "text-gray-700"),
  // Tertiary / meta / timestamps  (was zinc-500 / gray-500 — failed)
  textSubtle:  (d: boolean) => (d ? "text-zinc-400" : "text-gray-600"),
  // Section headings (uppercase labels)
  heading:     (d: boolean) => (d ? "text-zinc-400" : "text-gray-600"),
  // Icon-only buttons (was zinc-400 / gray-400 — gray-400 failed 3:1)
  iconButton:  (d: boolean) =>
    d ? "text-zinc-300 hover:text-teal-300" : "text-gray-600 hover:text-teal-700",
  // Destructive icon buttons
  dangerIcon:  (d: boolean) =>
    d ? "text-zinc-300 hover:text-red-300" : "text-gray-600 hover:text-red-700",
  // Surfaces / borders
  surface:     (d: boolean) => (d ? "bg-zinc-950" : "bg-white"),
  border:      (d: boolean) => (d ? "border-zinc-800" : "border-gray-200"),
} as const;

// Shared focus ring (theme-agnostic; offset bg set per surface where needed)
export const focusRing =
  "focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-teal-500 " +
  "focus-visible:ring-offset-2 focus-visible:ring-offset-white dark:focus-visible:ring-offset-zinc-950";
```

Migration rule: replace usages that **fail the audit** and usages of the **repeated patterns above**. Do not churn one-off colors that already pass.

### 1.2 Contrast audit

The implementation plan will produce a full table. Known headline findings (relative-luminance contrast, computed during brainstorming; exact values re-verified in implementation):

| Pair | Current ratio | Verdict | Fix | New ratio |
| --- | --- | --- | --- | --- |
| `text-zinc-500` on `bg-zinc-950` (dark meta text) | ~4.1:1 | **Fails AA** | → `text-zinc-400` | ~7.7:1 (AAA) |
| `text-gray-500` on white (light meta text) | ~4.8:1 | AA only | → `text-gray-600` | ~7.6:1 (AAA) |
| `text-gray-400` on white (light icon buttons) | ~2.7:1 | **Fails 3:1** | → `text-gray-600` | ~7.6:1 |
| `text-zinc-500` on `bg-zinc-800` (disabled) | low | Exempt* | bump to `zinc-400` for legibility | — |
| white text on `bg-amber-600` (Generate All) | ~2.6:1 | **Fails AA** | → `bg-amber-700` + verify, else darker / dark text | target ≥4.5:1 |
| white text on `bg-teal-600` (primary buttons) | ~3.3:1 | **Fails AA (normal)** | → `bg-teal-700` | ~4.6:1 (AA ✓; AAA infeasible — flagged) |
| `text-teal-600` on white (light accent text/links) | ~3.9:1 | AA large only | → `text-teal-700` | ~5.x (AA ✓) |
| `text-teal-400` on `bg-zinc-950` (dark accent text) | high | Passes | keep | — |

\* WCAG 1.4.3 exempts inactive/disabled controls; we improve legibility anyway but do not block on a ratio.

Rule applied: **text aims for AAA (7:1); solid accent buttons (teal/amber) aim for at least AA (4.5:1)** because pushing brand colors to 7:1 against white button text would noticeably darken them. Every button kept at AA (not AAA) is listed explicitly in the audit table so the trade-off is visible.

### 1.3 Focus visibility

Buttons across the app set no focus style today. Apply the shared `focusRing` to interactive controls (toolbar buttons, player buttons, list-row action buttons, dialog buttons, voice rows). Inputs already have `focus:border-teal-500`; add the ring there too for consistency.

### 1.4 Files touched

Primarily class-string edits guided by the audit, in: `MiddleToolbar`, `InlinePlayer`, `VoiceLibrary`, `ControlPanel`, `CachePanel`, `GenerationDetailModal`, `SegmentCard`, `SpeakerRoster`, `TtsEditor`, `EngineSelector`, `SampleMenu`, `ImportExportMenu`, `ModeToggle`, `ModeChooser`, dialogs (`VoiceMetaDialog`, `UploadVoiceDialog`, `InstallEngineDialog`, `DownloadModelDialog`), `App.tsx` (toast colors). New: `lib/theme.ts`.

---

## Feature 2 — Custom confirmation dialog

### 2.1 Components

- **`frontend/src/components/ConfirmDialog.tsx`** — presentational modal following the existing pattern (`fixed inset-0 z-40 flex items-center justify-center bg-black/60 p-4`, themed card `max-w-md`). Props: `{ open, title, message, confirmLabel, cancelLabel, danger, onConfirm, onCancel }`. `danger` swaps the confirm button to red.
- **`frontend/src/components/ConfirmProvider.tsx`** — context provider exposing a promise-based `useConfirm()`:

```ts
const confirm = useConfirm();
if (await confirm({
  title: "Clear all generations?",
  message: "Next synthesis will run the model again.",
  confirmLabel: "Clear all",
  danger: true,
})) {
  // proceed
}
```

The provider holds a single `ConfirmDialog` instance + the pending promise resolver, so any descendant can call `confirm()` ergonomically (mirrors the native `confirm()` it replaces). Mounted once near the app root.

### 2.2 Accessibility

- `role="alertdialog"`, `aria-modal="true"`, `aria-labelledby`/`aria-describedby` wired to title/message.
- **Esc** = cancel, **Enter** = confirm.
- Focus trap inside the dialog; initial focus on the confirm button (cancel for `danger` is acceptable too — choose confirm for parity with native, since these are explicit user-initiated deletes); focus restored to the trigger on close.
- Backdrop click = cancel.

### 2.3 Wiring (3 call sites)

| Action | Location | Current behavior | New |
| --- | --- | --- | --- |
| Clear all cache | `CachePanel.tsx` `useCacheData.onClear` | `window.confirm()` | `await confirm({ danger })` |
| Delete a generation | `CachePanel.tsx` `CacheBody` row delete | instant | `await confirm({ danger })` |
| Delete a voice | `VoiceLibrary.tsx` upload row delete (`onRemoveVoice`) | instant | `await confirm({ danger })` |

Segment removal (`SegmentCard`) and speaker removal (`SpeakerRoster`) stay instant — frequent, low-stakes, easily re-added.

### 2.4 Files touched

New: `ConfirmDialog.tsx`, `ConfirmProvider.tsx`. Modified: `main.tsx` or `App.tsx` (mount provider), `CachePanel.tsx`, `VoiceLibrary.tsx`.

---

## Feature 3 — Responsive (shrink + auto-collapse, ≥1024px)

### 3.1 VoiceLibrary collapse

`VoiceLibrary` gains the same collapse capability `ControlPanel` already has:
- A collapse toggle in its header (`PanelLeftClose` / `PanelLeftOpen`).
- A 48px icon rail when collapsed (logo + an expand button; theme toggle stays reachable on the rail, mirroring how ControlPanel keeps the theme toggle reachable).
- Its own `localStorage` key `vs.voiceLibrary.open`.

### 3.2 Width-driven defaults

New hook **`frontend/src/hooks/useViewportWidth.ts`** (or extend `useIsNarrow`) returns the current width tier. **Explicit user toggles persist and always win**; width only drives the *first-load default* when no stored preference exists for that panel.

| Width | VoiceLibrary default | ControlPanel default |
| --- | --- | --- |
| ≥1440px | open | open |
| 1180–1440px | open | collapsed |
| 1024–1180px | collapsed | collapsed |
| <1024px | collapsed | collapsed + show banner |

`ControlPanel` already defaults collapsed `<1200px`; this formalizes and aligns the thresholds across both panels.

### 3.3 Too-narrow banner

Below 1024px, a dismissible banner (`"Voice Studio is optimized for screens ≥1024px wide."`) renders at the top of the middle column. Dismissal persists for the session (`sessionStorage`), so it does not nag on every resize.

### 3.4 Container-query toolbar/player labels

Add `@tailwindcss/container-queries` to `tailwind.config.js` plugins. Mark the middle `<main>` (or a wrapper) as a container (`@container`). Replace the viewport-based `useIsNarrow()` label collapsing in `MiddleToolbar` and `InlinePlayer` with container-query variants (`@max-[Npx]:hidden` on label text), so labels collapse based on the **middle column's actual width** — fixing "the action bar wraps at 1600px when the right panel is open."

After migration, `useIsNarrow` is removed if it has no remaining consumers (verify with a grep before deleting).

### 3.5 Modest size scaling

Apply responsive paddings/gaps at narrower widths where elements feel cramped (e.g. toolbar `p-3 xl:p-4`, button `px-3 py-2 xl:px-4 xl:py-2.5`, gaps `gap-2 xl:gap-3`). Keep changes conservative — the goal is breathing room, not a new spacing system.

### 3.6 Files touched

New: `useViewportWidth.ts` (hook), possibly `TooNarrowBanner.tsx`. Modified: `App.tsx` (layout defaults, banner), `VoiceLibrary.tsx` (collapse), `ControlPanel.tsx` (threshold alignment), `MiddleToolbar.tsx` + `InlinePlayer.tsx` (container queries), `tailwind.config.js` (plugin), `index.css` if any raw `@container` setup is needed.

---

## Error handling

- `ConfirmDialog` resolves `false` on cancel/Esc/backdrop; callers treat that as "abort, no side effects."
- Responsive hooks guard `typeof window === "undefined"` (already the pattern in `useIsNarrow`).
- The too-narrow banner never blocks interaction — the app stays fully usable below 1024px, just not optimized.

## Testing

- **Type/build:** `npm run typecheck` and `npm run build` pass after each phase.
- **Contrast:** a small dev-time check (script or inline assertion) computing the ratio for the audited pairs against their targets; documented in the audit table.
- **Playwright (per standing rule, after each phase):** screenshots at **1024, 1280, 1440, 1600px**, in **both themes**, verifying: no toolbar/player wrapping; panels collapse/expand per tier; confirm dialogs open/cancel/confirm and trap focus; too-narrow banner appears <1024px and dismisses.
- **Backend:** unchanged; existing `pytest` suite stays green (no backend edits).

## Out of scope

- No backend/API changes.
- No mobile (<1024px) optimization beyond the graceful banner.
- No full CSS-variable design-system migration (only the targeted `lib/theme.ts` token module).
- No new confirmations on segment/speaker removal.

## Phasing

Three independent phases, each independently testable and shippable:

1. **Foundation + WCAG** (`lib/theme.ts`, focus rings, contrast audit + fixes).
2. **Confirmation dialogs** (`ConfirmDialog`, `ConfirmProvider`, 3 call sites).
3. **Responsive** (VoiceLibrary collapse, width tiers, container queries, banner, size scaling).
