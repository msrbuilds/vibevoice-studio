# UI Accessibility & Responsive Enhancements Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make the Voice Studio frontend WCAG-AAA-where-feasible, replace browser `confirm()` with styled confirmation dialogs for data-loss actions, and make the 3-column layout scale cleanly from 1024px upward.

**Architecture:** Three independent phases over the existing React 18 + TS + Vite + Tailwind v3 frontend. Phase 1 adds a Vitest test harness, a contrast utility, and a semantic-token module (`lib/theme.ts`), then fixes contrast + focus rings across components. Phase 2 adds a promise-based `useConfirm()` provider + `ConfirmDialog`. Phase 3 adds width-tier-driven panel auto-collapse, container-query toolbar labels, and a too-narrow banner.

**Tech Stack:** React 18, TypeScript, Vite 5, Tailwind v3.4, lucide-react. New dev deps: `vitest`, `jsdom`, `@testing-library/react`, `@testing-library/jest-dom`, `@testing-library/user-event`, `@tailwindcss/container-queries`.

**Spec:** `docs/superpowers/specs/2026-06-29-ui-accessibility-responsive-design.md`

**Working directory for all commands:** `frontend/` unless stated otherwise.

**Branch:** Implement on a feature branch (e.g. `feat/a11y-responsive`), not `main`.

---

## File Structure

**New files:**
- `frontend/vitest.config.ts` — Vitest config (jsdom env, setup file).
- `frontend/src/test/setup.ts` — Testing Library jest-dom matchers.
- `frontend/src/lib/contrast.ts` — pure WCAG contrast-ratio math + Tailwind palette hex map.
- `frontend/src/lib/contrast.test.ts` — data-driven audit asserting chosen colors meet targets.
- `frontend/src/lib/theme.ts` — semantic role → AAA-tuned class strings + shared `focusRing`.
- `frontend/src/components/ConfirmDialog.tsx` — presentational confirm modal.
- `frontend/src/components/ConfirmProvider.tsx` — context provider + `useConfirm()` hook.
- `frontend/src/components/ConfirmProvider.test.tsx` — provider behavior tests.
- `frontend/src/lib/layout.ts` — pure width-tier + panel-default helpers.
- `frontend/src/lib/layout.test.ts` — tier/default tests.
- `frontend/src/hooks/useViewportWidth.ts` — reactive viewport width hook.
- `frontend/src/components/TooNarrowBanner.tsx` — dismissible <1024px notice.

**Modified files:**
- `frontend/package.json` — add `test` script + dev deps.
- `frontend/tailwind.config.js` — add container-queries plugin.
- Component class-string edits (Phase 1 sweep): `App.tsx`, `MiddleToolbar.tsx`, `InlinePlayer.tsx`, `VoiceLibrary.tsx`, `ControlPanel.tsx`, `CachePanel.tsx`, `GenerationDetailModal.tsx`, `SegmentCard.tsx`, `SpeakerRoster.tsx`, `TtsEditor.tsx`, `EngineSelector.tsx`, `SampleMenu.tsx`, `ImportExportMenu.tsx`, `ModeToggle.tsx`, `ModeChooser.tsx`, `ThemeToggle.tsx`, `VoiceMetaDialog.tsx`, `UploadVoiceDialog.tsx`, `InstallEngineDialog.tsx`, `DownloadModelDialog.tsx`, `CfgScaleControl.tsx`, `ExaggerationControl.tsx`, `LanguageSelect.tsx`, `Waveform.tsx`.
- `frontend/src/main.tsx` — mount `ConfirmProvider`.
- Phase 3 wiring: `App.tsx`, `VoiceLibrary.tsx`, `ControlPanel.tsx`, `MiddleToolbar.tsx`, `InlinePlayer.tsx`.

**Deleted (Phase 3, if no consumers remain):** `frontend/src/hooks/useIsNarrow.ts`.

---

# PHASE 1 — Foundation + WCAG

## Task 1: Add the Vitest test harness

**Files:**
- Create: `frontend/vitest.config.ts`
- Create: `frontend/src/test/setup.ts`
- Modify: `frontend/package.json`

- [ ] **Step 1: Install dev dependencies**

Run (in `frontend/`):
```bash
npm install -D vitest@^2 jsdom@^25 @testing-library/react@^16 @testing-library/dom@^10 @testing-library/jest-dom@^6 @testing-library/user-event@^14
```
Expected: packages added to `devDependencies`, no errors.

- [ ] **Step 2: Create the Vitest config**

Create `frontend/vitest.config.ts`:
```ts
import { defineConfig } from "vitest/config";
import react from "@vitejs/plugin-react";
import path from "node:path";

export default defineConfig({
  plugins: [react()],
  resolve: {
    alias: { "@": path.resolve(__dirname, "./src") },
  },
  test: {
    environment: "jsdom",
    globals: true,
    setupFiles: ["./src/test/setup.ts"],
    css: false,
  },
});
```

- [ ] **Step 3: Create the test setup file**

Create `frontend/src/test/setup.ts`:
```ts
import "@testing-library/jest-dom";
```

- [ ] **Step 4: Add the test script**

In `frontend/package.json`, add to `"scripts"`:
```json
    "test": "vitest run",
    "test:watch": "vitest"
```

- [ ] **Step 5: Add a smoke test to verify the harness runs**

Create `frontend/src/test/smoke.test.ts`:
```ts
import { describe, it, expect } from "vitest";

describe("vitest harness", () => {
  it("runs", () => {
    expect(1 + 1).toBe(2);
  });
});
```

- [ ] **Step 6: Run the smoke test**

Run: `npm test`
Expected: PASS (1 test passed). If alias/jsdom errors appear, fix config before continuing.

- [ ] **Step 7: Delete the smoke test and commit**

Delete `frontend/src/test/smoke.test.ts` (keep `setup.ts`).
```bash
git add frontend/package.json frontend/package-lock.json frontend/vitest.config.ts frontend/src/test/setup.ts
git commit -m "test: add Vitest + Testing Library harness"
```

---

## Task 2: WCAG contrast utility + audit test (TDD)

**Files:**
- Create: `frontend/src/lib/contrast.ts`
- Create: `frontend/src/lib/contrast.test.ts`

This task locks in the exact color decisions via an executable audit. Ratios below were computed during design with the WCAG 2.x relative-luminance formula.

- [ ] **Step 1: Write the failing test**

Create `frontend/src/lib/contrast.test.ts`:
```ts
import { describe, it, expect } from "vitest";
import { contrastRatio, PALETTE } from "./contrast";

// Sanity checks on the math itself
describe("contrastRatio", () => {
  it("is 21 for black on white", () => {
    expect(contrastRatio("#000000", "#ffffff")).toBeCloseTo(21, 0);
  });
  it("is 1 for identical colors", () => {
    expect(contrastRatio("#14b8a6", "#14b8a6")).toBeCloseTo(1, 5);
  });
  it("is symmetric", () => {
    const a = contrastRatio(PALETTE["zinc-400"], PALETTE["zinc-950"]);
    const b = contrastRatio(PALETTE["zinc-950"], PALETTE["zinc-400"]);
    expect(a).toBeCloseTo(b, 5);
  });
});

// The audit: every CHOSEN (post-fix) pair must clear its target.
// AAA = 7:1 for text; accent buttons flagged as AA = 4.5:1.
const AAA = 7;
const AA = 4.5;
const UI = 3; // graphical objects / large text

const AUDIT: Array<{ fg: string; bg: string; min: number; label: string }> = [
  // --- Dark theme text (target AAA) ---
  { fg: "zinc-400", bg: "zinc-950", min: AAA, label: "dark subtle/meta text" },
  { fg: "zinc-300", bg: "zinc-950", min: AAA, label: "dark muted text" },
  { fg: "zinc-100", bg: "zinc-950", min: AAA, label: "dark primary text" },
  { fg: "teal-400", bg: "zinc-950", min: AAA, label: "dark accent text" },
  // --- Light theme text (target AAA) ---
  { fg: "gray-600", bg: "white", min: AAA, label: "light subtle/meta/icon text" },
  { fg: "gray-700", bg: "white", min: AAA, label: "light muted text" },
  { fg: "gray-900", bg: "white", min: AAA, label: "light primary text" },
  // --- Accent text links (target AA; AAA infeasible on brand teal) ---
  { fg: "teal-700", bg: "white", min: AA, label: "light accent text" },
  // --- Solid accent buttons w/ white text (target AA; flagged) ---
  { fg: "white", bg: "teal-700", min: AA, label: "primary button (teal)" },
  { fg: "white", bg: "amber-700", min: AA, label: "generate-all button (amber)" },
  { fg: "white", bg: "red-600", min: AA, label: "danger button (red)" },
  // --- Danger icon hover (UI / large) ---
  { fg: "red-700", bg: "white", min: AA, label: "light danger icon hover" },
];

describe("WCAG audit — chosen colors clear their targets", () => {
  for (const { fg, bg, min, label } of AUDIT) {
    it(`${label}: ${fg} on ${bg} >= ${min}:1`, () => {
      const ratio = contrastRatio(PALETTE[fg], PALETTE[bg]);
      expect(ratio).toBeGreaterThanOrEqual(min);
    });
  }
});

// Regression guards: the colors we REPLACED must indeed have failed,
// documenting WHY they were changed.
describe("WCAG audit — replaced colors were failing", () => {
  it("zinc-500 on zinc-950 failed AA", () => {
    expect(contrastRatio(PALETTE["zinc-500"], PALETTE["zinc-950"])).toBeLessThan(AA);
  });
  it("gray-400 on white failed UI 3:1", () => {
    expect(contrastRatio(PALETTE["gray-400"], PALETTE["white"])).toBeLessThan(UI);
  });
  it("white on amber-600 failed AA", () => {
    expect(contrastRatio(PALETTE["white"], PALETTE["amber-600"])).toBeLessThan(AA);
  });
  it("white on teal-600 failed AA", () => {
    expect(contrastRatio(PALETTE["white"], PALETTE["teal-600"])).toBeLessThan(AA);
  });
});
```

- [ ] **Step 2: Run the test to verify it fails**

Run: `npm test -- contrast`
Expected: FAIL with "Cannot find module './contrast'" (or similar import error).

- [ ] **Step 3: Implement the contrast utility**

Create `frontend/src/lib/contrast.ts`:
```ts
/**
 * WCAG 2.x relative-luminance contrast math + the subset of the Tailwind v3
 * palette this app uses. Pure and dependency-free so it can run under Vitest
 * and double as living documentation of our color decisions.
 */

export const PALETTE: Record<string, string> = {
  white: "#ffffff",
  "gray-50": "#f9fafb",
  "gray-100": "#f3f4f6",
  "gray-200": "#e5e7eb",
  "gray-300": "#d1d5db",
  "gray-400": "#9ca3af",
  "gray-500": "#6b7280",
  "gray-600": "#4b5563",
  "gray-700": "#374151",
  "gray-900": "#111827",
  "zinc-100": "#f4f4f5",
  "zinc-300": "#d4d4d8",
  "zinc-400": "#a1a1aa",
  "zinc-500": "#71717a",
  "zinc-700": "#3f3f46",
  "zinc-800": "#27272a",
  "zinc-900": "#18181b",
  "zinc-950": "#09090b",
  "teal-300": "#5eead4",
  "teal-400": "#2dd4bf",
  "teal-500": "#14b8a6",
  "teal-600": "#0d9488",
  "teal-700": "#0f766e",
  "amber-600": "#d97706",
  "amber-700": "#b45309",
  "red-300": "#fca5a5",
  "red-600": "#dc2626",
  "red-700": "#b91c1c",
};

function channelToLinear(c8: number): number {
  const c = c8 / 255;
  return c <= 0.03928 ? c / 12.92 : Math.pow((c + 0.055) / 1.055, 2.4);
}

/** Relative luminance per WCAG 2.x. */
export function luminance(hex: string): number {
  const h = hex.replace("#", "");
  const r = parseInt(h.slice(0, 2), 16);
  const g = parseInt(h.slice(2, 4), 16);
  const b = parseInt(h.slice(4, 6), 16);
  return (
    0.2126 * channelToLinear(r) +
    0.7152 * channelToLinear(g) +
    0.0722 * channelToLinear(b)
  );
}

/** Contrast ratio between two hex colors (order-independent, 1..21). */
export function contrastRatio(a: string, b: string): number {
  const la = luminance(a);
  const lb = luminance(b);
  const lighter = Math.max(la, lb);
  const darker = Math.min(la, lb);
  return (lighter + 0.05) / (darker + 0.05);
}
```

- [ ] **Step 4: Run the test to verify it passes**

Run: `npm test -- contrast`
Expected: PASS (all audit + regression cases green). If any audit case fails, the chosen color is wrong — adjust the color in `theme.ts` (Task 3) and re-check; do not loosen the threshold.

- [ ] **Step 5: Commit**

```bash
git add frontend/src/lib/contrast.ts frontend/src/lib/contrast.test.ts
git commit -m "test: WCAG contrast utility + color audit"
```

---

## Task 3: Semantic token module + focus ring

**Files:**
- Create: `frontend/src/lib/theme.ts`

- [ ] **Step 1: Create the token module**

Create `frontend/src/lib/theme.ts`:
```ts
/**
 * Semantic color roles → AAA-tuned Tailwind class strings, the single source
 * of truth for the colors that previously failed contrast (see contrast.test.ts).
 * Each helper takes `isDark` and returns a className fragment.
 */
export const theme = {
  /** Primary body text. */
  text: (d: boolean) => (d ? "text-zinc-100" : "text-gray-900"),
  /** Secondary / label text. */
  textMuted: (d: boolean) => (d ? "text-zinc-300" : "text-gray-700"),
  /** Tertiary / meta / timestamps (was zinc-500 / gray-500 — failed). */
  textSubtle: (d: boolean) => (d ? "text-zinc-400" : "text-gray-600"),
  /** Uppercase section headings. */
  heading: (d: boolean) => (d ? "text-zinc-400" : "text-gray-600"),
  /** Icon-only buttons (was zinc-400 / gray-400 — gray-400 failed 3:1). */
  iconButton: (d: boolean) =>
    d ? "text-zinc-300 hover:text-teal-300" : "text-gray-600 hover:text-teal-700",
  /** Destructive icon buttons. */
  dangerIcon: (d: boolean) =>
    d ? "text-zinc-300 hover:text-red-300" : "text-gray-600 hover:text-red-700",
  /** Panel surface. */
  surface: (d: boolean) => (d ? "bg-zinc-950" : "bg-white"),
  /** Panel border. */
  border: (d: boolean) => (d ? "border-zinc-800" : "border-gray-200"),
} as const;

/**
 * Shared visible focus indicator (WCAG 2.4.7). Append to interactive elements.
 * The offset color is themed so the ring reads on both surfaces.
 */
export const focusRing =
  "focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-teal-500 " +
  "focus-visible:ring-offset-2 focus-visible:ring-offset-white dark:focus-visible:ring-offset-zinc-950";

/** Primary solid button base (teal). AA-compliant white-on-teal-700. */
export const primaryButton =
  "bg-teal-700 hover:bg-teal-600 text-white disabled:bg-zinc-700 disabled:text-zinc-400";
```

- [ ] **Step 2: Typecheck**

Run: `npm run typecheck`
Expected: PASS (no errors; the module is not yet imported anywhere).

- [ ] **Step 3: Commit**

```bash
git add frontend/src/lib/theme.ts
git commit -m "feat(theme): semantic AAA color tokens + focus ring"
```

---

## Task 4: Apply contrast fixes + focus rings across components

This is a mechanical sweep guided by a fixed mapping. The audit test (Task 2) already proves the *target* colors are correct; this task changes the *usages*. Verification is typecheck + build + Playwright (Task 5), since class-string swaps aren't unit-testable.

**Canonical replacement mapping** (apply everywhere these appear, in both the `isDark` and light branches of ternaries):

| Old class | New class | Role |
| --- | --- | --- |
| `text-zinc-500` | `text-zinc-400` | dark subtle/meta/heading |
| `text-gray-500` | `text-gray-600` | light subtle/meta/heading |
| `text-gray-400` | `text-gray-600` | light icon button |
| `text-zinc-400` (as icon btn base) | `text-zinc-300` | dark icon button |
| `text-teal-600` (text/links on light) | `text-teal-700` | light accent text |
| `bg-teal-600 hover:bg-teal-500` (solid buttons) | `bg-teal-700 hover:bg-teal-600` | primary button |
| `bg-amber-600 hover:bg-amber-500` | `bg-amber-700 hover:bg-amber-600` | generate-all button |
| `hover:text-red-600` (light danger) | `hover:text-red-700` | light danger icon |
| `text-amber-100` (count on amber btn) | `text-white` | button count text |

Leave unchanged: `text-teal-400` on dark (10.7:1 ✓), `bg-red-600` danger buttons (white text 4.8:1 ✓), already-passing primary text (`text-white`/`text-gray-900`).

**Focus rings:** append `` ${focusRing} `` (import from `@/lib/theme`) to the `className` of every `<button>` and clickable role element, and add it to inputs/selects/textareas alongside their existing `focus:border-teal-500`.

- [ ] **Step 1: Inventory occurrences**

Run (from repo root):
```bash
cd frontend && npx grep -rn "text-zinc-500\|text-gray-500\|text-gray-400\|bg-teal-600\|bg-amber-600\|text-teal-600\|hover:text-red-600\|text-amber-100" src/ || \
  grep -rn "text-zinc-500\|text-gray-500\|text-gray-400\|bg-teal-600\|bg-amber-600\|text-teal-600\|hover:text-red-600\|text-amber-100" src/
```
Expected: a list of files+lines to edit. Use the Grep tool in practice; this command just enumerates scope.

- [ ] **Step 2: Apply the mapping to `MiddleToolbar.tsx`**

In `frontend/src/components/MiddleToolbar.tsx`:
- Import the helpers: add at top `import { focusRing } from "@/lib/theme";`
- Generate-all button: change `bg-amber-600 hover:bg-amber-500 text-white` → `bg-amber-700 hover:bg-amber-600 text-white`.
- Generate-all count: change `text-amber-100` → `text-white`.
- Add-segment button (teal): change `bg-teal-600 hover:bg-teal-500` → `bg-teal-700 hover:bg-teal-600`.
- Append `` ` ${focusRing}` `` to the Add-segment and Generate-all button className strings.

Example (Add-segment button):
```tsx
className={`flex items-center gap-2 px-4 py-2.5 bg-teal-700 hover:bg-teal-600 disabled:bg-zinc-700 text-white disabled:text-zinc-400 rounded-lg font-medium transition-colors disabled:cursor-not-allowed ${focusRing}`}
```

- [ ] **Step 3: Apply the mapping to `InlinePlayer.tsx`**

In `frontend/src/components/InlinePlayer.tsx`:
- `import { focusRing } from "@/lib/theme";`
- Volume icon stays `text-teal-400` (dark-only context; passes).
- Subtext `text-zinc-500`/`text-gray-500` → `text-zinc-400`/`text-gray-600`.
- Download button: `disabled:text-zinc-500` → `disabled:text-zinc-400`; keep zinc-700 bg.
- Play button (teal): `bg-teal-600 hover:bg-teal-500` → `bg-teal-700 hover:bg-teal-600`; `disabled:text-zinc-500` → `disabled:text-zinc-400`.
- Stop button stays `bg-red-600 hover:bg-red-500` (passes).
- Append `` ` ${focusRing}` `` to all three button classNames.

- [ ] **Step 4: Apply the mapping to `App.tsx`**

In `frontend/src/App.tsx`:
- Error/info toast: `text-zinc-500`→`text-zinc-400` where present; the red toast `text-red-200`/`text-red-700` and amber `text-amber-800` stay (verify with the contrast tool if unsure — `red-700` on `red-50` and `amber-800` on `amber-50` both clear AA).
- Loading + backend-error screens: `text-zinc-400`/`text-zinc-500` → `text-zinc-300`/`text-zinc-400` for body copy; `text-zinc-500` footer → `text-zinc-400`.
- Cancel-export button (`bg-zinc-800 hover:bg-zinc-700`): append `` ` ${focusRing}` `` and `text-white` (already white).

- [ ] **Step 5: Apply the mapping to the sidebars + panels**

Apply the canonical mapping + focus rings to: `VoiceLibrary.tsx`, `ControlPanel.tsx`, `CachePanel.tsx`, `ThemeToggle.tsx`, `CfgScaleControl.tsx`, `ExaggerationControl.tsx`, `LanguageSelect.tsx`, `EngineSelector.tsx`, `SampleMenu.tsx`, `ImportExportMenu.tsx`, `ModeToggle.tsx`. For each:
- Add `import { focusRing } from "@/lib/theme";`
- Swap `text-zinc-500`→`text-zinc-400`, `text-gray-500`→`text-gray-600`, `text-gray-400`→`text-gray-600` (icon buttons), `text-teal-600`→`text-teal-700` (light text), `hover:text-red-600`→`hover:text-red-700`, solid `bg-teal-600 hover:bg-teal-500`→`bg-teal-700 hover:bg-teal-600`.
- Append `` ` ${focusRing}` `` to each `<button>` className.

- [ ] **Step 6: Apply the mapping to content + dialogs**

Apply the same to: `SegmentCard.tsx`, `SpeakerRoster.tsx`, `TtsEditor.tsx`, `GenerationDetailModal.tsx`, `Waveform.tsx`, `ModeChooser.tsx`, `VoiceMetaDialog.tsx`, `UploadVoiceDialog.tsx`, `InstallEngineDialog.tsx`, `DownloadModelDialog.tsx`. Same swaps + `${focusRing}` on buttons; for inputs/selects/textareas add `${focusRing}` alongside the existing `focus:border-teal-500`.

- [ ] **Step 7: Re-run the inventory grep to confirm zero stragglers**

Run the Step 1 grep again.
Expected: no remaining `text-gray-400`, `bg-amber-600`, `bg-teal-600` (solid buttons), `text-amber-100`. Remaining `text-teal-400` (dark accent) and `bg-red-600` are intentional — fine. If `bg-teal-600` survives only inside `bg-teal-600/20`-style translucent backgrounds (decorative), those are fine; only solid button backgrounds change.

- [ ] **Step 8: Typecheck + build + audit test**

Run: `npm run typecheck && npm test -- contrast && npm run build`
Expected: all PASS.

- [ ] **Step 9: Commit**

```bash
git add frontend/src
git commit -m "feat(a11y): WCAG AAA contrast fixes + focus rings across UI"
```

---

## Task 5: Playwright verification — Phase 1

**Files:** none (verification only).

- [ ] **Step 1: Ensure the dev environment is running**

Confirm `studio.py start --dev` is up (Vite :5173, backend :8880). If a Phase-1 backend restart isn't needed (it isn't — frontend only), just confirm Vite served the new build (HMR picks up edits).

- [ ] **Step 2: Screenshot the matrix**

Using the Playwright tools, for each width in {1024, 1280, 1440, 1600} and each theme in {dark, light}:
- `browser_resize` to the width (height 900).
- Toggle theme via the sidebar Appearance control.
- `browser_take_screenshot` (full page) of Podcast mode and Text-to-Voice mode.

- [ ] **Step 3: Inspect for contrast + focus**

Verify: meta text (timestamps, "Recent generations", device/dtype) is clearly legible in both themes; primary/Generate-all buttons read white-on-teal/amber cleanly; keyboard-tab shows a visible teal focus ring on buttons. Note any element still looking washed out and fix its class per the mapping, then re-commit.

- [ ] **Step 4: Commit any fixes**

```bash
git add frontend/src
git commit -m "fix(a11y): contrast tweaks found in Playwright review"
```

---

# PHASE 2 — Custom confirmation dialogs

## Task 6: ConfirmDialog component

**Files:**
- Create: `frontend/src/components/ConfirmDialog.tsx`

- [ ] **Step 1: Create the component**

Create `frontend/src/components/ConfirmDialog.tsx`:
```tsx
import { useEffect, useRef } from "react";
import { AlertTriangle } from "lucide-react";
import { focusRing } from "@/lib/theme";

export interface ConfirmDialogProps {
  open: boolean;
  isDark: boolean;
  title: string;
  message: string;
  confirmLabel?: string;
  cancelLabel?: string;
  danger?: boolean;
  onConfirm: () => void;
  onCancel: () => void;
}

export function ConfirmDialog({
  open,
  isDark,
  title,
  message,
  confirmLabel = "Confirm",
  cancelLabel = "Cancel",
  danger = false,
  onConfirm,
  onCancel,
}: ConfirmDialogProps) {
  const confirmRef = useRef<HTMLButtonElement | null>(null);
  const cardRef = useRef<HTMLDivElement | null>(null);

  // Focus the confirm button on open; restore focus on close.
  useEffect(() => {
    if (!open) return;
    const prev = document.activeElement as HTMLElement | null;
    confirmRef.current?.focus();
    return () => prev?.focus?.();
  }, [open]);

  // Keyboard: Esc cancels, Enter confirms, Tab is trapped within the card.
  useEffect(() => {
    if (!open) return;
    const onKey = (e: KeyboardEvent) => {
      if (e.key === "Escape") {
        e.preventDefault();
        onCancel();
      } else if (e.key === "Enter") {
        e.preventDefault();
        onConfirm();
      } else if (e.key === "Tab") {
        const card = cardRef.current;
        if (!card) return;
        const focusables = card.querySelectorAll<HTMLElement>("button");
        if (focusables.length === 0) return;
        const first = focusables[0];
        const last = focusables[focusables.length - 1];
        if (e.shiftKey && document.activeElement === first) {
          e.preventDefault();
          last.focus();
        } else if (!e.shiftKey && document.activeElement === last) {
          e.preventDefault();
          first.focus();
        }
      }
    };
    document.addEventListener("keydown", onKey);
    return () => document.removeEventListener("keydown", onKey);
  }, [open, onCancel, onConfirm]);

  if (!open) return null;

  const surface = isDark ? "bg-zinc-900" : "bg-white";
  const border = isDark ? "border-zinc-800" : "border-gray-200";
  const titleColor = isDark ? "text-zinc-100" : "text-gray-900";
  const msgColor = isDark ? "text-zinc-300" : "text-gray-700";
  const cancelColor = isDark
    ? "text-zinc-300 hover:text-white"
    : "text-gray-700 hover:text-gray-900";
  const confirmColor = danger
    ? "bg-red-600 hover:bg-red-500 text-white"
    : "bg-teal-700 hover:bg-teal-600 text-white";

  return (
    <div
      className="fixed inset-0 z-50 flex items-center justify-center bg-black/60 p-4"
      onClick={onCancel}
    >
      <div
        ref={cardRef}
        role="alertdialog"
        aria-modal="true"
        aria-labelledby="confirm-title"
        aria-describedby="confirm-message"
        className={`${surface} ${border} border rounded-xl shadow-xl w-full max-w-md p-6`}
        onClick={(e) => e.stopPropagation()}
      >
        <div className="flex items-center gap-2 mb-2">
          {danger && <AlertTriangle className="w-5 h-5 text-red-500 shrink-0" />}
          <h2 id="confirm-title" className={`text-lg font-semibold ${titleColor}`}>
            {title}
          </h2>
        </div>
        <p id="confirm-message" className={`text-sm ${msgColor}`}>
          {message}
        </p>
        <div className="mt-6 flex items-center justify-end gap-2">
          <button
            type="button"
            onClick={onCancel}
            className={`px-4 py-2 text-sm rounded-lg transition-colors ${cancelColor} ${focusRing}`}
          >
            {cancelLabel}
          </button>
          <button
            ref={confirmRef}
            type="button"
            onClick={onConfirm}
            className={`px-4 py-2 text-sm rounded-lg font-medium transition-colors ${confirmColor} ${focusRing}`}
          >
            {confirmLabel}
          </button>
        </div>
      </div>
    </div>
  );
}
```

- [ ] **Step 2: Typecheck**

Run: `npm run typecheck`
Expected: PASS.

- [ ] **Step 3: Commit**

```bash
git add frontend/src/components/ConfirmDialog.tsx
git commit -m "feat(confirm): styled ConfirmDialog with focus trap + keyboard"
```

---

## Task 7: ConfirmProvider + useConfirm (TDD)

**Files:**
- Create: `frontend/src/components/ConfirmProvider.tsx`
- Create: `frontend/src/components/ConfirmProvider.test.tsx`

- [ ] **Step 1: Write the failing test**

Create `frontend/src/components/ConfirmProvider.test.tsx`:
```tsx
import { describe, it, expect } from "vitest";
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { ConfirmProvider, useConfirm } from "./ConfirmProvider";

function Harness({ onResult }: { onResult: (v: boolean) => void }) {
  const confirm = useConfirm();
  return (
    <button
      onClick={async () => {
        const ok = await confirm({ title: "Delete?", message: "Sure?" });
        onResult(ok);
      }}
    >
      trigger
    </button>
  );
}

function setup() {
  const results: boolean[] = [];
  render(
    <ConfirmProvider isDark={false}>
      <Harness onResult={(v) => results.push(v)} />
    </ConfirmProvider>,
  );
  return results;
}

describe("useConfirm", () => {
  it("resolves true when the confirm button is clicked", async () => {
    const user = userEvent.setup();
    const results = setup();
    await user.click(screen.getByText("trigger"));
    expect(screen.getByRole("alertdialog")).toBeInTheDocument();
    await user.click(screen.getByText("Confirm"));
    expect(results).toEqual([true]);
  });

  it("resolves false when the cancel button is clicked", async () => {
    const user = userEvent.setup();
    const results = setup();
    await user.click(screen.getByText("trigger"));
    await user.click(screen.getByText("Cancel"));
    expect(results).toEqual([false]);
  });

  it("resolves false on Escape", async () => {
    const user = userEvent.setup();
    const results = setup();
    await user.click(screen.getByText("trigger"));
    await user.keyboard("{Escape}");
    expect(results).toEqual([false]);
  });

  it("closes the dialog after a decision", async () => {
    const user = userEvent.setup();
    setup();
    await user.click(screen.getByText("trigger"));
    await user.click(screen.getByText("Confirm"));
    expect(screen.queryByRole("alertdialog")).not.toBeInTheDocument();
  });
});
```

- [ ] **Step 2: Run the test to verify it fails**

Run: `npm test -- ConfirmProvider`
Expected: FAIL with module-not-found for `./ConfirmProvider`.

- [ ] **Step 3: Implement the provider**

Create `frontend/src/components/ConfirmProvider.tsx`:
```tsx
import { createContext, useCallback, useContext, useMemo, useRef, useState } from "react";
import { ConfirmDialog } from "./ConfirmDialog";

export interface ConfirmOptions {
  title: string;
  message: string;
  confirmLabel?: string;
  cancelLabel?: string;
  danger?: boolean;
}

type ConfirmFn = (opts: ConfirmOptions) => Promise<boolean>;

const ConfirmContext = createContext<ConfirmFn | null>(null);

interface State extends ConfirmOptions {
  open: boolean;
}

const CLOSED: State = { open: false, title: "", message: "" };

export function ConfirmProvider({
  isDark,
  children,
}: {
  isDark: boolean;
  children: React.ReactNode;
}) {
  const [state, setState] = useState<State>(CLOSED);
  const resolverRef = useRef<((v: boolean) => void) | null>(null);

  const confirm = useCallback<ConfirmFn>((opts) => {
    return new Promise<boolean>((resolve) => {
      resolverRef.current = resolve;
      setState({ ...opts, open: true });
    });
  }, []);

  const settle = useCallback((value: boolean) => {
    resolverRef.current?.(value);
    resolverRef.current = null;
    setState(CLOSED);
  }, []);

  const value = useMemo(() => confirm, [confirm]);

  return (
    <ConfirmContext.Provider value={value}>
      {children}
      <ConfirmDialog
        open={state.open}
        isDark={isDark}
        title={state.title}
        message={state.message}
        confirmLabel={state.confirmLabel}
        cancelLabel={state.cancelLabel}
        danger={state.danger}
        onConfirm={() => settle(true)}
        onCancel={() => settle(false)}
      />
    </ConfirmContext.Provider>
  );
}

export function useConfirm(): ConfirmFn {
  const ctx = useContext(ConfirmContext);
  if (!ctx) throw new Error("useConfirm must be used within <ConfirmProvider>");
  return ctx;
}
```

- [ ] **Step 4: Run the test to verify it passes**

Run: `npm test -- ConfirmProvider`
Expected: PASS (4 tests). The `isDark` prop drives dialog theming; tests use `false`.

- [ ] **Step 5: Typecheck**

Run: `npm run typecheck`
Expected: PASS.

- [ ] **Step 6: Commit**

```bash
git add frontend/src/components/ConfirmProvider.tsx frontend/src/components/ConfirmProvider.test.tsx
git commit -m "feat(confirm): promise-based useConfirm provider"
```

---

## Task 8: Mount provider + wire the 3 call sites

The provider needs the current `isDark`. `App` owns theme state, so the provider must wrap the part of the tree that consumes `useConfirm` AND receive `isDark`. Wrap `App`'s returned tree internally (simplest, keeps theme in one place).

**Files:**
- Modify: `frontend/src/App.tsx`
- Modify: `frontend/src/components/CachePanel.tsx`
- Modify: `frontend/src/components/VoiceLibrary.tsx`

- [ ] **Step 1: Wrap App's tree with ConfirmProvider**

In `frontend/src/App.tsx`:
- Add import: `import { ConfirmProvider } from "@/components/ConfirmProvider";`
- The main return (the `<div className="flex h-screen …">`) is wrapped so the provider sees `isDark`. Since `isDark` is computed inside `App`, wrap the returned JSX:
```tsx
  return (
    <ConfirmProvider isDark={isDark}>
      <div className={`flex h-screen overflow-hidden ${isDark ? "bg-zinc-950" : "bg-gray-50"}`}>
        {/* …existing children unchanged… */}
      </div>
    </ConfirmProvider>
  );
```
(Leave the early-return loading/error screens unwrapped — they have no confirm consumers.)

- [ ] **Step 2: Wire Clear-cache + delete-generation in CachePanel**

In `frontend/src/components/CachePanel.tsx`:
- Add import: `import { useConfirm } from "./ConfirmProvider";`
- `useCacheData` currently calls `confirm(...)` directly. Move the confirmation OUT of the hook and into the components that have provider context (the hook isn't a component and can't call `useConfirm`). Change `onClear` in `useCacheData` to NOT prompt (just clear):
```ts
  const onClear = async () => {
    setBusy(true);
    try {
      await clearCache();
      await refresh();
    } finally {
      setBusy(false);
    }
  };
```
- In `CacheBody`, get the confirm fn and gate the actions:
```tsx
export function CacheBody({ isDark, data, busy, onClear, onDelete }: BodyProps) {
  const confirm = useConfirm();
  // …existing state…

  const handleClear = async () => {
    stopSharedAudio();
    const ok = await confirm({
      title: "Clear all generations?",
      message: "This deletes every cached clip. Next synthesis will run the model again.",
      confirmLabel: "Clear all",
      danger: true,
    });
    if (ok) onClear();
  };

  const handleDelete = async (e: React.MouseEvent, hash: string) => {
    e.stopPropagation();
    const ok = await confirm({
      title: "Delete this generation?",
      message: "This removes the cached clip. It can be regenerated later.",
      confirmLabel: "Delete",
      danger: true,
    });
    if (!ok) return;
    stopSharedAudio(hash);
    await onDelete(hash);
  };
  // …rest unchanged; handleClear/handleDelete already wired to the buttons…
```
- Note: the legacy standalone `CachePanel` popover (bottom of the file) also renders `CacheBody`; it now requires a `ConfirmProvider` ancestor. Since the live UI mounts `CacheBody` via `ControlPanel` inside the provider, this is fine. The standalone `CachePanel` is unused in the live tree — leave as-is.

- [ ] **Step 3: Wire delete-voice in VoiceLibrary**

In `frontend/src/components/VoiceLibrary.tsx`:
- Add import: `import { useConfirm } from "./ConfirmProvider";`
- Inside the component: `const confirm = useConfirm();`
- Replace the delete button's handler:
```tsx
                <button
                  type="button"
                  onClick={async (e) => {
                    e.stopPropagation();
                    const ok = await confirm({
                      title: `Delete "${v.name}"?`,
                      message: "This permanently removes the uploaded voice.",
                      confirmLabel: "Delete",
                      danger: true,
                    });
                    if (ok) void onRemoveVoice(v.id);
                  }}
                  className={`p-1 ${danger} ${focusRing}`}
                  title="Delete"
                >
                  <Trash2 className="w-3.5 h-3.5" />
                </button>
```
(`focusRing` import was added in Task 4 Step 5.)

- [ ] **Step 4: Typecheck + build + tests**

Run: `npm run typecheck && npm test && npm run build`
Expected: all PASS.

- [ ] **Step 5: Commit**

```bash
git add frontend/src
git commit -m "feat(confirm): wire styled confirm into clear-cache, delete-generation, delete-voice"
```

---

## Task 9: Playwright verification — Phase 2

**Files:** none.

- [ ] **Step 1: Exercise each confirm**

In the running dev app (dark + light), trigger: Clear-all (trash icon in Recent generations), per-row delete, and delete-voice (My voices row). For each: screenshot the dialog open; click Cancel and confirm the item survives; re-open and click Confirm and verify the item is removed. Press Esc on an open dialog and confirm it cancels.

- [ ] **Step 2: Keyboard check**

Tab into a dialog: confirm focus lands on the confirm button, Tab cycles within the dialog only, Enter confirms, Esc cancels.

- [ ] **Step 3: Commit any fixes**

```bash
git add frontend/src
git commit -m "fix(confirm): adjustments from Playwright review"
```

---

# PHASE 3 — Responsive (shrink + auto-collapse, ≥1024px)

## Task 10: Width-tier + panel-default helpers (TDD)

**Files:**
- Create: `frontend/src/lib/layout.ts`
- Create: `frontend/src/lib/layout.test.ts`

- [ ] **Step 1: Write the failing test**

Create `frontend/src/lib/layout.test.ts`:
```ts
import { describe, it, expect } from "vitest";
import {
  widthTier,
  defaultVoiceLibraryOpen,
  defaultControlPanelOpen,
  showNarrowBanner,
} from "./layout";

describe("widthTier", () => {
  it("classifies widths into tiers", () => {
    expect(widthTier(1600)).toBe("xl");
    expect(widthTier(1440)).toBe("xl");
    expect(widthTier(1300)).toBe("lg");
    expect(widthTier(1180)).toBe("lg");
    expect(widthTier(1100)).toBe("md");
    expect(widthTier(1024)).toBe("md");
    expect(widthTier(900)).toBe("sm");
  });
});

describe("panel defaults", () => {
  it("voice library open for xl/lg, collapsed for md/sm", () => {
    expect(defaultVoiceLibraryOpen(1440)).toBe(true);
    expect(defaultVoiceLibraryOpen(1200)).toBe(true);
    expect(defaultVoiceLibraryOpen(1100)).toBe(false);
    expect(defaultVoiceLibraryOpen(800)).toBe(false);
  });
  it("control panel open only for xl", () => {
    expect(defaultControlPanelOpen(1500)).toBe(true);
    expect(defaultControlPanelOpen(1300)).toBe(false);
    expect(defaultControlPanelOpen(1024)).toBe(false);
  });
});

describe("showNarrowBanner", () => {
  it("is true below 1024", () => {
    expect(showNarrowBanner(1023)).toBe(true);
    expect(showNarrowBanner(1024)).toBe(false);
    expect(showNarrowBanner(1400)).toBe(false);
  });
});
```

- [ ] **Step 2: Run the test to verify it fails**

Run: `npm test -- layout`
Expected: FAIL with module-not-found.

- [ ] **Step 3: Implement the helpers**

Create `frontend/src/lib/layout.ts`:
```ts
/**
 * Pure layout helpers: map a viewport width to a tier and derive the
 * FIRST-LOAD default open/collapsed state of each side panel. Explicit user
 * toggles (persisted in localStorage) always override these defaults.
 *
 * Tiers (px):  xl >= 1440 | lg 1180–1439 | md 1024–1179 | sm < 1024
 */
export type WidthTier = "xl" | "lg" | "md" | "sm";

export function widthTier(w: number): WidthTier {
  if (w >= 1440) return "xl";
  if (w >= 1180) return "lg";
  if (w >= 1024) return "md";
  return "sm";
}

/** Voices are primary — keep open until the middle column gets tight. */
export function defaultVoiceLibraryOpen(w: number): boolean {
  const t = widthTier(w);
  return t === "xl" || t === "lg";
}

/** Controls are secondary — only open by default on the widest tier. */
export function defaultControlPanelOpen(w: number): boolean {
  return widthTier(w) === "xl";
}

/** Below the supported floor (1024px) we show a soft notice. */
export function showNarrowBanner(w: number): boolean {
  return w < 1024;
}
```

- [ ] **Step 4: Run the test to verify it passes**

Run: `npm test -- layout`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add frontend/src/lib/layout.ts frontend/src/lib/layout.test.ts
git commit -m "test(layout): width-tier + panel-default helpers"
```

---

## Task 11: useViewportWidth hook

**Files:**
- Create: `frontend/src/hooks/useViewportWidth.ts`

- [ ] **Step 1: Create the hook**

Create `frontend/src/hooks/useViewportWidth.ts`:
```ts
import { useEffect, useState } from "react";

/** Reactive viewport width (px). Updates on resize. SSR-safe (returns 1440). */
export function useViewportWidth(): number {
  const [width, setWidth] = useState<number>(() =>
    typeof window === "undefined" ? 1440 : window.innerWidth,
  );

  useEffect(() => {
    const onResize = () => setWidth(window.innerWidth);
    window.addEventListener("resize", onResize);
    onResize();
    return () => window.removeEventListener("resize", onResize);
  }, []);

  return width;
}
```

- [ ] **Step 2: Typecheck**

Run: `npm run typecheck`
Expected: PASS.

- [ ] **Step 3: Commit**

```bash
git add frontend/src/hooks/useViewportWidth.ts
git commit -m "feat(layout): useViewportWidth hook"
```

---

## Task 12: VoiceLibrary collapse + width-default

`ControlPanel` already collapses via `localStorage` key `vs.controlPanel.open` (stored `"true"` = open, `"false"` = collapsed; its first-load fallback is `window.innerWidth < 1200`). Mirror that in `VoiceLibrary`, but drive the fallback from `defaultVoiceLibraryOpen`.

**Files:**
- Modify: `frontend/src/components/VoiceLibrary.tsx`

- [ ] **Step 1: Add collapse state + imports**

In `frontend/src/components/VoiceLibrary.tsx`, add imports:
```tsx
import { useEffect, useState } from "react";
import { Mic2, PanelLeftClose, PanelLeftOpen, Pencil, Plus, Trash2, Volume2, Waves } from "lucide-react";
import { focusRing } from "@/lib/theme";
import { defaultVoiceLibraryOpen } from "@/lib/layout";
```
(Keep existing imports; merge the lucide list. `useState` may already be imported — dedupe.)

Add near the top of the component body:
```tsx
  const LS_KEY = "vs.voiceLibrary.open";
  const [open, setOpen] = useState<boolean>(() => {
    const stored = localStorage.getItem(LS_KEY);
    if (stored !== null) return stored === "true";
    return typeof window !== "undefined"
      ? defaultVoiceLibraryOpen(window.innerWidth)
      : true;
  });
  useEffect(() => {
    localStorage.setItem(LS_KEY, open ? "true" : "false");
  }, [open]);
```

- [ ] **Step 2: Render the collapsed rail**

Before the existing `return (`, add an early return for the collapsed state:
```tsx
  if (!open) {
    return (
      <aside
        className={`w-12 shrink-0 z-10 border-r flex flex-col items-center pt-4 gap-3 transition-colors ${surface} ${border}`}
      >
        <div className="w-9 h-9 rounded-lg bg-teal-600/20 flex items-center justify-center">
          <Waves className="w-5 h-5 text-teal-400" />
        </div>
        <button
          type="button"
          onClick={() => setOpen(true)}
          className={`p-2 rounded-lg transition-colors ${iconBtn} ${focusRing}`}
          title="Open voice library"
        >
          <PanelLeftOpen className="w-5 h-5" />
        </button>
        <button
          type="button"
          onClick={onThemeToggle}
          className={`p-2 rounded-lg transition-colors ${iconBtn} ${focusRing}`}
          title="Toggle theme"
        >
          {isDark ? <Sun className="w-5 h-5" /> : <Moon className="w-5 h-5" />}
        </button>
      </aside>
    );
  }
```
Add `Moon, Sun` to the lucide import for the rail theme toggle.

- [ ] **Step 3: Add a collapse button to the open header**

In the open-state header (the `<div className="p-5 border-b flex items-center gap-3 …">`), append a collapse button at the end so the header becomes `justify-between`:
```tsx
      <div className={`p-5 border-b flex items-center gap-3 ${border}`}>
        <div className="w-9 h-9 rounded-lg bg-teal-600/20 flex items-center justify-center">
          <Waves className="w-5 h-5 text-teal-400" />
        </div>
        <div className="min-w-0 flex-1">
          <h1 className={`font-semibold text-sm truncate ${isDark ? "text-white" : "text-gray-900"}`}>
            Voice Studio by MSR
          </h1>
          <p className={`text-xs truncate ${heading}`}>Local · {config?.model_id ?? "—"}</p>
        </div>
        <button
          type="button"
          onClick={() => setOpen(false)}
          className={`p-1 rounded transition-colors ${iconBtn} ${focusRing}`}
          title="Collapse voice library"
        >
          <PanelLeftClose className="w-4 h-4" />
        </button>
      </div>
```

- [ ] **Step 4: Typecheck + build**

Run: `npm run typecheck && npm run build`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add frontend/src/components/VoiceLibrary.tsx
git commit -m "feat(layout): collapsible VoiceLibrary with width-aware default"
```

---

## Task 13: Align ControlPanel default with width tiers

**Files:**
- Modify: `frontend/src/components/ControlPanel.tsx`

- [ ] **Step 1: Use the shared default helper**

In `frontend/src/components/ControlPanel.tsx`:
- Add import: `import { defaultControlPanelOpen } from "@/lib/layout";`
- Replace the `collapsed` initializer's width fallback. Current code:
```tsx
  const [collapsed, setCollapsed] = useState<boolean>(() => {
    const stored = localStorage.getItem(LS_KEY);
    if (stored !== null) return stored === "false";
    return typeof window !== "undefined" ? window.innerWidth < 1200 : false;
  });
```
becomes:
```tsx
  const [collapsed, setCollapsed] = useState<boolean>(() => {
    const stored = localStorage.getItem(LS_KEY);
    if (stored !== null) return stored === "false";
    return typeof window !== "undefined"
      ? !defaultControlPanelOpen(window.innerWidth)
      : false;
  });
```
(Keep the existing LS scheme: stored `"false"` = collapsed. Only the no-stored-value fallback changes.)

- [ ] **Step 2: Add focus ring to the expand/collapse buttons**

Ensure the collapse toggle and the collapsed-strip expand button include `${focusRing}` (from Task 4 Step 5 import). Verify the import exists; if not, add `import { focusRing } from "@/lib/theme";`.

- [ ] **Step 3: Typecheck + build**

Run: `npm run typecheck && npm run build`
Expected: PASS.

- [ ] **Step 4: Commit**

```bash
git add frontend/src/components/ControlPanel.tsx
git commit -m "feat(layout): align ControlPanel default with width tiers"
```

---

## Task 14: Container-query toolbar + player labels

**Files:**
- Modify: `frontend/tailwind.config.js`
- Modify: `frontend/src/App.tsx`
- Modify: `frontend/src/components/MiddleToolbar.tsx`
- Modify: `frontend/src/components/InlinePlayer.tsx`
- Delete (if unused): `frontend/src/hooks/useIsNarrow.ts`

- [ ] **Step 1: Install + register the container-queries plugin**

Run (in `frontend/`):
```bash
npm install -D @tailwindcss/container-queries
```
Then edit `frontend/tailwind.config.js`:
```js
/** @type {import('tailwindcss').Config} */
import containerQueries from "@tailwindcss/container-queries";

export default {
  content: ["./index.html", "./src/**/*.{ts,tsx}"],
  darkMode: "class",
  theme: { extend: {} },
  plugins: [containerQueries],
};
```

- [ ] **Step 2: Mark the middle column as a container**

In `frontend/src/App.tsx`, add `@container` to the `<main>`:
```tsx
      <main className="flex-1 flex flex-col min-w-0 @container">
```

- [ ] **Step 3: Replace viewport-based labels with container queries in MiddleToolbar**

In `frontend/src/components/MiddleToolbar.tsx`:
- Remove `import { useIsNarrow } from "@/hooks/useIsNarrow";` and the `const narrow = useIsNarrow();` line.
- Remove the `addLabel`/`generateLabel` `narrow ? … : …` constructs. Instead render icon + a label `<span>` that hides below a container width. Add-segment button content:
```tsx
            <Plus className="w-5 h-5" />
            <span className="@max-[1100px]:hidden">Add Segment</span>
```
- Generate-all button content:
```tsx
            <RefreshCw className="w-4 h-4" />
            <span className="@max-[1100px]:hidden">Generate All</span>
            {validCount > 0 && (
              <span
                className={`text-xs ml-1 ${
                  cachedCount === validCount ? "text-teal-100" : "text-amber-100"
                }`}
              >
                {cachedCount}/{validCount}
              </span>
            )}
```
(The count chip stays visible at all widths; only the word labels collapse. Adjust `text-amber-100`→keep as count-on-amber readability is acceptable, or use `text-white` per Task 4.)

- [ ] **Step 4: Replace viewport-based labels with container queries in InlinePlayer**

In `frontend/src/components/InlinePlayer.tsx`:
- Remove `useIsNarrow` import + usage.
- The "Full podcast" title: wrap in `<span className="@max-[900px]:hidden">`. Replace the three `narrow ? <Icon/> : <>…</>` label builders with icon + `<span className="@max-[1100px]:hidden">…</span>`:
```tsx
  const downloadLabel = (
    <>
      <FileAudio className="w-5 h-5" />
      <span className="@max-[1100px]:hidden">Download Audio</span>
    </>
  );
  const playLabel = (
    <>
      <Play className="w-5 h-5" />
      <span className="@max-[1100px]:hidden">Play Podcast</span>
    </>
  );
  const stopLabel = (
    <>
      <Square className="w-5 h-5" />
      <span className="@max-[1100px]:hidden">Stop Podcast</span>
    </>
  );
```
- For the subtext block, replace `{!narrow && (<p>Full podcast</p>)}` with the always-rendered title wrapped in the hide-span above.

- [ ] **Step 5: Remove the now-unused useIsNarrow hook**

Run (from `frontend/`):
```bash
grep -rn "useIsNarrow" src/ || echo "no consumers"
```
Expected: "no consumers" (or only the file itself). If clean, delete `frontend/src/hooks/useIsNarrow.ts`. If any other consumer exists, leave the file and convert that consumer too before deleting.

- [ ] **Step 6: Typecheck + build**

Run: `npm run typecheck && npm run build`
Expected: PASS.

- [ ] **Step 7: Commit**

```bash
git add frontend/package.json frontend/package-lock.json frontend/tailwind.config.js frontend/src
git rm frontend/src/hooks/useIsNarrow.ts 2>/dev/null || true
git commit -m "feat(layout): container-query toolbar/player labels (no more premature wrapping)"
```

---

## Task 15: Too-narrow banner + size scaling

**Files:**
- Create: `frontend/src/components/TooNarrowBanner.tsx`
- Modify: `frontend/src/App.tsx`

- [ ] **Step 1: Create the banner**

Create `frontend/src/components/TooNarrowBanner.tsx`:
```tsx
import { useState } from "react";
import { X } from "lucide-react";
import { focusRing } from "@/lib/theme";

const SS_KEY = "vs.narrowBannerDismissed";

export function TooNarrowBanner({ isDark }: { isDark: boolean }) {
  const [dismissed, setDismissed] = useState<boolean>(
    () => sessionStorage.getItem(SS_KEY) === "true",
  );
  if (dismissed) return null;

  const wrap = isDark
    ? "bg-amber-900/30 border-amber-600/40 text-amber-100"
    : "bg-amber-50 border-amber-300 text-amber-800";

  return (
    <div className={`flex items-center justify-between gap-3 px-4 py-2 border-b text-sm ${wrap}`}>
      <span>Voice Studio is optimized for screens at least 1024px wide.</span>
      <button
        type="button"
        onClick={() => {
          sessionStorage.setItem(SS_KEY, "true");
          setDismissed(true);
        }}
        className={`p-1 rounded shrink-0 ${focusRing}`}
        title="Dismiss"
      >
        <X className="w-4 h-4" />
      </button>
    </div>
  );
}
```

- [ ] **Step 2: Render the banner when below the floor**

In `frontend/src/App.tsx`:
- Add imports:
```tsx
import { TooNarrowBanner } from "@/components/TooNarrowBanner";
import { useViewportWidth } from "@/hooks/useViewportWidth";
import { showNarrowBanner } from "@/lib/layout";
```
- In the component body add: `const viewportWidth = useViewportWidth();`
- Render the banner at the top of the middle column, just inside `<main … @container>`, before `<MiddleToolbar …>`:
```tsx
        {showNarrowBanner(viewportWidth) && <TooNarrowBanner isDark={isDark} />}
        <MiddleToolbar … />
```

- [ ] **Step 3: Modest size scaling in the toolbar**

In `frontend/src/components/MiddleToolbar.tsx`, soften padding at narrow container widths on the outer wrapper:
```tsx
    <div
      className={`flex flex-wrap items-center justify-between gap-2 @[1200px]:gap-3 p-3 @[1200px]:p-4 border-b ${
        isDark ? "bg-zinc-900 border-zinc-800" : "bg-white border-gray-200"
      }`}
    >
```
(Keep `flex-wrap` as a final safety net; with container-query labels it should no longer trigger above 1024px.)

- [ ] **Step 4: Typecheck + build + full test run**

Run: `npm run typecheck && npm test && npm run build`
Expected: all PASS.

- [ ] **Step 5: Commit**

```bash
git add frontend/src
git commit -m "feat(layout): too-narrow banner + responsive size scaling"
```

---

## Task 16: Playwright verification — Phase 3

**Files:** none.

- [ ] **Step 1: Resize matrix**

For widths {1600, 1440, 1300, 1180, 1100, 1024, 960} in both themes:
- `browser_resize` then screenshot Podcast + TTS modes.
- Verify: **no toolbar/player wrapping** at any width ≥1024; panels auto-collapse per the tier table (xl: both open; lg: controls collapsed; md: both collapsed; sm: both collapsed + banner).

- [ ] **Step 2: Toggle persistence**

Manually open/collapse each panel, reload the page, confirm the explicit choice persists and overrides the width default.

- [ ] **Step 3: Banner behavior**

At 960px confirm the banner appears; dismiss it; confirm it stays dismissed for the session (reload within the session keeps it dismissed per sessionStorage — note: a fresh tab shows it again, which is intended).

- [ ] **Step 4: Commit any fixes**

```bash
git add frontend/src
git commit -m "fix(layout): adjustments from Playwright review"
```

---

## Final verification (all phases)

- [ ] **Step 1: Full frontend gate**

Run (in `frontend/`): `npm run typecheck && npm test && npm run build`
Expected: typecheck clean, all Vitest suites pass, build succeeds.

- [ ] **Step 2: Backend untouched**

Run (in `backend/`): `python -m pytest tests/ -q`
Expected: green (this plan made no backend changes; this confirms no accidental coupling).

- [ ] **Step 3: Dispatch final code review**

Per subagent-driven-development, dispatch a final code-reviewer over the whole branch before finishing.

- [ ] **Step 4: Finish the branch**

Use superpowers:finishing-a-development-branch.

---

## Self-Review notes (plan author)

- **Spec coverage:** WCAG audit+fixes → Tasks 2–5; semantic tokens (fork A) → Task 3; focus rings → Tasks 3–4; confirm dialogs on 3 data-loss sites → Tasks 6–9; shrink+auto-collapse → Tasks 12–13; container queries (fork B) → Task 14; too-narrow banner + size scaling → Task 15; 1024px floor → Tasks 10/15. All spec sections mapped.
- **Accent-button AAA exception:** explicitly encoded — the audit test (Task 2) asserts teal/amber/red buttons at AA (4.5:1), not AAA, matching the spec's flagged trade-off.
- **No-test-runner gap:** resolved by Task 1 (Vitest harness) before any TDD task.
- **Type consistency:** `useConfirm()`/`ConfirmOptions`/`confirm({title,message,danger})` signatures match across Tasks 7–8; `widthTier`/`defaultVoiceLibraryOpen`/`defaultControlPanelOpen`/`showNarrowBanner` names match across Tasks 10–15; `focusRing`/`theme.*` names match Task 3 definitions.
