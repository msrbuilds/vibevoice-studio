# UI Redesign Phase 2 — Project Modes + Language Metadata — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a persisted Text-to-Voice / Podcast project mode (both work on every engine), a first-run mode chooser, a Text-to-Voice editor (big textarea + char/word/duration counts), and a data-driven language dropdown fed by new backend per-engine `languages` metadata.

**Architecture:** Backend gains an `Engine.languages()` method (default `[]`; Chatterbox = 23 codes as synth param, Kokoro = its 4 built-in-voice languages as a voice filter) surfaced via `info()`/schema. Frontend gains a `useProjectMode` hook (mode + tts buffer, persisted to localStorage), a `ModeChooser`, a `ModeToggle`, a `TtsEditor`, and a `LanguageSelect`; `App.tsx` renders chooser/podcast/tts by mode. Built on Phase 1's three-column shell.

**Tech Stack:** FastAPI + Pydantic (backend), React 18 + TS + Vite + Tailwind (frontend). Backend tests via pytest; frontend via typecheck/build + Playwright.

**Constraints:** Structural/additive only — reuse the existing design language. Playwright verification at the end.

---

## Backend

### Task 1: `Engine.languages()` metadata

**Files:**
- Modify: `backend/core/engines/__init__.py` (add base method + include in `info()`)
- Modify: `backend/core/engines/chatterbox_engine.py` (override)
- Modify: `backend/core/engines/kokoro_engine.py` (override)
- Test: `backend/tests/test_engine_languages.py` (create)

- [ ] **Step 1: Write the failing test** — create `backend/tests/test_engine_languages.py`

```python
"""Per-engine language metadata for the UI language dropdown."""
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT))

from backend.core.engines.chatterbox_engine import ChatterboxEngine  # noqa: E402
from backend.core.engines.kokoro_engine import KokoroEngine  # noqa: E402


def test_chatterbox_languages_cover_supported_ids():
    eng = ChatterboxEngine(worker_python=Path("x"), worker_script=Path("y"))
    langs = eng.languages()
    codes = {l["code"] for l in langs}
    # All 23 Chatterbox language ids are present, each with a non-empty label.
    assert "en" in codes and "ur" in codes and "zh" in codes
    assert len(codes) == 23
    assert all(l["label"] for l in langs)


def test_kokoro_languages_are_its_voice_groups():
    eng = KokoroEngine()
    codes = {l["code"] for l in eng.languages()}
    # Kokoro language == the distinct languages of its built-in voice catalog.
    assert codes == {"en-us", "en-gb", "ja", "zh"}


def test_languages_in_info_dict():
    eng = KokoroEngine()
    assert "languages" in eng.info()
    assert isinstance(eng.info()["languages"], list)
```

- [ ] **Step 2: Run to verify failure**

Run: `cd backend && ./venv/Scripts/python.exe -m pytest tests/test_engine_languages.py -v`
Expected: FAIL (`Engine` has no `languages`).

- [ ] **Step 3: Add the base method + info() field** in `backend/core/engines/__init__.py`

Add to the `Engine` class (near `downloaded`):
```python
    def languages(self) -> list[dict[str, str]]:
        """UI language options as [{"code","label"}].

        Default empty = the engine shows no language selector (reference-
        driven like VibeVoice, or auto-detected like OmniVoice). Cloning
        engines that accept a language param (Chatterbox) and built-in-voice
        engines whose voices are language-grouped (Kokoro) override this.
        """
        return []
```
And add `"languages": self.languages(),` to the dict returned by `info()`.

- [ ] **Step 4: Override in Chatterbox** — `backend/core/engines/chatterbox_engine.py`

Add a module-level label map + method. Use the existing `SUPPORTED_LANGUAGE_IDS`:
```python
_LANGUAGE_LABELS: dict[str, str] = {
    "ar": "Arabic", "da": "Danish", "de": "German", "el": "Greek",
    "en": "English", "es": "Spanish", "fi": "Finnish", "fr": "French",
    "he": "Hebrew", "hi": "Hindi", "it": "Italian", "ja": "Japanese",
    "ko": "Korean", "ms": "Malay", "nl": "Dutch", "no": "Norwegian",
    "pl": "Polish", "pt": "Portuguese", "ru": "Russian", "sv": "Swedish",
    "sw": "Swahili", "tr": "Turkish", "zh": "Chinese",
}
```
Method on `ChatterboxEngine`:
```python
    def languages(self) -> list[dict[str, str]]:
        return [
            {"code": c, "label": _LANGUAGE_LABELS.get(c, c)}
            for c in sorted(SUPPORTED_LANGUAGE_IDS)
        ]
```

- [ ] **Step 5: Override in Kokoro** — `backend/core/engines/kokoro_engine.py`

Derive from `_KOKORO_VOICES` (distinct `language` values), with labels:
```python
_KOKORO_LANG_LABELS: dict[str, str] = {
    "en-us": "English (US)", "en-gb": "English (UK)",
    "ja": "Japanese", "zh": "Chinese",
}
```
Method on `KokoroEngine`:
```python
    def languages(self) -> list[dict[str, str]]:
        seen: list[str] = []
        for v in _KOKORO_VOICES:
            if v.language not in seen:
                seen.append(v.language)
        return [{"code": c, "label": _KOKORO_LANG_LABELS.get(c, c)} for c in seen]
```

- [ ] **Step 6: Run tests to verify pass**

Run: `cd backend && ./venv/Scripts/python.exe -m pytest tests/test_engine_languages.py -v`
Expected: PASS (3 tests).

- [ ] **Step 7: Commit**

```bash
git add backend/core/engines/__init__.py backend/core/engines/chatterbox_engine.py backend/core/engines/kokoro_engine.py backend/tests/test_engine_languages.py
git commit -m "feat(engines): add per-engine languages() metadata for UI selector"
```

### Task 2: Surface `languages` in the API schema + endpoint

**Files:**
- Modify: `backend/api/schemas.py` (`EngineInfoModel`)
- Modify: `backend/api/engines.py` (the info dict builder — confirm it passes `languages` through)
- Test: `backend/tests/test_engine_languages.py` (extend)

- [ ] **Step 1: Add the failing assertion** — append to `backend/tests/test_engine_languages.py`

```python
def test_engines_endpoint_includes_languages(monkeypatch):
    # The /api/engines payload must carry the languages list per engine.
    from fastapi.testclient import TestClient
    from backend.app import create_app

    app = create_app()
    with TestClient(app) as client:
        resp = client.get("/api/engines")
        assert resp.status_code == 200
        engines = resp.json()["engines"] if isinstance(resp.json(), dict) else resp.json()
        by_name = {e["name"]: e for e in engines}
        assert "languages" in by_name["kokoro"]
        assert {l["code"] for l in by_name["kokoro"]["languages"]} == {"en-us", "en-gb", "ja", "zh"}
```
(If `/api/engines` returns a bare list, the `engines` extraction handles both; adjust to the actual shape after reading `backend/api/engines.py`.)

- [ ] **Step 2: Run to verify failure**

Run: `cd backend && ./venv/Scripts/python.exe -m pytest tests/test_engine_languages.py::test_engines_endpoint_includes_languages -v`
Expected: FAIL (`languages` absent from the serialized model).

- [ ] **Step 3: Add `languages` to `EngineInfoModel`** in `backend/api/schemas.py`

```python
class EngineLanguageModel(BaseModel):
    code: str
    label: str


class EngineInfoModel(BaseModel):
    name: str
    display_name: str
    description: str = ""
    loaded: bool
    supports_voice_cloning: bool
    supports_streaming: bool = False
    sample_rate: int | None = None
    max_speakers: int
    default_cfg_scale: float | None = None
    languages: list[EngineLanguageModel] = []
    active: bool = False
```

- [ ] **Step 4: Confirm the endpoint passes it through** — read `backend/api/engines.py`

The `/api/engines` (and `/api/config`) handlers build dicts from `engine.info()`. Since `info()` now includes `languages`, confirm the serialization includes it (the Pydantic model now has the field). If the handler constructs `EngineInfoModel(**subset)` with an explicit field list, add `languages=info["languages"]`. If it passes `**info`, no change needed beyond the schema.

- [ ] **Step 5: Run tests + full suite**

Run: `cd backend && ./venv/Scripts/python.exe -m pytest tests/ -q`
Expected: PASS (all, incl. the new endpoint test).

- [ ] **Step 6: Commit**

```bash
git add backend/api/schemas.py backend/api/engines.py backend/tests/test_engine_languages.py
git commit -m "feat(api): surface engine languages in /api/engines + /api/config"
```

---

## Frontend

### Task 3: Types + `useProjectMode` hook (mode + TTS buffer, persisted)

**Files:**
- Modify: `frontend/src/types/models.ts` (add `languages` to `EngineInfo`; add `ProjectMode`, `TtsBuffer`, `EngineLanguage`)
- Create: `frontend/src/hooks/useProjectMode.ts`

- [ ] **Step 1: Extend types** in `frontend/src/types/models.ts`

```ts
export interface EngineLanguage {
  code: string;
  label: string;
}
```
Add to `EngineInfo`: `languages: EngineLanguage[];`
Add:
```ts
export type ProjectMode = "tts" | "podcast";

export interface TtsBuffer {
  text: string;
  voiceId: string | null;
  language: string | null;
}
```

- [ ] **Step 2: Create `useProjectMode.ts`**

A hook owning the mode + TTS buffer with localStorage persistence. Keys: `vs.mode`, `vs.tts`. `mode` is `null` until chosen (drives the chooser).

```ts
import { useCallback, useEffect, useState } from "react";
import type { ProjectMode, TtsBuffer } from "@/types/models";

const MODE_KEY = "vs.mode";
const TTS_KEY = "vs.tts";
const EMPTY_TTS: TtsBuffer = { text: "", voiceId: null, language: null };

function readMode(): ProjectMode | null {
  const v = localStorage.getItem(MODE_KEY);
  return v === "tts" || v === "podcast" ? v : null;
}
function readTts(): TtsBuffer {
  try {
    const raw = localStorage.getItem(TTS_KEY);
    if (!raw) return EMPTY_TTS;
    const p = JSON.parse(raw) as Partial<TtsBuffer>;
    return { text: p.text ?? "", voiceId: p.voiceId ?? null, language: p.language ?? null };
  } catch {
    return EMPTY_TTS;
  }
}

export interface UseProjectModeApi {
  mode: ProjectMode | null;
  setMode: (m: ProjectMode) => void;
  tts: TtsBuffer;
  setTtsText: (text: string) => void;
  setTtsVoice: (voiceId: string | null) => void;
  setTtsLanguage: (language: string | null) => void;
}

export function useProjectMode(): UseProjectModeApi {
  const [mode, setModeState] = useState<ProjectMode | null>(readMode);
  const [tts, setTts] = useState<TtsBuffer>(readTts);

  useEffect(() => {
    if (mode) localStorage.setItem(MODE_KEY, mode);
  }, [mode]);
  useEffect(() => {
    localStorage.setItem(TTS_KEY, JSON.stringify(tts));
  }, [tts]);

  const setMode = useCallback((m: ProjectMode) => setModeState(m), []);
  const setTtsText = useCallback((text: string) => setTts((t) => ({ ...t, text })), []);
  const setTtsVoice = useCallback((voiceId: string | null) => setTts((t) => ({ ...t, voiceId })), []);
  const setTtsLanguage = useCallback((language: string | null) => setTts((t) => ({ ...t, language })), []);

  return { mode, setMode, tts, setTtsText, setTtsVoice, setTtsLanguage };
}
```

- [ ] **Step 3: Typecheck**

Run: `cd frontend && npm run typecheck`
Expected: PASS.

- [ ] **Step 4: Commit**

```bash
git add frontend/src/types/models.ts frontend/src/hooks/useProjectMode.ts
git commit -m "feat(ui): project-mode + TTS-buffer hook with localStorage persistence"
```

### Task 4: `ModeChooser` + `ModeToggle`

**Files:**
- Create: `frontend/src/components/ModeChooser.tsx`
- Create: `frontend/src/components/ModeToggle.tsx`

- [ ] **Step 1: Create `ModeChooser.tsx`**

Empty-state shown when `mode === null`. Two large cards centered in the middle column, styled with existing tokens (rounded panel, zinc surface, teal hover border). Mirror the visual language of existing cards (no new colors).

```tsx
import { Mic2, FileText } from "lucide-react";
import type { ProjectMode } from "@/types/models";

interface Props {
  isDark: boolean;
  onPick: (m: ProjectMode) => void;
}

export function ModeChooser({ isDark, onPick }: Props) {
  const card = isDark
    ? "bg-zinc-900 border-zinc-800 hover:border-teal-500"
    : "bg-white border-gray-200 hover:border-teal-500";
  const title = isDark ? "text-white" : "text-gray-900";
  const sub = isDark ? "text-zinc-400" : "text-gray-500";
  return (
    <div className="flex-1 flex items-center justify-center p-8">
      <div className="grid grid-cols-1 sm:grid-cols-2 gap-6 max-w-3xl w-full">
        <button type="button" onClick={() => onPick("tts")}
          className={`text-left p-6 rounded-xl border transition-colors ${card}`}>
          <FileText className="w-8 h-8 text-teal-400 mb-3" />
          <div className={`font-semibold ${title}`}>Text-to-Voice</div>
          <p className={`text-sm mt-1 ${sub}`}>Type or paste text and generate with a single voice.</p>
        </button>
        <button type="button" onClick={() => onPick("podcast")}
          className={`text-left p-6 rounded-xl border transition-colors ${card}`}>
          <Mic2 className="w-8 h-8 text-teal-400 mb-3" />
          <div className={`font-semibold ${title}`}>Podcast</div>
          <p className={`text-sm mt-1 ${sub}`}>Build a multi-speaker conversation from segments.</p>
        </button>
      </div>
    </div>
  );
}
```

- [ ] **Step 2: Create `ModeToggle.tsx`** — a segmented control in the toolbar

```tsx
import type { ProjectMode } from "@/types/models";

interface Props {
  isDark: boolean;
  mode: ProjectMode;
  onChange: (m: ProjectMode) => void;
}

export function ModeToggle({ isDark, mode, onChange }: Props) {
  const wrap = isDark ? "bg-zinc-800" : "bg-gray-100";
  const seg = (m: ProjectMode, label: string) => (
    <button type="button" onClick={() => onChange(m)}
      className={`px-3 py-1.5 text-sm font-medium rounded-md transition-colors ${
        mode === m ? "bg-teal-600 text-white"
        : isDark ? "text-zinc-400 hover:text-zinc-200" : "text-gray-500 hover:text-gray-700"
      }`}>
      {label}
    </button>
  );
  return <div className={`inline-flex gap-1 p-1 rounded-lg ${wrap}`}>{seg("tts", "Text-to-Voice")}{seg("podcast", "Podcast")}</div>;
}
```

- [ ] **Step 3: Typecheck**

Run: `cd frontend && npm run typecheck`
Expected: PASS.

- [ ] **Step 4: Commit**

```bash
git add frontend/src/components/ModeChooser.tsx frontend/src/components/ModeToggle.tsx
git commit -m "feat(ui): ModeChooser empty-state + ModeToggle segmented control"
```

### Task 5: `LanguageSelect` + counts helper

**Files:**
- Create: `frontend/src/components/LanguageSelect.tsx`
- Create: `frontend/src/lib/textStats.ts`

- [ ] **Step 1: Create `lib/textStats.ts`**

```ts
export interface TextStats {
  chars: number;
  words: number;
  seconds: number;
}

/** ~2.5 words/sec (≈150 wpm) duration estimate. */
export function textStats(text: string): TextStats {
  const chars = text.length;
  const words = text.trim() ? text.trim().split(/\s+/).length : 0;
  const seconds = Math.ceil(words / 2.5);
  return { chars, words, seconds };
}

export function fmtDuration(seconds: number): string {
  if (seconds < 60) return `~${seconds}s`;
  const m = Math.floor(seconds / 60);
  const s = seconds % 60;
  return `~${m}m ${String(s).padStart(2, "0")}s`;
}
```

- [ ] **Step 2: Create `LanguageSelect.tsx`**

```tsx
import type { EngineLanguage } from "@/types/models";

interface Props {
  isDark: boolean;
  languages: EngineLanguage[];
  value: string | null;
  onChange: (code: string) => void;
}

export function LanguageSelect({ isDark, languages, value, onChange }: Props) {
  if (languages.length === 0) return null;
  const selectBg = isDark ? "bg-zinc-800 border-zinc-700 text-white" : "bg-white border-gray-300 text-gray-900";
  return (
    <select
      value={value ?? languages[0]!.code}
      onChange={(e) => onChange(e.target.value)}
      className={`border rounded-md px-2 py-1.5 text-xs focus:outline-none focus:border-teal-500 ${selectBg}`}
    >
      {languages.map((l) => (
        <option key={l.code} value={l.code}>{l.label}</option>
      ))}
    </select>
  );
}
```

- [ ] **Step 3: Typecheck**

Run: `cd frontend && npm run typecheck`
Expected: PASS.

- [ ] **Step 4: Commit**

```bash
git add frontend/src/components/LanguageSelect.tsx frontend/src/lib/textStats.ts
git commit -m "feat(ui): LanguageSelect dropdown + textStats (chars/words/duration)"
```

### Task 6: `TtsEditor` (big textarea + counts + language + generate/play)

**Files:**
- Create: `frontend/src/components/TtsEditor.tsx`

- [ ] **Step 1: Create `TtsEditor.tsx`**

Reuses the existing text-input styling. Shows the textarea, the counts row, a language dropdown (when the engine has languages and is a cloning engine — see Task 8 for filter-vs-param wiring), the active voice name (from the left library selection), and Generate + Play buttons (styled like SegmentCard's).

```tsx
import { Loader2, Play, RefreshCw } from "lucide-react";
import type { EngineLanguage, Voice } from "@/types/models";
import { textStats, fmtDuration } from "@/lib/textStats";
import { LanguageSelect } from "./LanguageSelect";

interface Props {
  isDark: boolean;
  text: string;
  onTextChange: (t: string) => void;
  activeVoice: Voice | null;
  languages: EngineLanguage[];
  showLanguage: boolean;          // false for built-in-voice engines (filter handled in library)
  language: string | null;
  onLanguageChange: (code: string) => void;
  busy: boolean;
  isGenerating: boolean;
  onGenerate: () => void;
  onPlay: () => void;
}

export function TtsEditor(props: Props) {
  const { isDark, text, onTextChange, activeVoice, languages, showLanguage,
          language, onLanguageChange, busy, isGenerating, onGenerate, onPlay } = props;
  const stats = textStats(text);
  const inputBg = isDark ? "bg-zinc-900 border-zinc-800 text-white" : "bg-white border-gray-200 text-gray-900";
  const sub = isDark ? "text-zinc-500" : "text-gray-500";
  return (
    <div className="max-w-3xl mx-auto w-full space-y-3">
      <textarea
        value={text}
        onChange={(e) => onTextChange(e.target.value)}
        placeholder="Type or paste text to synthesize…"
        className={`w-full min-h-[260px] rounded-xl border p-4 text-sm leading-relaxed focus:outline-none focus:border-teal-500 ${inputBg}`}
      />
      <div className="flex items-center justify-between flex-wrap gap-2">
        <div className={`text-xs ${sub}`}>
          {stats.chars} chars · {stats.words} words · {fmtDuration(stats.seconds)}
        </div>
        <div className="flex items-center gap-2">
          {showLanguage && (
            <LanguageSelect isDark={isDark} languages={languages} value={language} onChange={onLanguageChange} />
          )}
          <span className={`text-xs ${sub}`}>
            Voice: <span className="text-teal-400">{activeVoice ? activeVoice.name : "none selected"}</span>
          </span>
          <button type="button" onClick={onGenerate} disabled={busy || !text.trim()}
            className="flex items-center gap-2 px-4 py-2 rounded-lg font-medium bg-amber-600 hover:bg-amber-500 disabled:bg-zinc-700 disabled:text-zinc-500 text-white transition-colors">
            {isGenerating ? <Loader2 className="w-4 h-4 animate-spin" /> : <RefreshCw className="w-4 h-4" />} Generate
          </button>
          <button type="button" onClick={onPlay} disabled={busy}
            className={`flex items-center gap-2 px-4 py-2 rounded-lg font-medium transition-colors ${
              isDark ? "bg-zinc-800 hover:bg-zinc-700 text-white" : "bg-gray-100 hover:bg-gray-200 text-gray-900"}`}>
            <Play className="w-4 h-4" /> Play
          </button>
        </div>
      </div>
    </div>
  );
}
```

- [ ] **Step 2: Typecheck**

Run: `cd frontend && npm run typecheck`
Expected: PASS.

- [ ] **Step 3: Commit**

```bash
git add frontend/src/components/TtsEditor.tsx
git commit -m "feat(ui): TtsEditor (textarea + counts + language + generate/play)"
```

### Task 7: Voice selection in `VoiceLibrary` (flat active voice)

**Files:**
- Modify: `frontend/src/components/VoiceLibrary.tsx`

- [ ] **Step 1: Add selection props + highlight**

Add optional props:
```tsx
  selectedVoiceId?: string | null;
  onSelectVoice?: (voiceId: string) => void;
```
Make each built-in and upload voice row clickable when `onSelectVoice` is provided: clicking calls `onSelectVoice(v.id)`. When `selectedVoiceId === v.id`, add a selected ring/teal accent using existing tokens (e.g. `ring-1 ring-teal-500 bg-teal-600/10`). When `onSelectVoice` is undefined (podcast mode), rows are non-interactive as before. Keep the edit/delete buttons working (stopPropagation on their onClick so a row-select doesn't fire).

- [ ] **Step 2: Typecheck**

Run: `cd frontend && npm run typecheck`
Expected: PASS.

- [ ] **Step 3: Commit**

```bash
git add frontend/src/components/VoiceLibrary.tsx
git commit -m "feat(ui): VoiceLibrary flat active-voice selection (TTS mode)"
```

### Task 8: Wire modes into `App.tsx`

**Files:**
- Modify: `frontend/src/App.tsx`
- Modify: `frontend/src/components/MiddleToolbar.tsx` (host the `ModeToggle` + a `mode`-aware Generate)

- [ ] **Step 1: Consume `useProjectMode` + derive language plumbing**

In `App.tsx`:
- `const pm = useProjectMode();`
- Compute `const activeEngineInfo = engines.find(e => e.name === activeEngine) ?? null;`
- `const engineLanguages = activeEngineInfo?.languages ?? [];`
- `const isCloningLangEngine = supportsVoiceCloning && engineLanguages.length > 0;` (Chatterbox → language is a synth param)
- `const isFilterLangEngine = !supportsVoiceCloning && engineLanguages.length > 0;` (Kokoro → language filters voices)
- For Kokoro filtering: when `isFilterLangEngine` and `pm.tts.language` is set, filter `displayedVoices` to voices whose `language === pm.tts.language` (Kokoro `Voice.language` is `en-us`/`en-gb`/`ja`/`zh`). Apply the same filter to the podcast voice selects via the `displayedVoices` prop.

- [ ] **Step 2: Render by mode**

Replace the middle scroll body so it renders:
- `pm.mode === null` → `<ModeChooser isDark={isDark} onPick={pm.setMode} />` (full-height, no toolbar segment list).
- `pm.mode === "podcast"` → the Phase 1 podcast body (SpeakerRoster + segments) unchanged.
- `pm.mode === "tts"` → `<TtsEditor ... />` wired to `pm.tts`, the active voice (the `displayedVoices` entry whose id === `pm.tts.voiceId`), `showLanguage={isCloningLangEngine}`, generation via a new `generateTts` handler.

Add `generateTts` (mirrors `generateFor` but for a single TTS buffer):
```tsx
const TTS_SEG_ID = "__tts__";
const generateTts = useCallback(async () => {
  const voice = displayedVoices.find((v) => v.id === pm.tts.voiceId) ?? null;
  if (!voice) { showError("Select a voice in the library first.", "No voice"); return; }
  if (!pm.tts.text.trim()) return;
  setGeneratingId(TTS_SEG_ID);
  try {
    const isChatterbox = activeEngine === "chatterbox";
    const speakers: SynthSpeaker[] = [{ name: "Voice", voice: voice.id }];
    const { audioData, cacheHash } = await synthesizeWav(pm.tts.text, speakers, cfgScale, {
      cfgWeight: isChatterbox ? cfgScale : null,
      exaggeration: isChatterbox ? exaggeration : null,
      languageId: isCloningLangEngine ? (pm.tts.language ?? undefined) : undefined,
    });
    project.cacheAudio(TTS_SEG_ID, { audioData, text: pm.tts.text, voice: voice.id, ...(cacheHash ? { cacheHash } : {}) });
  } catch (err) { showError(err, "Synthesis failed"); }
  finally { setGeneratingId(null); }
}, [pm.tts, displayedVoices, activeEngine, cfgScale, exaggeration, isCloningLangEngine, project, showError]);
```
And a `playTts` that calls `playCached(TTS_SEG_ID)` after generating if needed.

NOTE: confirm `synthesizeWav`'s options object supports a `languageId` field; if not, add it in `lib/api.ts` (it maps to the request body's `language_id`). Read `lib/api.ts` first.

- [ ] **Step 3: Add `ModeToggle` to `MiddleToolbar`**

Give `MiddleToolbar` new props `mode: ProjectMode | null` + `onModeChange: (m: ProjectMode) => void`, and render `<ModeToggle>` at the left of the toolbar when `mode !== null`. In TTS mode, hide `Add Segment` / `Generate All` (those are podcast-only); keep `Samples` + `Import/Export`. Pass `mode`/`onModeChange` from `App.tsx`.

- [ ] **Step 4: Typecheck + build**

Run: `cd frontend && npm run typecheck && npm run build`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add frontend/src/App.tsx frontend/src/components/MiddleToolbar.tsx
git commit -m "feat(ui): wire project modes (chooser/podcast/tts) + language into App"
```

### Task 9: `lib/api.ts` languageId option (if missing)

**Files:**
- Modify: `frontend/src/lib/api.ts` (only if `synthesizeWav` doesn't already accept `languageId`)

- [ ] **Step 1: Read `lib/api.ts`** — locate `synthesizeWav` and its options type.

- [ ] **Step 2: Add `languageId?: string` to the options** and map it into the request body as `language_id`. Show the exact edit after reading. If it already exists, skip this task.

- [ ] **Step 3: Typecheck + commit (if changed)**

```bash
git add frontend/src/lib/api.ts
git commit -m "feat(api-client): pass languageId to synthesize request"
```

---

## Task 10: Playwright verification

**Files:** none (controller-driven).

- [ ] **Step 1:** Ensure backend (:8880) + `npm run dev` (:5173) are running. Clear localStorage (`vs.mode`, `vs.tts`) via DevTools or `localStorage.clear()` in the page.
- [ ] **Step 2:** Navigate to `http://localhost:5173`. Verify:
  1. Fresh state → `ModeChooser` shows two cards. Click **Text-to-Voice** → `TtsEditor` renders.
  2. Type text → counts update (`chars · words · ~Ss`).
  3. Reload → chooser skipped; TTS view restored with the typed text (persistence).
  4. `ModeToggle` → switch to Podcast → segments view; switch back → TTS text intact (separate buffers).
  5. Switch engine to **Chatterbox** → language dropdown appears in TTS editor; to **VibeVoice** → dropdown hidden.
  6. Switch engine to **Kokoro** → choosing **Japanese** filters the left voice library to `jf_*/jm_*`.
  7. Select a voice in the library (TTS mode) → it highlights; Generate → audio plays (or request issues in a GPU-less env).
- [ ] **Step 3:** Screenshot both modes; confirm design language unchanged. Fix any regressions (structural only) and re-verify.

---

## Self-Review (controller)

1. **Spec coverage:** persisted mode + chooser (Task 3/4/8), TTS editor + counts (Task 5/6), language metadata backend (Task 1/2), language dropdown + filter-vs-param (Task 5/8), separate buffers (Task 3). ✅
2. **Type consistency:** `EngineLanguage`/`languages`, `ProjectMode`, `TtsBuffer`, `TTS_SEG_ID` used consistently. ✅
3. **No restyle:** all new components reuse existing token patterns. ✅
4. **Backend tests** cover Chatterbox 23 / Kokoro 4 / endpoint. ✅
