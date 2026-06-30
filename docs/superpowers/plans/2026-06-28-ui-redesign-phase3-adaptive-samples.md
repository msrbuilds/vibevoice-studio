# UI Redesign Phase 3 — Mode-Adaptive Samples + Native Scripts — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Split samples into Podcast (multi-speaker) and Text-to-Voice (single text), make the Samples menu show the list matching the active project mode, and add true native-script Urdu (اردو) and Hindi (हिन्दी) samples.

**Architecture:** `lib/samples.ts` keeps `Sample`/`loadSample` (renamed export `PODCAST_SAMPLES`) and adds `TtsSample`/`TTS_SAMPLES`/`loadTtsSample`. `SampleMenu` takes `mode` + two callbacks and renders the matching list. `App.tsx`/`MiddleToolbar` pass `mode` and wire `onLoadTts` to the Phase 2 TTS buffer.

**Tech Stack:** React + TS + Vite + Tailwind. Verified by typecheck/build + a light unit check + Playwright.

**Constraints:** Additive/structural only — reuse the existing `SampleMenu` styling. Playwright verification at the end.

---

## Task 1: Split sample catalog + native-script content

**Files:**
- Modify: `frontend/src/lib/samples.ts`

- [ ] **Step 1: Rename the podcast array + add TTS types/data**

Keep the existing `Sample`, `SampleSegment`, `loadSample`, and `SAMPLES` content but rename the exported array `SAMPLES` → `PODCAST_SAMPLES` (keep `export const SAMPLES = PODCAST_SAMPLES;` as a temporary alias so nothing breaks mid-refactor; remove the alias in Task 3 once `SampleMenu` is updated). Add the `TtsSample` type and `TTS_SAMPLES` + `loadTtsSample`.

Add near the top (after the existing `Sample` interface):
```ts
export interface TtsSample {
  id: string;
  name: string;
  description: string;
  text: string;
  voice?: string; // suggested voice id; falls back to first available at load
}
```

Add the loader at the bottom:
```ts
export function loadTtsSample(sample: TtsSample): { text: string; voiceId: string | null } {
  return { text: sample.text, voiceId: sample.voice ?? null };
}
```

- [ ] **Step 2: Add native-script PODCAST samples**

Append these two entries to `PODCAST_SAMPLES` (UTF-8; copy the native text verbatim). They reuse the existing default voice constants (`DEFAULT_FEMALE_VOICE`, `DEFAULT_URDU_MALE_VOICE`):

```ts
  {
    id: "urdu-podcast-native",
    name: "اردو پوڈکاسٹ (Urdu, two hosts)",
    description: "A two-host Urdu chat in native Nastaʿlīq script.",
    speakers: [
      { name: "Ayesha", voice: DEFAULT_FEMALE_VOICE, color: SPEAKER_COLORS[0]! },
      { name: "Hamza", voice: DEFAULT_URDU_MALE_VOICE, color: SPEAKER_COLORS[1]! },
    ],
    segments: [
      { speaker: "Ayesha", text: "السلام علیکم حمزہ، کیسے ہیں آپ؟ بہت دنوں بعد آج پوڈکاسٹ پر مل رہے ہیں۔" },
      { speaker: "Hamza", text: "وعلیکم السلام عائشہ، میں بالکل ٹھیک ہوں، شکریہ۔ ہاں، بہت دن ہو گئے۔ آج ہم ایک دلچسپ موضوع پر بات کریں گے۔" },
      { speaker: "Ayesha", text: "جی بالکل۔ آج کا موضوع یہ ہے کہ ہم مصنوعی ذہانت سے اپنی روزمرہ زندگی میں کیسے مدد لے سکتے ہیں۔" },
      { speaker: "Hamza", text: "دیکھیے، مصنوعی ذہانت اب صرف سائنس فکشن نہیں رہی۔ اب یہ ہمارے فون میں، ہمارے گھر میں، اور ہمارے اسٹوڈیو میں بھی موجود ہے۔" },
      { speaker: "Ayesha", text: "اور سب سے اچھی بات یہ ہے کہ یہ سب آپ کے اپنے کمپیوٹر پر ہو رہا ہے، کسی کلاؤڈ پر نہیں۔ آپ کی پرائیویسی محفوظ رہتی ہے۔" },
      { speaker: "Hamza", text: "بالکل۔ تو سننے والو، آپ بھی آزمائیں۔ شکریہ عائشہ، آج کے لیے اتنا ہی۔ اللہ حافظ۔" },
    ],
  },
  {
    id: "hindi-podcast-native",
    name: "हिन्दी पॉडकास्ट (Hindi, two hosts)",
    description: "A two-host Hindi chat in native Devanagari script.",
    speakers: [
      { name: "Ayesha", voice: DEFAULT_FEMALE_VOICE, color: SPEAKER_COLORS[0]! },
      { name: "Hamza", voice: DEFAULT_URDU_MALE_VOICE, color: SPEAKER_COLORS[1]! },
    ],
    segments: [
      { speaker: "Ayesha", text: "नमस्ते हम्ज़ा, आप कैसे हैं? बहुत दिनों बाद आज पॉडकास्ट पर मिल रहे हैं।" },
      { speaker: "Hamza", text: "नमस्ते आयशा, मैं बिलकुल ठीक हूँ, शुक्रिया। हाँ, बहुत दिन हो गए। आज हम एक दिलचस्प विषय पर बात करेंगे।" },
      { speaker: "Ayesha", text: "जी बिलकुल। आज का विषय यह है कि हम कृत्रिम बुद्धिमत्ता से अपने रोज़मर्रा के जीवन में कैसे मदद ले सकते हैं।" },
      { speaker: "Hamza", text: "देखिए, कृत्रिम बुद्धिमत्ता अब सिर्फ़ साइंस फ़िक्शन नहीं रही। अब यह हमारे फ़ोन में, हमारे घर में, और हमारे स्टूडियो में भी मौजूद है।" },
      { speaker: "Ayesha", text: "और सबसे अच्छी बात यह है कि यह सब आपके अपने कंप्यूटर पर हो रहा है, किसी क्लाउड पर नहीं। आपकी निजता सुरक्षित रहती है।" },
      { speaker: "Hamza", text: "बिलकुल। तो सुनने वालो, आप भी आज़माएँ। शुक्रिया आयशा, आज के लिए इतना ही। नमस्ते।" },
    ],
  },
```

- [ ] **Step 3: Add `TTS_SAMPLES` (incl. native scripts)**

```ts
export const TTS_SAMPLES: TtsSample[] = [
  {
    id: "tts-narration-en",
    name: "English narration",
    description: "A short single-voice narration passage.",
    text: "The morning fog rolled in from the bay, slow and deliberate, as if the city itself were exhaling. Elena pulled her coat tighter and walked faster, the streetlights still casting pale halos into the grey.",
    voice: DEFAULT_FEMALE_VOICE,
  },
  {
    id: "tts-tutorial-en",
    name: "How-to blurb",
    description: "A friendly explanatory paragraph.",
    text: "Welcome! In the next two minutes I'll show you how to set up a fully local text-to-speech pipeline. Everything runs on your own machine, so your scripts and voices never leave your computer.",
    voice: DEFAULT_MALE_VOICE,
  },
  {
    id: "tts-urdu-native",
    name: "اردو تحریر (Urdu narration)",
    description: "A single-voice Urdu narration in native script.",
    text: "خوش آمدید! یہ آواز مکمل طور پر آپ کے اپنے کمپیوٹر پر بنائی جا رہی ہے، بغیر انٹرنیٹ کے۔ آپ کوئی بھی تحریر لکھیں اور اسے قدرتی آواز میں سنیں۔ یہ ٹیکنالوجی اب ہر کسی کی پہنچ میں ہے۔",
    voice: DEFAULT_URDU_MALE_VOICE,
  },
  {
    id: "tts-hindi-native",
    name: "हिन्दी पाठ (Hindi narration)",
    description: "A single-voice Hindi narration in native script.",
    text: "स्वागत है! यह आवाज़ पूरी तरह आपके अपने कंप्यूटर पर बनाई जा रही है, बिना इंटरनेट के। आप कोई भी पाठ लिखें और उसे प्राकृतिक आवाज़ में सुनें। यह तकनीक अब हर किसी की पहुँच में है।",
    voice: DEFAULT_FEMALE_VOICE,
  },
];
```

- [ ] **Step 4: Typecheck**

Run: `cd frontend && npm run typecheck`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add frontend/src/lib/samples.ts
git commit -m "feat(samples): split podcast/tts catalogs + native Urdu/Hindi scripts"
```

---

## Task 2: Make `SampleMenu` mode-aware

**Files:**
- Modify: `frontend/src/components/SampleMenu.tsx`

- [ ] **Step 1: Update props + rendering**

Replace the props and the rendered list so the menu shows `PODCAST_SAMPLES` in podcast mode and `TTS_SAMPLES` in tts mode, calling the matching callback. Keep all existing styling (button, dropdown panel, row hover).

```tsx
import { useEffect, useRef, useState } from "react";
import { ChevronDown, Sparkles } from "lucide-react";
import { PODCAST_SAMPLES, TTS_SAMPLES, loadSample, loadTtsSample, type Sample, type TtsSample } from "@/lib/samples";
import type { ProjectMode } from "@/types/models";

interface Props {
  isDark: boolean;
  mode: ProjectMode;
  onLoadPodcast: (sample: Sample) => void;
  onLoadTts: (sample: TtsSample) => void;
}

export function SampleMenu({ isDark, mode, onLoadPodcast, onLoadTts }: Props) {
  const [open, setOpen] = useState(false);
  const ref = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (!open) return;
    const handler = (e: MouseEvent) => {
      if (ref.current && !ref.current.contains(e.target as Node)) setOpen(false);
    };
    document.addEventListener("mousedown", handler);
    return () => document.removeEventListener("mousedown", handler);
  }, [open]);

  return (
    <div className="relative" ref={ref}>
      <button
        type="button"
        onClick={() => setOpen((o) => !o)}
        className={`flex items-center gap-2 px-4 py-2.5 rounded-lg font-medium transition-colors border ${
          isDark
            ? "bg-zinc-800 hover:bg-zinc-700 text-zinc-300 hover:text-white border-zinc-700"
            : "bg-gray-100 hover:bg-gray-200 text-gray-700 hover:text-gray-900 border-gray-300"
        }`}
        title="Load a sample script"
      >
        <Sparkles className="w-4 h-4" />
        Samples
        <ChevronDown className="w-3.5 h-3.5" />
      </button>

      {open && (
        <div
          className={`absolute right-0 top-full mt-2 w-80 rounded-lg shadow-xl border z-30 overflow-hidden ${
            isDark ? "bg-zinc-900 border-zinc-800" : "bg-white border-gray-200"
          }`}
        >
          <div className={`p-2 text-xs uppercase tracking-wide font-semibold ${isDark ? "text-zinc-500" : "text-gray-500"}`}>
            Load a sample
          </div>
          <div className="max-h-96 overflow-y-auto">
            {mode === "podcast"
              ? PODCAST_SAMPLES.map((s) => (
                  <button
                    key={s.id}
                    type="button"
                    onClick={() => { onLoadPodcast(s); setOpen(false); }}
                    className={`block w-full text-left p-3 border-l-2 transition-colors ${
                      isDark ? "border-transparent hover:border-teal-500 hover:bg-zinc-800"
                             : "border-transparent hover:border-teal-500 hover:bg-gray-50"
                    }`}
                  >
                    <div className={`text-sm font-medium ${isDark ? "text-white" : "text-gray-900"}`}>{s.name}</div>
                    <div className={`text-xs mt-0.5 ${isDark ? "text-zinc-500" : "text-gray-500"}`}>{s.description}</div>
                    <div className={`text-xs mt-1 ${isDark ? "text-zinc-600" : "text-gray-400"}`}>
                      {s.speakers.length} speaker{s.speakers.length !== 1 ? "s" : ""} · {s.segments.length} segment{s.segments.length !== 1 ? "s" : ""}
                    </div>
                  </button>
                ))
              : TTS_SAMPLES.map((s) => (
                  <button
                    key={s.id}
                    type="button"
                    onClick={() => { onLoadTts(s); setOpen(false); }}
                    className={`block w-full text-left p-3 border-l-2 transition-colors ${
                      isDark ? "border-transparent hover:border-teal-500 hover:bg-zinc-800"
                             : "border-transparent hover:border-teal-500 hover:bg-gray-50"
                    }`}
                  >
                    <div className={`text-sm font-medium ${isDark ? "text-white" : "text-gray-900"}`}>{s.name}</div>
                    <div className={`text-xs mt-0.5 ${isDark ? "text-zinc-500" : "text-gray-500"}`}>{s.description}</div>
                  </button>
                ))}
          </div>
        </div>
      )}
    </div>
  );
}

export { PODCAST_SAMPLES, TTS_SAMPLES, loadSample, loadTtsSample };
export type { Sample, TtsSample };
```

- [ ] **Step 2: Typecheck**

Run: `cd frontend && npm run typecheck`
Expected: may FAIL where `App.tsx`/`MiddleToolbar` still pass the old `onLoad` prop — fixed in Task 3.

---

## Task 3: Wire `mode` + callbacks through `MiddleToolbar` and `App.tsx`

**Files:**
- Modify: `frontend/src/components/MiddleToolbar.tsx`
- Modify: `frontend/src/App.tsx`
- Modify: `frontend/src/lib/samples.ts` (remove the temporary `SAMPLES` alias)

- [ ] **Step 1: `MiddleToolbar` — pass mode + both sample callbacks**

Replace the `onLoadSample` prop with `mode: ProjectMode | null`, `onLoadPodcastSample: (s: Sample) => void`, `onLoadTtsSample: (s: TtsSample) => void`. Render `<SampleMenu mode={mode} onLoadPodcast={onLoadPodcastSample} onLoadTts={onLoadTtsSample} />` ONLY when `mode !== null` (the chooser has no Samples). Import `Sample`/`TtsSample` types. (`MiddleToolbar` already receives `mode` from Phase 2 for the ModeToggle — reuse it.)

- [ ] **Step 2: `App.tsx` — add the TTS sample handler + wire**

Add:
```tsx
const handleLoadTtsSample = useCallback((s: TtsSample) => {
  const { text, voiceId } = loadTtsSample(s);
  pm.setTtsText(text);
  // Use the suggested voice only if it exists in the current engine's voice list.
  if (voiceId && displayedVoices.some((v) => v.id === voiceId)) pm.setTtsVoice(voiceId);
}, [pm, displayedVoices]);
```
Update the existing `handleLoadSample` (podcast) — it stays as-is. Update the `MiddleToolbar` usage to pass `mode={pm.mode}`, `onLoadPodcastSample={handleLoadSample}`, `onLoadTtsSample={handleLoadTtsSample}`. Add `loadTtsSample` + `TtsSample` to the imports from `@/lib/samples` / types. Remove the old `onLoadSample` prop wiring.

- [ ] **Step 3: Remove the temporary alias** in `lib/samples.ts`

Delete `export const SAMPLES = PODCAST_SAMPLES;` (nothing should reference `SAMPLES` now — `SampleMenu` and `App` use `PODCAST_SAMPLES`/`loadSample`). Confirm with a search.

- [ ] **Step 4: Typecheck + build**

Run: `cd frontend && npm run typecheck && npm run build`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add frontend/src/components/SampleMenu.tsx frontend/src/components/MiddleToolbar.tsx frontend/src/App.tsx frontend/src/lib/samples.ts
git commit -m "feat(samples): mode-aware Samples menu (podcast vs tts)"
```

---

## Task 4: Light unit check (native scripts)

**Files:**
- Create: `frontend/src/lib/samples.test-notes.md` is NOT needed. Instead, a runtime assertion via the build is sufficient; this repo has no JS test runner. Do a manual grep verification:

- [ ] **Step 1: Verify native codepoints exist**

Run (from repo root):
```bash
cd frontend && node -e "const s=require('fs').readFileSync('src/lib/samples.ts','utf8'); console.log('urdu', /[؀-ۿ]/.test(s)); console.log('hindi', /[ऀ-ॿ]/.test(s));"
```
Expected: `urdu true` and `hindi true`.

---

## Task 5: Playwright verification

**Files:** none (controller-driven).

- [ ] **Step 1:** Ensure backend (:8880) + Vite (:5173) running.
- [ ] **Step 2:** Navigate to `http://localhost:5173`.
  1. In **Podcast** mode, open `Samples ▾` → the list includes "اردو پوڈکاسٹ" and "हिन्दी पॉडकास्ट" plus the English podcast samples. Click the Urdu one → segments load with Arabic-script text rendered RTL/correctly.
  2. Switch to **Text-to-Voice** mode, open `Samples ▾` → the list shows TTS samples ("English narration", "اردو تحریر", "हिन्दी पाठ"). Click the Hindi one → the textarea fills with Devanagari text; counts update.
  3. Confirm the chooser (mode === null) shows NO Samples button.
- [ ] **Step 3:** Screenshot both menus; confirm styling unchanged. Fix any issues (structural only) and re-verify.

---

## Self-Review (controller)

1. **Spec coverage:** split catalogs (Task 1), mode-aware menu (Task 2/3), native Urdu/Hindi in both podcast + tts (Task 1), TTS sample loads into the Phase 2 buffer (Task 3). ✅
2. **Type consistency:** `PODCAST_SAMPLES`/`TTS_SAMPLES`/`TtsSample`/`loadTtsSample` used consistently; old `SAMPLES`/`onLoad` removed. ✅
3. **No restyle:** SampleMenu markup/classes unchanged except the list source. ✅
