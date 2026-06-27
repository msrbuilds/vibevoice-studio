# OmniVoice Voice Design + Auto (Spec B) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Let OmniVoice reach its `design` (attribute-prompt) and `auto` (no-prompt) modes via a per-speaker Clone/Design/Auto toggle, threading `voice_mode` + `instruct` end-to-end, with no change to any other engine.

**Architecture:** Spec A already ships the OmniVoice worker (which speaks all three modes) and a clone-only proxy. Spec B adds two optional fields (`voice_mode`, `instruct`) carried per-speaker through TS → API → service → `EngineSynthRequest` → the proxy's mode-dispatching `_build_synth_msg`. The speaker's mode is *derived* (`omnivoiceMode ?? (voice ? "clone" : "auto")`) so switching engines never mutates state. Voice resolution + cache keys skip/diverge for design/auto so they need no reference voice and never collide.

**Tech Stack:** Python / FastAPI (backend, tests via `backend/venv`); React + TypeScript + Vite + Tailwind (frontend, verified by `tsc` typecheck + `vite build` — the project has no JS test runner, matching prior features).

**Reference spec:** `docs/superpowers/specs/2026-06-28-omnivoice-voice-design-spec-b.md`

**Conventions:** Backend tests: `cd backend && ./venv/Scripts/python.exe -m pytest …`. Frontend: from `frontend/`. Exact paths throughout.

---

## File Structure

- **Modify** `backend/core/engines/__init__.py` — `EngineSynthRequest` gains `voice_mode`, `instruct`.
- **Modify** `backend/api/schemas.py` — `SynthSpeakerModel` relaxes `voice`, adds `voice_mode`/`instruct`.
- **Modify** `backend/services/synthesize.py` — `Speaker` dataclass +2 fields; `_voice_cache_key` helper; resolution skip + request threading + cache-key fold.
- **Modify** `backend/api/synthesize.py` — pass the two new fields when building service `Speaker`s.
- **Modify** `backend/core/engines/omnivoice_engine.py` — `_build_synth_msg` dispatches all three modes.
- **Create** `backend/tests/test_voice_design.py` — schema + cache-key + service-resolution tests.
- **Modify** `backend/tests/test_omnivoice_proxy.py` — update/extend `_build_synth_msg` tests.
- **Modify** `frontend/src/types/models.ts` — `Speaker`, `SynthSpeaker`, `CachedAudio` gain fields.
- **Create** `frontend/src/lib/omnivoice.ts` — `OmniMode`, `effectiveMode`, `appendDesignChip`, `DESIGN_CHIPS`.
- **Modify** `frontend/src/components/Sidebar.tsx` — `SpeakerRow` toggle + design/auto inputs; thread `activeEngine`.
- **Modify** `frontend/src/App.tsx` — `generateFor` guard + payload; `isSegmentCached` mode-aware; `cacheAudio` stores mode/instruct.

---

## Task 1: Request fields (`voice_mode` + `instruct`) through the data layer

**Files:**
- Modify: `backend/core/engines/__init__.py`
- Modify: `backend/api/schemas.py`
- Modify: `backend/services/synthesize.py` (the `Speaker` dataclass only)
- Modify: `backend/api/synthesize.py`
- Test: `backend/tests/test_voice_design.py`

- [ ] **Step 1: Write the failing test**

Create `backend/tests/test_voice_design.py`:

```python
"""Spec B: OmniVoice voice_mode/instruct plumbing, cache-key divergence,
and design/auto voice-resolution skipping. No real model required."""

import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT))


def test_synth_speaker_model_allows_empty_voice_with_mode():
    from backend.api.schemas import SynthSpeakerModel
    m = SynthSpeakerModel(name="A", voice="", voice_mode="design", instruct="female, warm")
    assert m.voice == ""
    assert m.voice_mode == "design"
    assert m.instruct == "female, warm"


def test_synth_speaker_model_defaults():
    from backend.api.schemas import SynthSpeakerModel
    m = SynthSpeakerModel(name="A", voice="v")
    assert m.voice_mode is None
    assert m.instruct is None


def test_engine_synth_request_has_mode_fields():
    from backend.core.engines import EngineSynthRequest
    r = EngineSynthRequest(text="x", voice_id="v", voice_mode="auto", instruct=None)
    assert r.voice_mode == "auto"
    assert r.instruct is None
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd backend && ./venv/Scripts/python.exe -m pytest tests/test_voice_design.py::test_engine_synth_request_has_mode_fields -v`
Expected: FAIL with `TypeError: __init__() got an unexpected keyword argument 'voice_mode'`

- [ ] **Step 3: Implement**

In `backend/core/engines/__init__.py`, add two fields to the `EngineSynthRequest` dataclass, right after the existing `language_id` field:

```python
    language_id: str | None = None
    # --- OmniVoice only (other engines ignore) ---
    # Voice generation mode: "clone" (ref_audio), "design" (instruct), "auto".
    voice_mode: str | None = None
    # Free-text speaker-attribute prompt used when voice_mode == "design".
    instruct: str | None = None
```

In `backend/api/schemas.py`, update `SynthSpeakerModel` (currently `voice: str = Field(..., min_length=1, …)`):

```python
class SynthSpeakerModel(BaseModel):
    name: str = Field(..., min_length=1, max_length=64)
    # Voice id (filename stem). Empty is allowed for OmniVoice design/auto
    # modes, which carry no reference voice; clone-mode "voice required" is
    # enforced downstream by voice resolution.
    voice: str = Field("", max_length=256, description="Voice id; may be empty for OmniVoice design/auto")
    # OmniVoice only: "clone" | "design" | "auto". None for other engines.
    voice_mode: Literal["clone", "design", "auto"] | None = None
    # OmniVoice design-mode attribute prompt.
    instruct: str | None = None
```

In `backend/services/synthesize.py`, add two fields to the `Speaker` dataclass (top of file, after `voice_id`):

```python
@dataclass
class Speaker:
    """One speaker in a script."""
    name: str
    voice_id: str  # VoiceRegistry id (i.e. filename stem)
    voice_mode: str | None = None  # OmniVoice: clone|design|auto
    instruct: str | None = None    # OmniVoice design-mode prompt
```

In `backend/api/synthesize.py`, thread the fields when building service speakers (the `ServiceSpeaker(...)` list comprehension):

```python
                speakers=[
                    ServiceSpeaker(
                        name=sp.name,
                        voice_id=sp.voice,
                        voice_mode=sp.voice_mode,
                        instruct=sp.instruct,
                    )
                    for sp in body.speakers
                ],
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd backend && ./venv/Scripts/python.exe -m pytest tests/test_voice_design.py -v`
Expected: PASS (3 passed)

- [ ] **Step 5: Run full suite (no regressions)**

Run: `cd backend && ./venv/Scripts/python.exe -m pytest tests/ -q`
Expected: PASS, 0 failures.

- [ ] **Step 6: Commit**

```bash
git add backend/core/engines/__init__.py backend/api/schemas.py backend/services/synthesize.py backend/api/synthesize.py backend/tests/test_voice_design.py
git commit -m "feat: thread voice_mode/instruct through the synth request layer"
```

---

## Task 2: Proxy `_build_synth_msg` mode dispatch

**Files:**
- Modify: `backend/core/engines/omnivoice_engine.py`
- Modify: `backend/tests/test_omnivoice_proxy.py`

- [ ] **Step 1: Update + add tests**

In `backend/tests/test_omnivoice_proxy.py`, **replace** the existing `test_build_synth_msg_requires_reference_audio` with a version matching the new semantics (only *explicit clone* without a ref raises), and **append** the design/auto tests:

```python
def test_build_synth_msg_clone_requires_reference_audio():
    eng = OmniVoiceEngine(worker_python=Path("x"), worker_script=Path("y"))
    req = EngineSynthRequest(text="hi", voice_id="v", voice_mode="clone")  # explicit clone, no ref
    with pytest.raises(ValueError):
        eng._build_synth_msg(req, "/out.wav")


def test_build_synth_msg_design():
    eng = OmniVoiceEngine(worker_python=Path("x"), worker_script=Path("y"), num_step=20)
    req = EngineSynthRequest(text="hi", voice_id="", voice_mode="design", instruct="female, british accent")
    msg = eng._build_synth_msg(req, "/out.wav")
    assert msg["mode"] == "design"
    assert msg["instruct"] == "female, british accent"
    assert "ref_audio" not in msg
    assert msg["num_step"] == 20


def test_build_synth_msg_empty_design_becomes_auto():
    eng = OmniVoiceEngine(worker_python=Path("x"), worker_script=Path("y"))
    req = EngineSynthRequest(text="hi", voice_id="", voice_mode="design", instruct="   ")
    msg = eng._build_synth_msg(req, "/out.wav")
    assert msg["mode"] == "auto"
    assert "instruct" not in msg


def test_build_synth_msg_auto():
    eng = OmniVoiceEngine(worker_python=Path("x"), worker_script=Path("y"))
    req = EngineSynthRequest(text="hi", voice_id="", voice_mode="auto")
    msg = eng._build_synth_msg(req, "/out.wav")
    assert msg["mode"] == "auto"
    assert "ref_audio" not in msg
    assert "instruct" not in msg
```

(The existing `test_build_synth_msg_clone` — which passes `reference_audio` and no `voice_mode` — stays and still passes: with a ref present and no explicit mode, the message resolves to clone.)

- [ ] **Step 2: Run to verify the new tests fail**

Run: `cd backend && ./venv/Scripts/python.exe -m pytest tests/test_omnivoice_proxy.py -k "design or auto or clone_requires" -v`
Expected: FAIL (current `_build_synth_msg` raises for missing ref regardless of mode and ignores `voice_mode`/`instruct`).

- [ ] **Step 3: Implement**

In `backend/core/engines/omnivoice_engine.py`, **replace** the entire `_build_synth_msg` method with:

```python
    def _build_synth_msg(self, req: EngineSynthRequest, out_wav: str) -> dict:
        """Build the worker 'synth' message, dispatching on voice_mode.

        Mode resolution mirrors the frontend's effective-mode rule: an
        explicit req.voice_mode wins; otherwise clone if a reference voice is
        present, else auto. An empty design prompt downgrades to auto so a
        blank box never errors.
        """
        text = (req.text or "").strip()
        if not text:
            raise ValueError("text must be non-empty")
        mode = req.voice_mode or ("clone" if req.reference_audio else "auto")
        instruct = (req.instruct or "").strip()
        if mode == "design" and not instruct:
            mode = "auto"
        msg: dict[str, Any] = {
            "op": "synth",
            "mode": mode,
            "text": text,
            "out_wav": out_wav,
        }
        if mode == "clone":
            if not req.reference_audio:
                raise ValueError("OmniVoice clone mode requires a reference voice.")
            msg["ref_audio"] = req.reference_audio
        elif mode == "design":
            msg["instruct"] = instruct
        if req.speed is not None:
            msg["speed"] = float(req.speed)
        if self._num_step is not None:
            msg["num_step"] = int(self._num_step)
        return msg
```

(The `synthesize()` method is unchanged — it already calls `self._build_synth_msg(req, out_wav)`.)

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd backend && ./venv/Scripts/python.exe -m pytest tests/test_omnivoice_proxy.py -v`
Expected: PASS (all, including the clone/design/auto cases).

- [ ] **Step 5: Commit**

```bash
git add backend/core/engines/omnivoice_engine.py backend/tests/test_omnivoice_proxy.py
git commit -m "feat: OmniVoice proxy dispatches clone/design/auto modes"
```

---

## Task 3: Service voice-resolution skip + cache-key divergence

**Files:**
- Modify: `backend/services/synthesize.py`
- Test: `backend/tests/test_voice_design.py`

- [ ] **Step 1: Write the failing tests**

Append to `backend/tests/test_voice_design.py`:

```python
import numpy as np  # noqa: E402

from backend.core.engines import EngineResult, EngineSynthRequest, wrap_pcm_as_wav  # noqa: E402
from backend.services.synthesize import (  # noqa: E402
    SynthRequest,
    SynthService,
    Speaker,
    _voice_cache_key,
)


def test_voice_cache_key_diverges_by_mode_and_prompt():
    k_clone = _voice_cache_key("v", "clone", None, "/voices/v.wav")
    k_auto = _voice_cache_key("", "auto", None, None)
    k_d1 = _voice_cache_key("", "design", "female", None)
    k_d2 = _voice_cache_key("", "design", "male", None)
    assert len({k_clone, k_auto, k_d1, k_d2}) == 4          # all distinct
    assert _voice_cache_key("", "design", "female", None) == k_d1  # stable
    # Other engines (voice_mode None) keep their existing keys — no cache churn.
    assert _voice_cache_key("v", None, None, "/voices/v.wav") == "v.wav"
    assert _voice_cache_key("v", None, None, None) == "v"


class _StubEngine:
    name = "omnivoice"
    display_name = "OmniVoice"

    def __init__(self):
        self.last_req = None

    def is_loaded(self):
        return True

    def load(self):
        pass

    def max_speakers(self):
        return 1

    def supports_voice_cloning(self):
        return True

    def supports_streaming(self):
        return False

    def default_cfg_scale(self):
        return None

    def synthesize(self, req):
        self.last_req = req
        return EngineResult(
            wav_bytes=wrap_pcm_as_wav(np.zeros(100, dtype=np.int16), 24000),
            sample_rate=24000,
            duration_sec=100 / 24000,
            inference_ms=1,
        )


class _StubManager:
    def __init__(self, eng):
        self._eng = eng

    @property
    def active_engine(self):
        return self._eng

    @property
    def active_name(self):
        return "omnivoice"

    def get_engine(self, name):
        return self._eng


class _StubVoices:
    def get(self, voice_id):
        return f"/voices/{voice_id}.wav"

    def get_language(self, voice_id):
        return None


def _make_service():
    eng = _StubEngine()
    svc = SynthService(
        engine_manager=_StubManager(eng),
        voice_registry=_StubVoices(),
        max_text_chars=5000,
        synth_timeout_s=30,
        default_cfg_scale=1.0,
        cache=None,  # cache disabled keeps the test focused on resolution/threading
    )
    return svc, eng


def test_design_request_skips_voice_and_threads_mode():
    svc, eng = _make_service()
    svc.synthesize(SynthRequest(
        text="hello",
        speakers=[Speaker(name="A", voice_id="", voice_mode="design", instruct="female, warm")],
    ))
    assert eng.last_req.voice_mode == "design"
    assert eng.last_req.instruct == "female, warm"
    assert eng.last_req.reference_audio is None


def test_auto_request_needs_no_voice():
    svc, eng = _make_service()
    svc.synthesize(SynthRequest(
        text="hello",
        speakers=[Speaker(name="A", voice_id="", voice_mode="auto")],
    ))
    assert eng.last_req.voice_mode == "auto"
    assert eng.last_req.reference_audio is None


def test_clone_request_resolves_reference_audio():
    svc, eng = _make_service()
    svc.synthesize(SynthRequest(
        text="hello",
        speakers=[Speaker(name="A", voice_id="v", voice_mode="clone")],
    ))
    assert eng.last_req.reference_audio == "/voices/v.wav"
    assert eng.last_req.voice_mode == "clone"
```

- [ ] **Step 2: Run to verify it fails**

Run: `cd backend && ./venv/Scripts/python.exe -m pytest tests/test_voice_design.py -k "cache_key or design_request or auto_request or clone_request" -v`
Expected: FAIL — `ImportError: cannot import name '_voice_cache_key'` (and the resolution tests would raise/thread wrong until implemented).

- [ ] **Step 3: Implement**

In `backend/services/synthesize.py`, add this module-level helper (near the other helpers at the bottom, e.g. after `_build_script`):

```python
def _voice_cache_key(voice_id: str, voice_mode: str | None, instruct: str | None,
                     reference_audio: str | None) -> str:
    """Cache-key 'voice' component, folding OmniVoice mode/instruct.

    For other engines (voice_mode None) this returns exactly what the old
    inline logic did, so their cache entries don't churn. For OmniVoice it
    keeps clone/design/auto and distinct design prompts in separate slots.
    """
    if reference_audio:
        base = Path(reference_audio).name
    elif voice_mode in ("design", "auto"):
        base = f"{voice_mode}:{instruct or ''}"
    else:
        base = voice_id
    if voice_mode:
        base += f"|vm={voice_mode}"
        if instruct:
            base += f"|in={instruct}"
    return base
```

In `_resolve_request_context`, replace the speaker-resolution loop (currently resolves `reference_audio`/`voice_language` for every speaker) with a mode-aware version:

```python
        # Resolve reference audio (clone mode only) + voice language.
        reference_audio: str | None = None
        voice_language: str | None = None
        for sp in req.speakers:
            sp_mode = sp.voice_mode or ("clone" if sp.voice_id else "auto")
            if sp_mode != "clone":
                continue  # design/auto carry no reference voice
            if target_engine.supports_voice_cloning():
                reference_audio = str(self._voices.get(sp.voice_id))
            voice_language = voice_language or self._voices.get_language(sp.voice_id)
```

In `synthesize()`, thread the fields into the single-speaker `EngineSynthRequest` (the fast path) — add `voice_mode`/`instruct` from `req.speakers[0]`:

```python
        if len(speaker_chunks) <= 1 and len(req.speakers) <= 1:
            sp0 = req.speakers[0]
            engine_req = EngineSynthRequest(
                text=speaker_chunks[0] if speaker_chunks else text,
                voice_id=sp0.voice_id,
                speed=req.speed,
                cfg_scale=cfg,
                reference_audio=reference_audio,
                inference_steps=steps_override,
                disable_prefill=req.disable_prefill,
                voice_mode=sp0.voice_mode,
                instruct=sp0.instruct,
            )
            return self._synth_one(
                engine=target_engine,
                engine_name=target_name,
                engine_req=engine_req,
                cache_hash_for_write=content_hash,
            )
```

Still in `synthesize()`, update the cache-key block to use the helper (replace the `cache_voice_key = …` line and the `voice_samples=[…]` arg):

```python
        content_hash: str | None = None
        if self._cache is not None and self._cache.enabled:
            sp0 = req.speakers[0]
            cache_voice_key = _voice_cache_key(
                sp0.voice_id, sp0.voice_mode, sp0.instruct, reference_audio
            )
            # Fold the optional knobs into the voice field with a stable
            # delimiter so different knob combos don't share a cache slot.
            extra = ""
            if effective_cfg_weight is not None:
                extra += f"|cw={effective_cfg_weight:.3f}"
            if effective_exaggeration is not None:
                extra += f"|ex={effective_exaggeration:.3f}"
            if effective_language_id:
                extra += f"|lang={effective_language_id}"
            content_hash = compute_hash(
                text=req.text,
                voice=cache_voice_key + extra,
                cfg_scale=cfg,
                voice_samples=[reference_audio or cache_voice_key],
            )
            hit = self._cache.get(content_hash)
            if hit is not None and not req.force_regenerate:
                log.info(
                    "Cache hit for %s (%.1fs audio, engine=%s)",
                    content_hash, hit.duration_sec, target_name,
                )
                return SynthResult(
                    wav_bytes=hit.wav_path.read_bytes(),
                    sample_rate=hit.sample_rate,
                    duration_sec=hit.duration_sec,
                    inference_ms=hit.inference_ms,
                    cache_hash=content_hash,
                    cache_hit=True,
                    engine=target_name,
                )
```

(This preserves the existing cfg/exaggeration/language folding and the hit/return logic; only the `cache_voice_key` derivation and `voice_samples` entry change.)

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd backend && ./venv/Scripts/python.exe -m pytest tests/test_voice_design.py -v`
Expected: PASS (all).

- [ ] **Step 5: Run the full backend suite**

Run: `cd backend && ./venv/Scripts/python.exe -m pytest tests/ -q`
Expected: PASS, 0 failures (existing cache/synth tests unaffected — other engines' keys unchanged).

- [ ] **Step 6: Commit**

```bash
git add backend/services/synthesize.py backend/tests/test_voice_design.py
git commit -m "feat: skip voice resolution + diverge cache key for OmniVoice design/auto"
```

---

## Task 4: Frontend types + OmniVoice helpers

**Files:**
- Modify: `frontend/src/types/models.ts`
- Create: `frontend/src/lib/omnivoice.ts`

- [ ] **Step 1: Add the types**

In `frontend/src/types/models.ts`:
- Extend `Speaker` (add after `color: string;`):
```typescript
  color: string;
  // OmniVoice only: per-speaker voice mode + design prompt (optional; other
  // engines ignore). Mode is derived when unset — see lib/omnivoice.ts.
  omnivoiceMode?: "clone" | "design" | "auto";
  voiceDesign?: string;
```
- Extend `SynthSpeaker` (the request payload type):
```typescript
export interface SynthSpeaker {
  name: string;
  voice: string; // Voice.id (may be empty for OmniVoice design/auto)
  voice_mode?: "clone" | "design" | "auto";
  instruct?: string;
}
```
- Extend `CachedAudio` (add the two fields):
```typescript
export interface CachedAudio {
  audioData: ArrayBuffer;
  text: string;
  voice: string;
  cacheHash?: string;
  // OmniVoice: what mode/prompt produced this, so the cached badge stays honest.
  mode?: "clone" | "design" | "auto";
  instruct?: string;
}
```

- [ ] **Step 2: Create the helper module**

Create `frontend/src/lib/omnivoice.ts`:

```typescript
// OmniVoice per-speaker voice-mode helpers (Spec B).

export type OmniMode = "clone" | "design" | "auto";

// One-tap chips that append to the design prompt. Order = display order.
export const DESIGN_CHIPS: string[] = [
  "female",
  "male",
  "low pitch",
  "high pitch",
  "british accent",
  "american accent",
  "whisper",
  "energetic",
  "calm",
];

/**
 * The speaker's effective OmniVoice mode. An explicit choice wins; otherwise
 * clone if a reference voice is set, else auto. Keeping it derived means
 * switching engines never mutates speaker state.
 */
export function effectiveMode(speaker: { voice: string; omnivoiceMode?: OmniMode }): OmniMode {
  return speaker.omnivoiceMode ?? (speaker.voice ? "clone" : "auto");
}

/** Append a chip to a design prompt, de-duping (comma-separated, case-insensitive). */
export function appendDesignChip(text: string, chip: string): string {
  const t = (text ?? "").trim();
  if (!t) return chip;
  const parts = t.toLowerCase().split(/,\s*/);
  if (parts.includes(chip.toLowerCase())) return t;
  return `${t}, ${chip}`;
}
```

- [ ] **Step 3: Typecheck**

Run: `cd frontend && npm run typecheck`
Expected: PASS (new fields are optional; no consumer breaks yet).

- [ ] **Step 4: Commit**

```bash
git add frontend/src/types/models.ts frontend/src/lib/omnivoice.ts
git commit -m "feat: OmniVoice speaker types + effectiveMode/chip helpers"
```

---

## Task 5: `SpeakerRow` — Clone/Design/Auto toggle + inputs

**Files:**
- Modify: `frontend/src/components/Sidebar.tsx`

- [ ] **Step 1: Thread `activeEngine` into `SpeakerRow`**

In `frontend/src/components/Sidebar.tsx`:
- The `Sidebar` `Props` already include `activeEngine: string | null;`. Destructure it in the component signature (add `activeEngine,` to the destructured params — it is currently declared in `Props` but not pulled out).
- Pass it to each `SpeakerRow` in the `.map` (add `activeEngine={activeEngine}` to the `<SpeakerRow … />` props).

- [ ] **Step 2: Add the toggle + mode inputs to `SpeakerRow`**

Add the import at the top of `Sidebar.tsx`:
```typescript
import { DESIGN_CHIPS, appendDesignChip, effectiveMode, type OmniMode } from "@/lib/omnivoice";
```

Extend the `SpeakerRow` prop type with `activeEngine: string | null;` and destructure it. Then, inside `SpeakerRow`, replace the bare voice `<select>` (the JSX from `<select value={speaker.voice} …>` through `</select>`) with engine-aware rendering. Compute the mode and render the toggle + the mode-specific input:

```tsx
  const isOmni = activeEngine === "omnivoice";
  const mode: OmniMode = effectiveMode(speaker);
  const setMode = (m: OmniMode) => onUpdate({ omnivoiceMode: m });

  const voiceSelect = (
    <select
      value={speaker.voice}
      onChange={(e) => onSetVoice(e.target.value)}
      className={`w-full border rounded-md px-2 py-1.5 text-xs focus:outline-none focus:border-teal-500 ${selectBg} ${selectBorder} ${selectText}`}
    >
      <option value="">Select voice…</option>
      {voices.map((v) => (
        <option key={v.id} value={v.id}>
          {v.name} {v.source === "upload" ? "(mine)" : ""}
        </option>
      ))}
    </select>
  );

  if (!isOmni) {
    return (
      <div className={`p-3 rounded-lg border ${panelBg} ${panelBorder}`}>
        {nameHeader}
        {voiceSelect}
      </div>
    );
  }

  const segBtn = (m: OmniMode, label: string) => (
    <button
      type="button"
      onClick={() => setMode(m)}
      className={`flex-1 px-2 py-1 text-[11px] font-medium rounded transition-colors ${
        mode === m
          ? "bg-teal-600 text-white"
          : isDark
            ? "bg-zinc-800 text-zinc-300 hover:bg-zinc-700"
            : "bg-gray-100 text-gray-600 hover:bg-gray-200"
      }`}
    >
      {label}
    </button>
  );

  return (
    <div className={`p-3 rounded-lg border ${panelBg} ${panelBorder}`}>
      {nameHeader}
      <div className="flex gap-1 mb-2">
        {segBtn("clone", "Clone")}
        {segBtn("design", "Design")}
        {segBtn("auto", "Auto")}
      </div>
      {mode === "clone" && voiceSelect}
      {mode === "design" && (
        <div className="space-y-1.5">
          <input
            type="text"
            value={speaker.voiceDesign ?? ""}
            onChange={(e) => onUpdate({ voiceDesign: e.target.value })}
            placeholder="e.g. female, low pitch, british accent, warm"
            className={`w-full border rounded-md px-2 py-1.5 text-xs focus:outline-none focus:border-teal-500 ${selectBg} ${selectBorder} ${selectText}`}
          />
          <div className="flex flex-wrap gap-1">
            {DESIGN_CHIPS.map((chip) => (
              <button
                key={chip}
                type="button"
                onClick={() => onUpdate({ voiceDesign: appendDesignChip(speaker.voiceDesign ?? "", chip) })}
                className={`px-1.5 py-0.5 text-[10px] rounded border transition-colors ${
                  isDark
                    ? "border-zinc-700 text-zinc-400 hover:border-teal-500 hover:text-teal-300"
                    : "border-gray-300 text-gray-500 hover:border-teal-500 hover:text-teal-600"
                }`}
              >
                {chip}
              </button>
            ))}
          </div>
        </div>
      )}
      {mode === "auto" && (
        <p className={`text-[11px] italic ${isDark ? "text-zinc-500" : "text-gray-500"}`}>
          OmniVoice will invent a voice for this speaker.
        </p>
      )}
    </div>
  );
```

To make the shared name-header reusable, extract the existing header block (the `<div className="flex items-center gap-2 mb-2">…</div>` containing the color dot, name input, and delete button) into a `const nameHeader = (…)` defined just before these returns, and use it in both branches. (Cut the existing header JSX, assign it to `nameHeader`, and reference it as shown.)

- [ ] **Step 3: Typecheck + build**

Run: `cd frontend && npm run typecheck`
Expected: PASS.
Run: `cd frontend && npm run build`
Expected: PASS.

- [ ] **Step 4: Commit**

```bash
git add frontend/src/components/Sidebar.tsx
git commit -m "feat: per-speaker Clone/Design/Auto toggle for OmniVoice"
```

---

## Task 6: `App.tsx` — generate guard, request payload, cached badge

**Files:**
- Modify: `frontend/src/App.tsx`

- [ ] **Step 1: Import the helper + make `isSegmentCached` mode-aware**

In `frontend/src/App.tsx`:
- Add the import near the other `@/lib` imports:
```typescript
import { effectiveMode } from "@/lib/omnivoice";
```
- Replace the `isSegmentCached` function (lines ~25–37) with a mode-aware version that takes `activeEngine`:
```typescript
function isSegmentCached(
  segment: { id: string; text: string; speakerId: string | null },
  cache: Record<string, CachedAudio>,
  speakers: Speaker[],
  activeEngine: string | null,
): { cached: boolean; voice: string | null; signature: string } {
  const entry = cache[segment.id];
  if (!entry) return { cached: false, voice: null, signature: "" };
  const speaker = speakers.find((s) => s.id === segment.speakerId);
  if (!speaker) return { cached: false, voice: null, signature: "" };

  if (activeEngine === "omnivoice") {
    const mode = effectiveMode(speaker);
    if (mode === "clone") {
      const voice = speaker.voice;
      if (!voice) return { cached: false, voice: null, signature: "" };
      const signature = `${segment.text}::${voice}::clone`;
      return {
        cached: entry.text === segment.text && entry.voice === voice && (entry.mode ?? "clone") === "clone",
        voice,
        signature,
      };
    }
    const design = mode === "design" ? (speaker.voiceDesign ?? "") : "";
    const signature = `${segment.text}::${mode}::${design}`;
    return {
      cached:
        entry.text === segment.text &&
        entry.mode === mode &&
        (entry.instruct ?? "") === design,
      voice: null,
      signature,
    };
  }

  const voice = speaker.voice;
  if (!voice) return { cached: false, voice: null, signature: "" };
  const signature = `${segment.text}::${voice}::${segment.speakerId ?? ""}`;
  return { cached: entry.text === segment.text && entry.voice === voice, voice, signature };
}
```
- Update all `isSegmentCached(…)` call sites to pass `activeEngine` as the 4th arg. There are five calls (lines ~223, ~280, ~350, ~491, ~630); each currently ends `…, project.speakers)` — change to `…, project.speakers, activeEngine)`.

- [ ] **Step 2: Update `generateFor` (guard + payload + cache write)**

Replace the body of `generateFor` (the guard, the `speakers` array, the `synthesizeWav` call, and the `cacheAudio` write) with mode-aware logic:

```typescript
  const generateFor = useCallback(
    async (segmentId: string, options: { forceRegenerate?: boolean } = {}) => {
      const seg = project.segments.find((s) => s.id === segmentId);
      if (!seg || !seg.text.trim()) return;
      const speaker = project.speakers.find((s) => s.id === seg.speakerId);
      if (!speaker) {
        showError("No speaker assigned to this segment.", "No speaker");
        return;
      }
      const isOmni = activeEngine === "omnivoice";
      const mode = isOmni ? effectiveMode(speaker) : "clone";
      // A reference voice is required except for OmniVoice design/auto.
      if (mode === "clone" && !speaker.voice) {
        showError("No voice assigned to the speaker. Pick one in the sidebar.", "No voice");
        return;
      }
      const instruct = mode === "design" ? (speaker.voiceDesign ?? "") : undefined;
      const speakers: SynthSpeaker[] = [
        {
          name: speaker.name,
          voice: speaker.voice,
          ...(isOmni ? { voice_mode: mode } : {}),
          ...(instruct ? { instruct } : {}),
        },
      ];

      setGeneratingId(segmentId);
      try {
        const isChatterbox = activeEngine === "chatterbox";
        const { audioData, cacheHash } = await synthesizeWav(seg.text, speakers, cfgScale, {
          forceRegenerate: options.forceRegenerate,
          cfgWeight: isChatterbox ? cfgScale : null,
          exaggeration: isChatterbox ? exaggeration : null,
        });
        project.cacheAudio(segmentId, {
          audioData,
          text: seg.text,
          voice: speaker.voice,
          ...(cacheHash ? { cacheHash } : {}),
          ...(isOmni ? { mode } : {}),
          ...(instruct ? { instruct } : {}),
        });
      } catch (err: unknown) {
        showError(err, "Synthesis failed");
      } finally {
        setGeneratingId(null);
      }
    },
    [project, showError, cfgScale, exaggeration, activeEngine],
  );
```

(Note: `exaggeration` is added to the dependency array since it's now referenced; it was already used in the body previously.)

- [ ] **Step 3: Typecheck + build**

Run: `cd frontend && npm run typecheck`
Expected: PASS. (If `SynthSpeaker` import is missing in App.tsx, it's already imported — it's used by the existing `generateFor`.)
Run: `cd frontend && npm run build`
Expected: PASS.

- [ ] **Step 4: Commit**

```bash
git add frontend/src/App.tsx
git commit -m "feat: wire OmniVoice design/auto through generate + cached badge"
```

---

## Final verification

- [ ] **Backend suite green:** `cd backend && ./venv/Scripts/python.exe -m pytest tests/ -q` → all pass.
- [ ] **Frontend green:** `cd frontend && npm run typecheck && npm run build` → both pass.
- [ ] **Manual smoke (needs the OmniVoice venv installed):** with OmniVoice active, a speaker shows the Clone/Design/Auto toggle; Design reveals a prompt box + chips and generates from the prompt; Auto generates with no voice; Clone behaves as before. Switching to VibeVoice/Kokoro/Chatterbox shows the plain voice dropdown (no toggle) and the "No voice assigned" error still fires when appropriate.
- [ ] **Update `CLAUDE.md`:** flip the OmniVoice note from "clone-only today (Spec A)" to "clone/design/auto via a per-speaker mode toggle".

---

## Self-Review (completed by plan author)

**Spec coverage:**
- `Speaker` + `SynthSpeaker` + `CachedAudio` fields, `effectiveMode`, chips → Tasks 4, 5. ✓
- Per-speaker toggle + mode inputs (OmniVoice-only) → Task 5. ✓
- `voice_mode`/`instruct` per-speaker through TS→API→service→EngineSynthRequest→proxy → Tasks 1, 2, 3, 6. ✓
- `_build_synth_msg` all three modes incl. empty-design→auto → Task 2. ✓
- Voice-resolution skip for design/auto + cache-key divergence → Task 3. ✓
- OmniVoice-gated "no voice" guard → Task 6. ✓
- Cached-badge honesty → Task 6 (`isSegmentCached` + `cacheAudio`). ✓
- Other engines unaffected (voice_mode None → old paths; cache keys unchanged) → Tasks 1, 3, 6 by construction. ✓
- Tests: schema (T1), proxy modes (T2), cache-key + resolution (T3); frontend via typecheck/build (T4–6). ✓

**Placeholder scan:** none — every code step shows full code/commands.

**Type/name consistency:** `voice_mode`/`instruct` names identical across `EngineSynthRequest` (T1), `SynthSpeakerModel` (T1), service `Speaker` (T1), `_build_synth_msg` (T2), `_voice_cache_key` (T3), and the TS `SynthSpeaker` (T4). `effectiveMode`/`appendDesignChip`/`DESIGN_CHIPS`/`OmniMode` consistent across `lib/omnivoice.ts` (T4), `Sidebar.tsx` (T5), `App.tsx` (T6). `CachedAudio.mode`/`instruct` written in `generateFor` (T6) and read in `isSegmentCached` (T6). The proxy's mode-resolution default matches the frontend `effectiveMode` rule.
