# UI Redesign Phase 1 — Three-Column Shell — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Reorganize the VibeVoice-era 2-zone UI (fixed left sidebar + fixed top action bar + fixed bottom footer) into a 3-column layout — voice library (left) · content (middle) · controls (right) — with zero behavior change and zero restyle.

**Architecture:** Extract the existing left sidebar into a voices-only `VoiceLibrary`; move the speaker roster to the top of the middle column as `SpeakerRoster`; build a `MiddleToolbar` (Add/Generate/Samples/Import-Export) and an inline player at the middle column's bottom; build a persistent+collapsible right `ControlPanel` (engine selector + CFG/exaggeration sliders + theme + device info). `App.tsx` becomes a flex row of three columns and keeps every existing handler/state untouched — only the JSX placement moves.

**Tech Stack:** React 18 + TypeScript, Vite, Tailwind CSS, lucide-react icons. Verified by `npm run typecheck` + `npm run build` + Playwright (no JS unit-test runner in this repo).

**Constraints (from spec):** Structural only — reuse existing Tailwind classes verbatim; do not change colors/spacing/fonts. Playwright verification at the end.

---

## File Structure

New components under `frontend/src/components/`:
- `VoiceLibrary.tsx` — left column: header (logo + model id), Built-in voices, My voices (+upload), the two dialogs. Extracted from `Sidebar.tsx`.
- `SpeakerRoster.tsx` — middle top: the `SPEAKERS` section + `SpeakerRow` (incl. OmniVoice Clone/Design/Auto). Extracted from `Sidebar.tsx`.
- `MiddleToolbar.tsx` — middle top: Add Segment, Generate All, Samples, Import/Export. Extracted from `ActionBar.tsx` (minus EngineSelector + Settings).
- `InlinePlayer.tsx` — middle bottom: Full podcast + Download Audio + Play Podcast. Extracted from `PlayerFooter.tsx`.
- `ControlPanel.tsx` — right column: EngineSelector + CFG/exaggeration sliders + ThemeToggle + device/dtype/sr. Collapsible.

Modified:
- `App.tsx` — three-column flex layout; rewire props; remove the `actionBarH`/`playerFooterH` measuring state.

Removed once unreferenced:
- `Sidebar.tsx`, `ActionBar.tsx`, `PlayerFooter.tsx`.

Reused as-is (do not modify): `SegmentCard.tsx`, `EngineSelector.tsx`, `SampleMenu.tsx`, `ImportExportMenu.tsx`, `CfgScaleControl.tsx`, `ThemeToggle.tsx`, `UploadVoiceDialog.tsx`, `VoiceMetaDialog.tsx`, `InstallEngineDialog.tsx`, `DownloadModelDialog.tsx`, `SettingsMenu.tsx` (its slider bodies are reused; see Task 5), `store.ts`, all hooks, `lib/*`.

---

## Task 1: Extract `VoiceLibrary` (left column)

**Files:**
- Create: `frontend/src/components/VoiceLibrary.tsx`
- Reference: `frontend/src/components/Sidebar.tsx:65-230` (the `<aside>` markup, MINUS the Speakers section and MINUS the footer's theme toggle)

- [ ] **Step 1: Create `VoiceLibrary.tsx`**

Copy the current `Sidebar`'s outer `<aside>` shell, header block, the **Built-in voices** section, and the **My voices** section (the `supportsVoiceCloning &&` block), plus the `UploadVoiceDialog` + `VoiceMetaDialog` at the bottom. Drop the Speakers section and drop the `ThemeToggle` + device info from the footer (those move to `ControlPanel`). Keep all Tailwind classes identical.

Props interface:
```tsx
interface Props {
  voices: Voice[];
  config: ConfigResponse | null;
  theme: "light" | "dark";
  onUploadVoice: (file: File, meta: VoiceMetadata) => Promise<unknown>;
  onRemoveVoice: (id: string) => Promise<void>;
  onUpdateVoiceMeta: (voiceId: string, meta: VoiceMetadata) => Promise<unknown>;
  supportsVoiceCloning: boolean;
}
```

Keep the same local state (`uploadOpen`, `editingVoice`) and the same `builtins`/`uploads` derivations and the same surface/border/heading token consts. The root stays `<aside class="w-80 ...">` but change `fixed top-0 left-0 bottom-0` to a flex-friendly `h-screen shrink-0` (the parent flex row positions it; see Task 6).

- [ ] **Step 2: Typecheck**

Run: `cd frontend && npm run typecheck`
Expected: PASS (VoiceLibrary compiles; it's not yet imported, which is fine).

- [ ] **Step 3: Commit**

```bash
git add frontend/src/components/VoiceLibrary.tsx
git commit -m "feat(ui): extract VoiceLibrary from Sidebar (voices only)"
```

---

## Task 2: Extract `SpeakerRoster` (middle top)

**Files:**
- Create: `frontend/src/components/SpeakerRoster.tsx`
- Reference: `frontend/src/components/Sidebar.tsx:82-113` (Speakers section) + `Sidebar.tsx:234-375` (the entire `SpeakerRow` function + its OmniVoice branch).

- [ ] **Step 1: Create `SpeakerRoster.tsx`**

Move the `SpeakerRow` function verbatim (it already encapsulates name/voice-select/OmniVoice toggle/design chips). Wrap the speakers list + the section header + the add button in a `SpeakerRoster` component. Reuse `DESIGN_CHIPS`, `appendDesignChip`, `effectiveMode`, `OmniMode` imports from `@/lib/omnivoice`. Keep all Tailwind classes identical. Container styling: a rounded panel matching the existing section (no new colors).

Props interface:
```tsx
interface Props {
  speakers: Speaker[];
  voices: Voice[];
  isDark: boolean;
  activeEngine: string | null;
  onAddSpeaker: () => void;
  onUpdateSpeaker: (id: string, patch: Partial<Speaker>) => void;
  onRemoveSpeaker: (id: string) => void;
  onSetSpeakerVoice: (speakerId: string, voiceId: string) => void;
}
```

- [ ] **Step 2: Typecheck**

Run: `cd frontend && npm run typecheck`
Expected: PASS.

- [ ] **Step 3: Commit**

```bash
git add frontend/src/components/SpeakerRoster.tsx
git commit -m "feat(ui): extract SpeakerRoster from Sidebar (incl. OmniVoice modes)"
```

---

## Task 3: Extract `MiddleToolbar`

**Files:**
- Create: `frontend/src/components/MiddleToolbar.tsx`
- Reference: `frontend/src/components/ActionBar.tsx` (keep Add Segment + Generate All buttons, `SampleMenu`, `ImportExportMenu`; DROP `EngineSelector` + `SettingsMenu` + the `ResizeObserver`/`onHeightChange` plumbing + `useIsNarrow` height logic — keep `useIsNarrow` only for the icon/label collapse).

- [ ] **Step 1: Create `MiddleToolbar.tsx`**

A non-fixed bar (the middle column makes it sticky via Task 6). Keep the `Add Segment` (teal) and `Generate All` (amber, with the `cachedCount/validCount` badge and `generateDisabled` logic) buttons, plus `ImportExportMenu` and `SampleMenu`. Same Tailwind classes; just remove `fixed top-0 right-0 left-80 z-20` and the height-measuring `useLayoutEffect`.

Props interface:
```tsx
interface Props {
  validCount: number;
  cachedCount: number;
  busy: boolean;
  isDark: boolean;
  onAddSegment: () => void;
  onGenerateAll: () => void;
  onExportJson: () => void;
  onImportJson: (file: File) => void;
  onLoadSample: (sample: Sample) => void;
}
```

- [ ] **Step 2: Typecheck**

Run: `cd frontend && npm run typecheck`
Expected: PASS.

- [ ] **Step 3: Commit**

```bash
git add frontend/src/components/MiddleToolbar.tsx
git commit -m "feat(ui): extract MiddleToolbar (content actions only)"
```

---

## Task 4: Extract `InlinePlayer`

**Files:**
- Create: `frontend/src/components/InlinePlayer.tsx`
- Reference: `frontend/src/components/PlayerFooter.tsx` (full content — Full podcast label + Play All/Stop All + Download Audio + Play Podcast).

- [ ] **Step 1: Create `InlinePlayer.tsx`**

Copy `PlayerFooter`'s markup verbatim, but drop the `fixed bottom-0 ... left-80` positioning and the `onHeightChange`/`ResizeObserver` plumbing (the middle flex column makes it sticky-bottom in Task 6). Keep all button styling and the `segmentCount/validCount/cachedCount/isPlayingAll/currentIndex/isExporting` props and handlers identical.

Props interface (mirror the current `PlayerFooter` minus `onHeightChange`):
```tsx
interface Props {
  segmentCount: number;
  validCount: number;
  cachedCount: number;
  isPlayingAll: boolean;
  currentIndex: number;
  isExporting: boolean;
  isDark: boolean;
  onPlayAll: () => void;
  onStopAll: () => void;
  onExportAudio: () => void;
}
```

- [ ] **Step 2: Typecheck**

Run: `cd frontend && npm run typecheck`
Expected: PASS.

- [ ] **Step 3: Commit**

```bash
git add frontend/src/components/InlinePlayer.tsx
git commit -m "feat(ui): extract InlinePlayer from PlayerFooter"
```

---

## Task 5: Build `ControlPanel` (right column, collapsible)

**Files:**
- Create: `frontend/src/components/ControlPanel.tsx`
- Reference: `frontend/src/components/ActionBar.tsx` (EngineSelector wiring + the `SettingsMenu` props), `frontend/src/components/SettingsMenu.tsx` (its CFG + exaggeration slider bodies — reuse the inner controls, drop the popover shell), `frontend/src/components/Sidebar.tsx:201-210` (device/dtype/sr line + `ThemeToggle`).

- [ ] **Step 1: Read `SettingsMenu.tsx` to identify the slider bodies**

Note which inner JSX renders the CFG slider (uses `CfgScaleControl` + `getCfgHints`) and the exaggeration slider, so they can be rendered inline in the panel (not inside a dropdown popover).

- [ ] **Step 2: Create `ControlPanel.tsx`**

A right column `<aside class="w-80 shrink-0 h-screen border-l ...">` (mirror VoiceLibrary's surface/border tokens, `border-l` instead of `border-r`). Vertical stack of labeled sections, each a small heading in the existing `text-xs font-semibold uppercase tracking-wide` style:
- **Engine** → `EngineSelector` (same props as in ActionBar: `engines`, `activeName`, `onSelect`, `onLoad`, `onInstall`, `onDownload`).
- **Settings** → the CFG slider (`CfgScaleControl` + `getCfgHints(activeEngine)`) and, when `activeEngine === "chatterbox"`, the exaggeration slider — rendered inline (reuse SettingsMenu's inner JSX; do not import the popover).
- **Appearance** → `ThemeToggle`.
- **Backend** → the `device · dtype · sr` line from config.

Collapsible: a `collapsed` boolean from `localStorage` key `vs.controlPanel.open` (default open ≥1200px, collapsed below — read `window.innerWidth` once on mount). When collapsed, render a thin `w-12 shrink-0 h-screen border-l` strip with a single `PanelRightOpen` icon button (lucide-react) that sets open and persists. When open, show a `PanelRightClose` icon button in the panel header that collapses + persists.

Props interface:
```tsx
interface Props {
  isDark: boolean;
  theme: "light" | "dark";
  onThemeToggle: () => void;
  config: ConfigResponse | null;
  engines: EngineInfo[];
  activeEngine: string | null;
  onSelectEngine: (name: string) => Promise<void>;
  onLoadEngine: (name: string) => Promise<void>;
  onInstallEngine: (name: string) => void;
  onDownloadEngine: (name: string) => void;
  cfgScale: number;
  onCfgScaleChange: (v: number) => void;
  exaggeration: number;
  onExaggerationChange: (v: number) => void;
}
```

- [ ] **Step 3: Typecheck**

Run: `cd frontend && npm run typecheck`
Expected: PASS.

- [ ] **Step 4: Commit**

```bash
git add frontend/src/components/ControlPanel.tsx
git commit -m "feat(ui): add collapsible ControlPanel (engine + settings + theme + info)"
```

---

## Task 6: Rewire `App.tsx` to the three-column layout

**Files:**
- Modify: `frontend/src/App.tsx` (the `return (...)` block at lines ~587-765, and remove the `actionBarH`/`playerFooterH` state at lines ~106-107)

- [ ] **Step 1: Replace the root layout**

Replace the current `<div class="flex min-h-screen">` containing `<Sidebar>` + `<main class="flex-1 ml-80 relative">` (ActionBar/segments/PlayerFooter) with a three-column flex row:

```tsx
return (
  <div className={`flex h-screen overflow-hidden ${isDark ? "bg-zinc-950" : "bg-gray-50"}`}>
    <VoiceLibrary
      voices={displayedVoices}
      config={config}
      theme={theme}
      onUploadVoice={uploadVoice}
      onRemoveVoice={removeVoice}
      onUpdateVoiceMeta={handleUpdateVoiceMeta}
      supportsVoiceCloning={supportsVoiceCloning}
    />

    {/* MIDDLE column: sticky toolbar, scroll body, sticky player */}
    <main className="flex-1 flex flex-col min-w-0">
      <MiddleToolbar
        validCount={validCount}
        cachedCount={cachedCount}
        busy={busy}
        isDark={isDark}
        onAddSegment={project.addSegment}
        onGenerateAll={handleGenerateAll}
        onExportJson={handleExportJson}
        onImportJson={handleImportJson}
        onLoadSample={handleLoadSample}
      />

      <div className="flex-1 overflow-y-auto px-6 py-4">
        <div className="max-w-5xl mx-auto space-y-4">
          {/* exporting banner + toast (move the existing two blocks here, unchanged) */}
          <SpeakerRoster
            speakers={project.speakers}
            voices={displayedVoices}
            isDark={isDark}
            activeEngine={activeEngine}
            onAddSpeaker={project.addSpeaker}
            onUpdateSpeaker={project.updateSpeaker}
            onRemoveSpeaker={project.removeSpeaker}
            onSetSpeakerVoice={project.setSpeakerVoice}
          />
          {project.segments.map((segment, index) => { /* unchanged SegmentCard map */ })}
        </div>
      </div>

      <InlinePlayer
        segmentCount={project.segments.length}
        validCount={validCount}
        cachedCount={cachedCount}
        isPlayingAll={isPlayingAll}
        currentIndex={currentIndex}
        isExporting={isExporting}
        isDark={isDark}
        onPlayAll={handlePlayAll}
        onStopAll={handleStopAll}
        onExportAudio={handleExportAudio}
      />
    </main>

    <ControlPanel
      isDark={isDark}
      theme={theme}
      onThemeToggle={() => setTheme((t) => (t === "dark" ? "light" : "dark"))}
      config={config}
      engines={engines}
      activeEngine={activeEngine}
      onSelectEngine={async (name) => { try { await setActiveEngine(name); } catch (err) { showError(err, "Engine switch failed"); } }}
      onLoadEngine={async (name) => { try { await ensureEngineLoaded(name); } catch (err) { showError(err, "Engine load failed"); } }}
      onInstallEngine={(name) => setInstallEngine(name)}
      onDownloadEngine={(name) => setDownloadEngine(name)}
      cfgScale={cfgScale}
      onCfgScaleChange={setCfgScale}
      exaggeration={exaggeration}
      onExaggerationChange={setExaggeration}
    />

    {/* keep the InstallEngineDialog + DownloadModelDialog blocks, unchanged, at the end inside the root div */}
  </div>
);
```

Keep the exporting banner and toast blocks (currently lines ~651-684) — move them inside the middle scroll body's `max-w-5xl` wrapper, unchanged. Keep the `InstallEngineDialog` and `DownloadModelDialog` conditional blocks exactly as-is (move them to just before the root `</div>`).

- [ ] **Step 2: Remove dead state + imports**

Delete the `actionBarH`/`playerFooterH` `useState` lines (~106-107). Remove imports of `Sidebar`, `ActionBar`, `PlayerFooter`. Add imports for `VoiceLibrary`, `SpeakerRoster`, `MiddleToolbar`, `InlinePlayer`, `ControlPanel`.

- [ ] **Step 3: Typecheck + build**

Run: `cd frontend && npm run typecheck && npm run build`
Expected: PASS, no unused-import or type errors.

- [ ] **Step 4: Commit**

```bash
git add frontend/src/App.tsx
git commit -m "feat(ui): rewire App to three-column layout (voices | content | controls)"
```

---

## Task 7: Delete superseded components

**Files:**
- Delete: `frontend/src/components/Sidebar.tsx`, `frontend/src/components/ActionBar.tsx`, `frontend/src/components/PlayerFooter.tsx`

- [ ] **Step 1: Confirm no imports remain**

Run: `cd frontend && npx grep -r "Sidebar\|ActionBar\|PlayerFooter" src` (or use the editor's search). Expected: no imports of these three files anywhere in `src/`.

- [ ] **Step 2: Delete the three files**

```bash
git rm frontend/src/components/Sidebar.tsx frontend/src/components/ActionBar.tsx frontend/src/components/PlayerFooter.tsx
```

- [ ] **Step 3: Typecheck + build**

Run: `cd frontend && npm run typecheck && npm run build`
Expected: PASS.

- [ ] **Step 4: Commit**

```bash
git commit -m "chore(ui): remove superseded Sidebar/ActionBar/PlayerFooter"
```

---

## Task 8: Playwright verification

**Files:** none (manual/driven verification by the controller, not a committed test).

- [ ] **Step 1: Start the dev server**

Run (background): `cd frontend && npm run dev` (Vite on :5173, proxies /api to :8880). Ensure the backend is running on :8880.

- [ ] **Step 2: Drive the browser with Playwright MCP**

Navigate to `http://localhost:5173` and verify:
1. Three columns render: `VoiceLibrary` left (Built-in voices + My voices headings), middle (toolbar buttons Add Segment/Generate All/Samples/Import-Export + a segment card), `ControlPanel` right (Engine section + a Settings slider).
2. `SpeakerRoster` renders at the top of the middle column (above the first segment), NOT in the left column.
3. Right panel: click the collapse icon → panel becomes the thin strip → click reopen → panel returns. Reload the page → collapsed/open state persisted.
4. The inline player sits at the bottom of the middle column with Download Audio + Play Podcast.
5. Take a screenshot; confirm the palette and card styling match the pre-change design (teal accents, zinc surfaces) — no restyle.
6. If a model is loaded, generate a segment and play it; otherwise assert the Generate request is issued (network) and the busy state toggles.

- [ ] **Step 3: Fix any layout regressions found, then re-verify**

If a column overflows, the player overlaps, or a control is missing, fix in the relevant component (structural only) and re-run Step 2.

- [ ] **Step 4: Stop the dev server**

---

## Self-Review (controller, before handing to Phase 2)

1. **Spec coverage:** VoiceLibrary (left), SpeakerRoster (middle top), MiddleToolbar, InlinePlayer (middle bottom), ControlPanel (right, collapsible) — all five spec components have tasks. ✅
2. **Behavior unchanged:** every handler in `App.tsx` is reused; only placement moves. ✅
3. **No restyle:** all Tailwind classes copied verbatim from the superseded components. ✅
4. **Playwright:** Task 8 covers render, roster placement, collapse persistence, and a smoke generate. ✅
