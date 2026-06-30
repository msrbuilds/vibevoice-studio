# Qwen Voice Modes (Custom / Clone / Design) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Convert the shipped built-in-only Qwen engine into a full multi-mode engine exposing the model's three real generation methods — **Custom** (9 built-in speakers + style), **Clone** (reference clip, ICL when a transcript exists else x-vector-only), and **Design** (free-text voice from a prompt) — via the existing per-speaker voice-mode toggle.

**Architecture:** The model `Qwen/Qwen3-TTS-12Hz-1.7B-CustomVoice` exposes `generate_custom_voice(text, speaker, language, instruct)`, `generate_voice_clone(text, language, ref_audio, ref_text, x_vector_only_mode)`, and `generate_voice_design(text, instruct, language)` (verified live via `inspect.signature`). We make `QwenEngine` a `supports_voice_modes` engine (like OmniVoice/VoxCPM), add a new `"custom"` mode to the shared mode system (the existing modes are `clone`/`design`/`auto`), reinterpret `voice_id` per-mode (built-in speaker in Custom, reference clip in Clone), and dispatch in the worker. The previously-shipped `supports_style_prompt` always-on field is **removed** — modes subsume it.

**Tech Stack:** Python isolated venv `backend/venv-qwen` (`qwen-tts`, `transformers==4.57.3`), FastAPI, React + TS + Vite + Tailwind. Backend tests via `./backend/venv/Scripts/python.exe -m pytest`; frontend via `npm run typecheck` / `npm test` from `frontend/`.

**Real API contract (verified against the installed package):**
- `generate_custom_voice(text, speaker, language=None, instruct=None, ...) -> (List[np.ndarray], int)` — `speaker` must be one of `get_supported_speakers()` (lowercased: `aiden,dylan,eric,ono_anna,ryan,serena,sohee,uncle_fu,vivian`); `language`/`instruct` lowercase-normalized vocab.
- `generate_voice_clone(text, language=None, ref_audio=None, ref_text=None, x_vector_only_mode=False, ...) -> (List[np.ndarray], int)` — `ref_audio` = wav path; `x_vector_only_mode=True` ignores `ref_text`; `False` (ICL) **requires** `ref_text`.
- `generate_voice_design(text, instruct, language=None, ...) -> (List[np.ndarray], int)` — `instruct` required (empty allowed = no instruction).
- Languages: lowercase full names, already normalized by `_normalize_language` (shipped).

**Mode model:**
| Qwen mode | UI label | method | needs |
|---|---|---|---|
| `custom` | "Custom voice" | `generate_custom_voice` | built-in speaker (voice_id) + optional style |
| `clone` | "Clone" | `generate_voice_clone` | reference clip (resolved WAV) + optional transcript |
| `design` | "Design" | `generate_voice_design` | free-text style (required) |

**Engine identity (unchanged):** name `qwen`, model `Qwen/Qwen3-TTS-12Hz-1.7B-CustomVoice`, venv `backend/venv-qwen`.

**Conventions (every task):** Backend tests via `./backend/venv/Scripts/python.exe -m pytest`; frontend from `frontend/`. Commit after each task; subagents only `git add`/`git commit`. The **VoxCPM/OmniVoice mode machinery is the template** — read `backend/voxcpm_worker.py`, `backend/core/engines/voxcpm_engine.py`, `backend/services/synthesize.py::_resolve_request_context`, `frontend/src/lib/voiceModes.ts`, `frontend/src/components/SpeakerRoster.tsx` when a task says "mirror".

---

## File Structure

**Modified (backend):** `qwen_worker.py` (3-way dispatch), `core/engines/qwen_engine.py` (capability flags + mode-dispatching `_build_synth_msg`), `core/engines/__init__.py` (remove `supports_style_prompt`), `services/synthesize.py` (engine-aware `custom` mode in `_resolve_request_context`), `api/schemas.py` + `api/engines.py` + `api/health.py` (remove `supports_style_prompt`), and the affected tests (`test_qwen_worker.py`, `test_qwen_engine.py`, `test_engines_capabilities.py`).
**Modified (frontend):** `lib/voiceModes.ts` (add `custom` mode + engine-aware `availableModes`/`effectiveMode`), `components/SpeakerRoster.tsx` + `components/TtsEditor.tsx` (engine-aware mode toggle + remove `supportsStylePrompt`), `App.tsx` (remove `supportsStylePrompt` derivation/props; `isSegmentCached` custom-mode signature), `types/models.ts` (remove `supports_style_prompt`; `Speaker.omnivoiceMode`/`TtsBuffer.omnivoiceMode` union gains `custom`).

---

## Task 1: Worker — 3-way mode dispatch (custom / clone / design)

**Files:** Modify `backend/qwen_worker.py`, `backend/tests/test_qwen_worker.py`.

The worker currently always calls `generate_custom_voice`. Add a `mode` field and dispatch. Speaker is normalized to the lowercase vocabulary; clone passes `ref_audio`/`ref_text`; design passes `instruct`.

- [ ] **Step 1: Failing tests** — replace the body of `test_qwen_worker.py`'s kwargs tests with mode-aware ones and add dispatch tests. Append these (keep the existing `_load_worker`, `_normalize_language`, WAV, and `_auto_max_new_tokens` tests that still hold):

```python
def test_custom_mode_lowercases_speaker():
    w = _load_worker()
    op, kw = w._build_call({"mode": "custom", "text": "hi", "speaker": "Vivian", "language": "English"})
    assert op == "custom"
    assert kw["speaker"] == "vivian"           # normalized to package vocab
    assert kw["language"] == "english"
    assert kw["text"] == "hi"


def test_custom_mode_requires_speaker():
    w = _load_worker()
    try:
        w._build_call({"mode": "custom", "text": "hi"})
    except ValueError:
        return
    raise AssertionError("expected ValueError when custom mode lacks a speaker")


def test_clone_mode_icl_when_ref_text_present():
    w = _load_worker()
    op, kw = w._build_call({"mode": "clone", "text": "hi", "ref_audio": "/tmp/r.wav", "ref_text": "hello there"})
    assert op == "clone"
    assert kw["ref_audio"] == "/tmp/r.wav"
    assert kw["ref_text"] == "hello there"
    assert kw["x_vector_only_mode"] is False   # ICL when transcript present


def test_clone_mode_xvector_when_no_ref_text():
    w = _load_worker()
    op, kw = w._build_call({"mode": "clone", "text": "hi", "ref_audio": "/tmp/r.wav"})
    assert op == "clone"
    assert kw["x_vector_only_mode"] is True
    assert "ref_text" not in kw


def test_clone_mode_requires_ref_audio():
    w = _load_worker()
    try:
        w._build_call({"mode": "clone", "text": "hi"})
    except ValueError:
        return
    raise AssertionError("expected ValueError when clone mode lacks ref_audio")


def test_design_mode_requires_instruct():
    w = _load_worker()
    op, kw = w._build_call({"mode": "design", "text": "hi", "instruct": "a calm elderly man"})
    assert op == "design"
    assert kw["instruct"] == "a calm elderly man"
    try:
        w._build_call({"mode": "design", "text": "hi", "instruct": "  "})
    except ValueError:
        return
    raise AssertionError("expected ValueError when design mode lacks instruct")


def test_quality_kwargs_forwarded_in_every_mode():
    w = _load_worker()
    for req in (
        {"mode": "custom", "text": "hi", "speaker": "Vivian"},
        {"mode": "clone", "text": "hi", "ref_audio": "/tmp/r.wav"},
        {"mode": "design", "text": "hi", "instruct": "x"},
    ):
        _op, kw = w._build_call({**req, "temperature": 0.8, "top_p": 0.9})
        assert kw["temperature"] == 0.8 and kw["top_p"] == 0.9
        assert kw["max_new_tokens"] > 0


def test_synth_dispatches_to_method(tmp_path):
    import numpy as np
    w = _load_worker()
    worker = w._Worker()

    class _FakeModel:
        def __init__(self):
            self.called = None
        def generate_custom_voice(self, **k):
            self.called = "custom"; return [np.zeros(24000, dtype=np.float32)], 24000
        def generate_voice_clone(self, **k):
            self.called = "clone"; return [np.zeros(24000, dtype=np.float32)], 24000
        def generate_voice_design(self, **k):
            self.called = "design"; return [np.zeros(24000, dtype=np.float32)], 24000

    worker._model = _FakeModel()
    out = tmp_path / "o.wav"
    resp = worker._synth({"mode": "design", "text": "hi", "instruct": "calm", "out_wav": str(out)})
    assert resp["ok"] is True and worker._model.called == "design"
    assert out.is_file() and out.stat().st_size > 0
```

Delete the now-obsolete `test_basic_kwargs`, `test_language_defaults_to_auto`, `test_instruct_passed_when_present`, `test_empty_instruct_omitted`, `test_quality_kwargs_passed_through_only_when_set`, `test_missing_speaker_raises`, and `test_synth_end_to_end_with_fake_model` (they assert the old single-method `_build_generate_kwargs`, which is replaced by `_build_call`). Keep `test_language_normalized_to_package_vocabulary` and `test_max_new_tokens_scales_with_text` (update the latter to call `_build_call({"mode":"custom","text":...,"speaker":"Vivian"})` and read `kw["max_new_tokens"]`).

- [ ] **Step 2: Run — verify fail** `./backend/venv/Scripts/python.exe -m pytest backend/tests/test_qwen_worker.py -v` → FAIL (`_build_call` undefined).

- [ ] **Step 3: Implement.** Replace `_build_generate_kwargs` with `_build_call` and update `_Worker._synth`. Keep `_normalize_language`, `_write_wav_int16`, `_auto_max_new_tokens`, `_norm_device`, `_log`, `_reply`, `main()` unchanged.

```python
def _common_kwargs(req: dict) -> dict:
    """Quality kwargs + max_new_tokens shared by every mode."""
    text = (req.get("text") or "").strip()
    if not text:
        raise ValueError("text must be non-empty")
    kw: dict = {"text": text, "language": _normalize_language(req.get("language"))}
    for key in ("temperature", "top_p", "top_k", "repetition_penalty"):
        if req.get(key) is not None:
            kw[key] = req[key]
    kw["max_new_tokens"] = _auto_max_new_tokens(text)
    return kw


def _build_call(req: dict) -> tuple[str, dict]:
    """Return (op, kwargs) for the requested mode. op is the method suffix:
    'custom' -> generate_custom_voice, 'clone' -> generate_voice_clone,
    'design' -> generate_voice_design. Defaults to custom (built-in voice)."""
    mode = (req.get("mode") or "custom").strip().lower()
    kw = _common_kwargs(req)
    if mode == "clone":
        ref_audio = req.get("ref_audio")
        if not ref_audio:
            raise ValueError("clone mode requires ref_audio")
        kw["ref_audio"] = ref_audio
        ref_text = (req.get("ref_text") or "").strip()
        if ref_text:
            kw["ref_text"] = ref_text
            kw["x_vector_only_mode"] = False   # ICL: condition on the transcript
        else:
            kw["x_vector_only_mode"] = True     # embedding-only clone
        return "clone", kw
    if mode == "design":
        instruct = (req.get("instruct") or "").strip()
        if not instruct:
            raise ValueError("design mode requires a non-empty instruct/style")
        kw["instruct"] = instruct
        return "design", kw
    # custom (default): one of the 9 built-in speakers + optional style
    speaker = req.get("speaker")
    if not speaker:
        raise ValueError("custom mode requires a speaker (one of the 9 Qwen voices)")
    kw["speaker"] = str(speaker).strip().lower()
    instruct = (req.get("instruct") or "").strip()
    if instruct:
        kw["instruct"] = instruct
    return "custom", kw
```

In `_Worker._synth`, replace the `kwargs = _build_generate_kwargs(req)` + `self._model.generate_custom_voice(**kwargs)` block with:

```python
        try:
            op, kwargs = _build_call(req)
        except ValueError as exc:
            return {"ok": False, "error": str(exc)}
        if req.get("seed") is not None:
            try:
                import torch
                torch.manual_seed(int(req["seed"]))
            except Exception:  # noqa: BLE001
                pass
        method = {
            "custom": "generate_custom_voice",
            "clone": "generate_voice_clone",
            "design": "generate_voice_design",
        }[op]
        t0 = time.perf_counter()
        try:
            wavs, sr = getattr(self._model, method)(**kwargs)
        except Exception as exc:  # noqa: BLE001
            return {"ok": False, "error": f"generate failed: {exc}"}
```

(Keep the existing numpy/WAV-writing + response tail below it.) Update the module docstring's protocol block to mention `"mode"`, `"ref_audio"`, `"ref_text"`.

- [ ] **Step 4: Run — verify pass** `./backend/venv/Scripts/python.exe -m pytest backend/tests/test_qwen_worker.py -v` → PASS.

- [ ] **Step 5: Commit**
```bash
git add backend/qwen_worker.py backend/tests/test_qwen_worker.py
git commit -m "feat(qwen): worker 3-way dispatch (custom/clone/design)"
```

---

## Task 2: Add `custom` mode to the shared mode system (frontend)

**Files:** Modify `frontend/src/lib/voiceModes.ts`, `frontend/src/types/models.ts`.

- [ ] **Step 1: Extend the `VoiceMode` union** (`voiceModes.ts:5`):
```typescript
export type VoiceMode = "clone" | "design" | "auto" | "custom";
```

- [ ] **Step 2: Add engine-aware mode helpers.** Replace `effectiveMode` (`voiceModes.ts:58-60`) with:
```typescript
/** The ordered modes a given engine exposes in the toggle. */
export function availableModes(engineName: string | null | undefined): VoiceMode[] {
  if (engineName === "qwen") return ["custom", "clone", "design"];
  return ["clone", "design", "auto"]; // OmniVoice / VoxCPM
}

/** Human label for a mode (engine-aware where it differs). */
export function modeLabel(mode: VoiceMode): string {
  if (mode === "custom") return "Custom voice";
  if (mode === "clone") return "Clone";
  if (mode === "design") return "Design";
  return "Auto";
}

/**
 * The speaker's effective voice mode. An explicit choice wins; otherwise:
 * Qwen defaults to `custom` (built-in voice), other engines to clone if a
 * reference voice is set else auto. Derived so switching engines never mutates
 * speaker state. Falls back to the engine's first available mode if the stored
 * choice isn't valid for this engine (e.g. a VoxCPM "auto" left on a Qwen speaker).
 */
export function effectiveMode(
  speaker: { voice: string; omnivoiceMode?: VoiceMode },
  engineName?: string | null,
): VoiceMode {
  const modes = availableModes(engineName);
  if (speaker.omnivoiceMode && modes.includes(speaker.omnivoiceMode)) return speaker.omnivoiceMode;
  if (engineName === "qwen") return "custom";
  return speaker.voice ? "clone" : "auto";
}
```
> Note: `effectiveMode` now takes an optional `engineName`. Existing callers that omit it keep the OmniVoice/VoxCPM behavior. Task 5/6 pass `activeEngine` at the call sites.

- [ ] **Step 3: Widen the stored-mode unions** in `types/models.ts`. `Speaker.omnivoiceMode` and `TtsBuffer.omnivoiceMode` are typed `"clone" | "design" | "auto"`; change BOTH to `"clone" | "design" | "auto" | "custom"`. Also widen `SynthSpeaker.voice_mode` the same way (it feeds the request body).

- [ ] **Step 4: Typecheck** (from `frontend/`): `npm run typecheck`. Existing `effectiveMode(speaker)` calls still compile (new arg optional). Expected: PASS.

- [ ] **Step 5: Commit**
```bash
git add frontend/src/lib/voiceModes.ts frontend/src/types/models.ts
git commit -m "feat(voice-modes): add Qwen 'custom' mode + engine-aware helpers"
```

---

## Task 3: QwenEngine — voice-mode capabilities + mode-dispatching `_build_synth_msg`

**Files:** Modify `backend/core/engines/qwen_engine.py`, `backend/tests/test_qwen_engine.py`.

- [ ] **Step 1: Failing tests** — replace `test_capabilities`, `test_build_msg_*` in `test_qwen_engine.py` with:
```python
def test_capabilities():
    e = _eng()
    assert e.name == "qwen"
    assert e.sample_rate() == 24000
    assert e.supports_voice_cloning() is True       # clone mode exists
    assert e.supports_voice_modes() is True
    assert e.supports_style_clone() is False         # clone has no style arg
    assert e.supports_streaming() is False
    assert e.default_cfg_scale() is None


def test_build_msg_custom_mode():
    msg = _eng()._build_synth_msg(
        EngineSynthRequest(text="hi", voice_id="Vivian", voice_mode="custom",
                           instruct="cheerful", language_id="English"), "/tmp/o.wav")
    assert msg["mode"] == "custom"
    assert msg["speaker"] == "Vivian"      # worker lowercases; engine passes through
    assert msg["instruct"] == "cheerful"
    assert msg["language"] == "English"
    assert "ref_audio" not in msg


def test_build_msg_custom_defaults_when_mode_absent():
    msg = _eng()._build_synth_msg(EngineSynthRequest(text="hi", voice_id="Aiden"), "/tmp/o.wav")
    assert msg["mode"] == "custom"
    assert msg["speaker"] == "Aiden"


def test_build_msg_clone_mode():
    msg = _eng()._build_synth_msg(
        EngineSynthRequest(text="hi", voice_mode="clone", reference_audio="/tmp/r.wav",
                           reference_text="hello"), "/tmp/o.wav")
    assert msg["mode"] == "clone"
    assert msg["ref_audio"] == "/tmp/r.wav"
    assert msg["ref_text"] == "hello"
    assert "speaker" not in msg


def test_build_msg_design_mode():
    msg = _eng()._build_synth_msg(
        EngineSynthRequest(text="hi", voice_mode="design", instruct="a calm man"), "/tmp/o.wav")
    assert msg["mode"] == "design"
    assert msg["instruct"] == "a calm man"
    assert "speaker" not in msg and "ref_audio" not in msg


def test_build_msg_custom_requires_speaker():
    try:
        _eng()._build_synth_msg(EngineSynthRequest(text="hi", voice_id="", voice_mode="custom"), "/tmp/o.wav")
    except ValueError:
        return
    raise AssertionError("expected ValueError: custom mode needs a speaker")
```
Keep `test_nine_builtin_voices` and `test_languages_include_auto_first` (the voice catalog + languages are unchanged).

- [ ] **Step 2: Run — verify fail** `./backend/venv/Scripts/python.exe -m pytest backend/tests/test_qwen_engine.py -v` → FAIL.

- [ ] **Step 3: Implement.** In `qwen_engine.py`:
  (a) Capability methods — change/replace:
```python
    def supports_voice_cloning(self) -> bool:
        return True

    def supports_voice_modes(self) -> bool:
        return True

    def supports_style_clone(self) -> bool:
        return False  # generate_voice_clone takes no instruct/style arg
```
  Delete the `supports_style_prompt` override (the always-on field is removed; Task 4 drops the ABC method).
  (b) Replace `_build_synth_msg` with mode dispatch:
```python
    def _build_synth_msg(self, req: EngineSynthRequest, out_wav: str) -> dict:
        text = (req.text or "").strip()
        if not text:
            raise ValueError("text must be non-empty")
        mode = (req.voice_mode or "custom").strip().lower()
        msg: dict[str, Any] = {
            "op": "synth",
            "mode": mode,
            "text": text,
            "out_wav": out_wav,
            "language": req.language_id or "Auto",
        }
        instruct = (req.instruct or "").strip()
        if mode == "clone":
            if not req.reference_audio:
                raise ValueError("Qwen clone mode requires a reference voice clip.")
            msg["ref_audio"] = req.reference_audio
            if req.reference_text:
                msg["ref_text"] = req.reference_text
        elif mode == "design":
            if not instruct:
                raise ValueError("Qwen design mode requires a style description.")
            msg["instruct"] = instruct
        else:  # custom
            if not req.voice_id:
                raise ValueError("Qwen custom mode requires a voice (one of the 9 speakers).")
            msg["speaker"] = req.voice_id
            if instruct:
                msg["instruct"] = instruct
        for attr in ("temperature", "top_p", "top_k", "repetition_penalty", "seed"):
            val = getattr(req, attr, None)
            if val is not None:
                msg[attr] = val
        return msg
```
  (c) Update the class docstring (no longer "built-in-voice engine only"; now 3 modes). Keep `available_voices()` / `languages()` / lifecycle internals unchanged.

- [ ] **Step 4: Run — verify pass** `./backend/venv/Scripts/python.exe -m pytest backend/tests/test_qwen_engine.py -v` → PASS.

- [ ] **Step 5: Commit**
```bash
git add backend/core/engines/qwen_engine.py backend/tests/test_qwen_engine.py
git commit -m "feat(qwen): voice-mode capabilities + custom/clone/design _build_synth_msg"
```

---

## Task 4: Remove the now-unused `supports_style_prompt` capability (backend)

**Files:** Modify `backend/core/engines/__init__.py`, `backend/api/schemas.py`, `backend/api/engines.py`, `backend/api/health.py`, `backend/tests/test_engines_capabilities.py`.

Qwen no longer sets it and no other engine ever did, so the flag is dead. Remove it everywhere it was added.

- [ ] **Step 1: Update the capabilities test** — in `test_engines_capabilities.py`, replace `test_engines_expose_style_prompt_flag` with one asserting Qwen now reports voice modes:
```python
def test_qwen_reports_voice_modes():
    from fastapi.testclient import TestClient
    from backend.app import create_app
    client = TestClient(create_app())
    by_name = {e["name"]: e for e in client.get("/api/engines").json()["engines"]}
    assert by_name["qwen"]["supports_voice_modes"] is True
    assert by_name["qwen"]["supports_voice_cloning"] is True
    assert by_name["qwen"]["supports_style_clone"] is False
    assert "supports_style_prompt" not in by_name["qwen"]   # flag removed
```

- [ ] **Step 2: Run — verify fail** `./backend/venv/Scripts/python.exe -m pytest backend/tests/test_engines_capabilities.py -k voice_modes -v` → FAIL (`supports_style_prompt` still present / qwen modes False).

- [ ] **Step 3: Remove the flag.** Delete these lines:
  - `core/engines/__init__.py`: the `def supports_style_prompt(self)` method AND the `"supports_style_prompt": self.supports_style_prompt(),` line in `info()`.
  - `api/schemas.py`: `supports_style_prompt: bool = False` from `EngineInfoModel`.
  - `api/engines.py`: `supports_style_prompt: bool = False` from its `EngineInfoModel` AND `supports_style_prompt=info.get(...)` from `_to_model`.
  - `api/health.py`: the `supports_style_prompt=info.get(...)` line in `/config`.

- [ ] **Step 4: Run — verify pass** `./backend/venv/Scripts/python.exe -m pytest backend/tests/test_engines_capabilities.py backend/tests/test_smoke.py -q` → PASS.

- [ ] **Step 5: Commit**
```bash
git add backend/core/engines/__init__.py backend/api/schemas.py backend/api/engines.py backend/api/health.py backend/tests/test_engines_capabilities.py
git commit -m "refactor(qwen): drop supports_style_prompt (subsumed by voice modes)"
```

---

## Task 5: SynthService — engine-aware `custom` mode resolution

**Files:** Modify `backend/services/synthesize.py`, `backend/tests/test_synthesize.py`.

`_resolve_request_context` currently derives `sp_mode = sp.voice_mode or ("clone" if sp.voice_id else "auto")` and resolves a reference WAV only when `sp_mode == "clone"`. For Qwen, a built-in voice in **custom** mode must NOT be resolved to a reference WAV (the voice_id is the speaker name). Make the default mode + resolution engine-aware.

- [ ] **Step 1: Failing test** — append to `test_synthesize.py` (uses the existing test harness/fixtures in that file; mirror an existing `_resolve_request_context` test's setup — read the file for the real fixture names):
```python
def test_qwen_custom_mode_does_not_resolve_reference(synth_service_qwen):
    # custom mode: voice_id is a built-in speaker, NOT a clone reference.
    svc = synth_service_qwen
    req = _qwen_req(voice_id="Vivian", voice_mode="custom")   # helper in this file
    _eng, name, ref_audio, *_ = svc._resolve_request_context(req)
    assert name == "qwen"
    assert ref_audio is None        # built-in speaker, no WAV resolved


def test_qwen_clone_mode_resolves_reference(synth_service_qwen):
    svc = synth_service_qwen
    req = _qwen_req(voice_id="my_upload", voice_mode="clone")
    _eng, _name, ref_audio, *_ = svc._resolve_request_context(req)
    assert ref_audio is not None    # clone resolves the upload to a WAV path
```
> If the test file has no existing `_resolve_request_context` fixture/helpers, instead write a smaller unit test that constructs `SynthService` the way other tests in the file do and asserts the same two facts. Read the file first and match its real patterns; report the exact helper names you used.

- [ ] **Step 2: Run — verify fail** `./backend/venv/Scripts/python.exe -m pytest backend/tests/test_synthesize.py -k qwen_custom -v` → FAIL (custom resolves a reference / errors).

- [ ] **Step 3: Implement.** In `_resolve_request_context`, change the per-speaker mode default + the resolve condition. Current logic (≈ lines 204-217):
```python
        supports_modes = target_engine.supports_voice_modes()
        ...
                sp_mode = sp.voice_mode or ("clone" if sp.voice_id else "auto")
            ...
            if sp_mode != "clone":
                ... skip reference ...
            else:
                reference_audio = str(self._voices.get(sp.voice_id))
```
Make the default engine-aware so Qwen defaults to `custom`, and only `clone` resolves a reference (already true). Replace the default-derivation line with:
```python
                default_mode = "custom" if target_name == "qwen" else ("clone" if sp.voice_id else "auto")
                sp_mode = sp.voice_mode or default_mode
```
The existing `if sp_mode != "clone": skip` already does the right thing for `custom` and `design` (no reference resolved); only `clone` resolves the WAV + transcript. Confirm `target_name` is in scope at that point (it is computed earlier in the method — verify; if not, derive it before this block).

- [ ] **Step 4: Run — verify pass** `./backend/venv/Scripts/python.exe -m pytest backend/tests/test_synthesize.py backend/tests/test_smoke.py -q` → PASS.

- [ ] **Step 5: Commit**
```bash
git add backend/services/synthesize.py backend/tests/test_synthesize.py
git commit -m "feat(qwen): custom mode skips reference resolution in SynthService"
```

---

## Task 6: SpeakerRoster + TtsEditor — engine-aware mode toggle, drop `supportsStylePrompt`

**Files:** Modify `frontend/src/components/SpeakerRoster.tsx`, `frontend/src/components/TtsEditor.tsx`.

Both render a mode toggle gated on `supportsVoiceModes` using hardcoded `["clone","design","auto"]`. Make the toggle use `availableModes(activeEngine)` + `modeLabel`, render the **Custom** mode body (voice picker + optional style), and remove the `supportsStylePrompt` branch added previously.

- [ ] **Step 1: SpeakerRoster.** Read the current `SpeakerRow` (modes section ≈ lines 154-260). Changes:
  - Import `availableModes`, `modeLabel` from `@/lib/voiceModes`; keep `effectiveMode`, `DESIGN_CHIPS`, `appendDesignChip`.
  - `const mode = effectiveMode(speaker, activeEngine);` (pass engine).
  - Replace the hardcoded mode-button list with `availableModes(activeEngine).map((m) => <button ... onClick={() => setMode(m)} ...>{modeLabel(m)}</button>)`.
  - Add a **custom** mode body (mirrors the existing `auto`/`design` bodies' styling): render the voice picker (`voiceSelect`) + an always-shown optional style input bound to `speaker.voiceDesign` (`onUpdate({ voiceDesign })`), placeholder `"Style (optional) — e.g. cheerful, slightly faster"`.
  - The existing `mode === "clone"` body stays (reference voice); since `supportsStyleClone` is false for Qwen, the clone style sub-field stays hidden for Qwen (correct — clone has no style). The `mode === "design"` body stays (free-text). The `mode === "auto"` body stays for OmniVoice/VoxCPM (Qwen never yields `auto`).
  - DELETE the `if (supportsStylePrompt) { ... }` early-return branch and the `supportsStylePrompt` prop from `Props`, the `SpeakerRow` params, and the inline prop-type object.

- [ ] **Step 2: TtsEditor.** Same treatment: mode toggle uses `availableModes(activeEngine)`/`modeLabel`; add the custom-mode style input (bound to `voiceDesign`/`onVoiceDesignChange`); show the active-voice "Voice: X" note in custom + clone modes; DELETE the `supportsStylePrompt` branch + prop.

- [ ] **Step 3: Typecheck** (from `frontend/`): `npm run typecheck`. App.tsx still passes `supportsStylePrompt` (removed in Task 7) — to keep THIS task green, leave the App.tsx prop pass-through until Task 7, OR make the removal in both this task and Task 7 atomic. PREFER: do Step 1-2 here, then immediately Task 7 (they share the typecheck gate). If typecheck is red only because App.tsx passes a now-removed prop, that's resolved in Task 7; run the combined typecheck at the end of Task 7. Report this sequencing.

- [ ] **Step 4: Commit**
```bash
git add frontend/src/components/SpeakerRoster.tsx frontend/src/components/TtsEditor.tsx
git commit -m "feat(qwen): engine-aware mode toggle + Custom mode body; drop style-prompt field"
```

---

## Task 7: App.tsx — remove `supportsStylePrompt`, custom-mode cache, engine-aware derivations

**Files:** Modify `frontend/src/App.tsx`.

- [ ] **Step 1: Remove `supportsStylePrompt`.** Delete `const supportsStylePrompt = activeEngineInfo?.supports_style_prompt ?? false;` and both `supportsStylePrompt={supportsStylePrompt}` props passed to `<SpeakerRoster>` / `<TtsEditor>`.

- [ ] **Step 2: `isSegmentCached` — fold Custom/Design style; resolve mode engine-awarely.** The non-voice-modes branch was extended (Task 16 of the prior plan) to fold `style` for `supportsStylePrompt`. Qwen is now a voice-modes engine, so it flows through the `supportsVoiceModes` branch instead. Two changes there:
  - Where the branch derives the mode, pass the engine: `const mode = effectiveMode(speaker, activeEngine);`.
  - Add a `mode === "custom"` arm (mirror the existing `clone` arm but compare the built-in voice + style): signature `${segment.text}::${voice}::custom::${style}::${effectiveQuality ?? ""}::${effectiveGenSig ?? ""}`, cached when `entry.text === segment.text && entry.voice === voice && (entry.instruct ?? "") === style && entry.quality === effectiveQuality && entry.genSig === effectiveGenSig`, where `style = (speaker.voiceDesign ?? "").trim()`.
  - REMOVE the `supportsStylePrompt`-gated `style` fold from the non-voice-modes (default) branch added previously (revert it to its pre-Qwen form: no `style`), since Qwen no longer uses that branch. Also remove the `supportsStylePrompt` parameter you added to `isSegmentCached` and at the 5 call sites.

- [ ] **Step 3: Cache writes — store the mode.** At both `cacheAudio` writes, Qwen now uses voice modes, so the existing `...(isOmni ? { mode } : {})` won't store the Qwen mode. Generalize the gate to `supportsVoiceModes` (so Qwen's custom/clone/design mode is persisted on the cache entry, matching the badge comparison): change `isOmni ? { mode }` → `supportsVoiceModes ? { mode }` at both writes. Confirm `mode`/`instruct` are computed for Qwen in the synth path (the `instruct` block already covers `mode === "design" || mode === "clone"`; ADD `|| mode === "custom"` so a Custom-mode style is sent + cached).

- [ ] **Step 4: Generate path — compute Qwen mode + instruct.** Where `mode`/`instruct` are computed before `synthesizeWav` (≈ lines 285-304), the current `const mode = isOmni ? effectiveMode(speaker) : "clone";` forces non-omni engines to `clone`. Change to be modes-aware: `const mode = supportsVoiceModes ? effectiveMode(speaker, activeEngine) : "clone";`. Ensure the `clone && !speaker.voice` guard only triggers for `mode === "clone"` (it already checks `mode === "clone"`). For `mode === "custom"`, `speaker.voice` is the built-in speaker name and flows as the request voice (it already does via `voice: speaker.voice`).

- [ ] **Step 5: Typecheck + the combined Task-6 gate** (from `frontend/`): `npm run typecheck` → PASS (this resolves the Task-6 cross-file prop removal).

- [ ] **Step 6: Commit**
```bash
git add frontend/src/App.tsx
git commit -m "feat(qwen): wire 3 modes through generate + cache; remove style-prompt"
```

---

## Task 8: Full suites + build gate

- [ ] **Step 1:** `./backend/venv/Scripts/python.exe -m pytest backend/tests/ -q` → 0 failures. Fix any leftover test asserting `supports_style_prompt` or the old Qwen single-method behavior.
- [ ] **Step 2:** From `frontend/`: `npm run typecheck` && `npm test` && `npm run build` → all clean. Update any mock/test referencing `supports_style_prompt` or the removed prop.
- [ ] **Step 3:** Commit any fixes: `git commit -am "test(qwen): update suites for voice-mode redesign"`.

---

## Task 9: Docs — update CLAUDE.md

**Files:** Modify `CLAUDE.md`.

- [ ] **Step 1:** In the isolated-engines paragraph, replace the Qwen description (currently "built-in-voice engine … `supports_style_prompt` always-available style field") with: Qwen is a **voice-modes** engine (`supports_voice_modes`) with three modes — **Custom** (9 built-in speakers + optional style via `generate_custom_voice`), **Clone** (reference clip; ICL with the voice's `reference_transcript` else x-vector-only, via `generate_voice_clone`), and **Design** (free-text style via `generate_voice_design`). It adds the shared `"custom"` mode to `voiceModes.ts` (`availableModes`/`modeLabel` are engine-aware; `effectiveMode` defaults Qwen to `custom`). `supports_style_clone=false` (clone takes no style); the prior `supports_style_prompt` flag is removed. The Advanced generation panel (temperature/top_p/top_k/repetition_penalty/seed) and language normalization (`_normalize_language`) apply across all three modes.
- [ ] **Step 2: Commit**
```bash
git add CLAUDE.md
git commit -m "docs: Qwen voice modes (custom/clone/design) in CLAUDE.md"
```

---

## Task 10: Final holistic review + manual verification

- [ ] **Step 1:** Full suites green (backend `pytest`, frontend `npm test` + `npm run build`).
- [ ] **Step 2:** Dispatch a holistic reviewer over `git diff` of these tasks, focused on: the mode flows end-to-end (toggle → `omnivoiceMode`/`voice_mode` → `SynthSpeaker` → `SynthRequest` → `_resolve_request_context` default + reference resolution → `EngineSynthRequest.voice_mode` → `qwen_engine._build_synth_msg` → worker `_build_call` → the correct `generate_*` method); that Custom mode never resolves a reference WAV while Clone always does; that the cache badge folds mode + style + reference for all three Qwen modes (no stale audio when switching mode/style); that `supports_style_prompt` is fully removed (no dangling refs in backend, frontend, tests); and that OmniVoice/VoxCPM mode behavior is unchanged (regression). Address findings.
- [ ] **Step 3 (manual, GPU):** Switch to Qwen → **Custom** (pick each of 9 voices, add a style) → **Clone** (upload a reference; with + without a saved transcript → ICL vs x-vector) → **Design** (free-text). Confirm audio in each mode, that changing mode/voice/style re-synthesizes (no stale cache), and that export honors the active mode. Confirm `get_supported_speakers()` matches the 9 lowercased names.
- [ ] **Step 4:** Hand off to `superpowers:finishing-a-development-branch` (push to the existing PR branch `feat/qwen-tts-engine`).

---

## Self-review notes (author)

- **Spec coverage:** 3 real methods → worker dispatch (T1) + engine `_build_synth_msg` (T3); `custom` mode added to shared system (T2); engine-aware reference resolution so Custom doesn't clone (T5); UI mode toggle + Custom body (T6); generate + cache wiring (T7); `supports_style_prompt` removed (T4, T7); ICL-vs-x-vector auto from `reference_transcript` (T1 clone, T3 passes `ref_text`); speaker lowercasing (T1); docs (T9); holistic + manual (T10).
- **Type consistency:** `VoiceMode` gains `"custom"` (T2) and is used consistently in `effectiveMode`/`availableModes` (FE), `Speaker.omnivoiceMode`/`SynthSpeaker.voice_mode` (FE types), `EngineSynthRequest.voice_mode` (BE, already `str|None`), worker `mode` string (BE). Worker op strings `custom`/`clone`/`design` ↔ engine `msg["mode"]` ↔ method map are identical.
- **Risks:** `_resolve_request_context` must have `target_name` in scope at the default-mode line (T5 verifies). The clone ICL path depends on a real `reference_transcript`; without one it cleanly degrades to x-vector. Manual GPU pass (T10) confirms the live `generate_voice_clone`/`generate_voice_design` signatures match (already introspected, but unverified end-to-end with weights).
