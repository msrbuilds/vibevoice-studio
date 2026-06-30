# VoxCPM2 Engine Integration — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add `openbmb/VoxCPM2` as a fifth TTS engine — an isolated-venv worker proxy exposing all five generation modes (auto/design/clone/controllable/ultimate), a CFG + quality control, and a per-voice reference transcript — with the full install/download/delete/uninstall lifecycle.

**Architecture:** A `VoxCPMEngine` proxy (mirroring `OmniVoiceEngine`) drives `backend/voxcpm_worker.py` inside `backend/venv-voxcpm` over newline-delimited JSON; audio passes as temp WAVs. Voice modes are generalized off OmniVoice's hardcode via two engine capability flags. The only schema change is an optional per-voice `reference_transcript`.

**Tech Stack:** Python 3.10–3.12 (isolated venv), FastAPI, `voxcpm` ≥2.0.3 (torch ≥2.5/CUDA ≥12), React + TypeScript + Vite + Tailwind. Backend tests: pytest via `backend/venv/Scripts/python.exe -m pytest`. Frontend tests: Vitest.

**Spec:** `docs/superpowers/specs/2026-06-30-voxcpm-engine-design.md`

**Conventions for every task:**
- Run backend tests with the venv Python: `./backend/venv/Scripts/python.exe -m pytest backend/tests/<file> -v` (the system Python has no pytest).
- Run frontend checks from `frontend/`: `npm run typecheck` and `npm test`.
- Commit after each task. Subagents only `git add` / `git commit` — never checkout/switch/reset/merge/push.

---

## File Structure

**New (backend):**
- `backend/voxcpm_worker.py` — runs in `venv-voxcpm`; JSON `load`/`synth`/`shutdown`; composes the inline `(style)` prefix and dispatches the five modes onto `voxcpm.VoxCPM.generate(...)`.
- `backend/core/engines/voxcpm_engine.py` — `VoxCPMEngine` proxy (copy of `OmniVoiceEngine`); builds the synth message, owns worker lifecycle.
- `backend/requirements-voxcpm.txt` — single line `voxcpm`.
- `backend/tests/test_voxcpm_worker.py`, `backend/tests/test_voxcpm_engine.py`.

**New (frontend):**
- `frontend/src/lib/voiceModes.ts` — renamed/generalized from `lib/omnivoice.ts` (kept `effectiveMode`, `OmniMode`→`VoiceMode`, design chips; OmniVoice-specific data stays tagged).

**Modified (backend):** `core/engines/__init__.py` (request field + capability methods + `info()`), `core/engine_manager.py` (register engine + ctor args), `config.py` (settings + Literal), `app.py` (ctor args + installers/uninstallers), `services/voices.py` (transcript field + persistence + resolver), `services/synthesize.py` (resolve transcript, generalize voice-modes, cache key), `api/schemas.py` + `api/engines.py` (capability flags, transcript field, EngineInfoModel), `scripts/download_models.py` (catalog), `services/model_download.py` (DOWNLOADABLE), `services/model_delete.py` (DELETABLE), `services/engine_uninstall.py` (UNINSTALLABLE), `studio.py` (install-voxcpm), `tools/envdetect.py` (cuda tag), `tests/test_setup_helpers.py`, `tests/test_synthesize.py`.

**Modified (frontend):** `types/models.ts`, `lib/engineHints.ts`, `lib/api.ts`, `components/SpeakerRoster.tsx`, `components/ControlPanel.tsx`, `components/VoiceLibrary.tsx`, `components/EngineSelector.tsx`, `components/DownloadModelDialog.tsx`, `components/DeleteWeightsDialog.tsx`, `App.tsx`, and every `@/lib/omnivoice` import site.

---

## Task 1: VoxCPM worker — mode dispatch (`voxcpm_worker.py`)

**Files:**
- Create: `backend/voxcpm_worker.py`
- Create: `backend/tests/test_voxcpm_worker.py`
- Create: `backend/requirements-voxcpm.txt`

The worker is pure-Python and testable with a fake `voxcpm` module injected into `sys.modules`. Its `_build_generate_kwargs` is the spec's mode dispatch table.

- [ ] **Step 1: Write `requirements-voxcpm.txt`**

```text
voxcpm
# torch + torchaudio are installed separately by studio.py with a CUDA-matched
# wheel (see _ensure_voxcpm_env). Do NOT pin torch here.
```

- [ ] **Step 2: Write the failing test** `backend/tests/test_voxcpm_worker.py`

```python
"""Tests for the VoxCPM worker's mode dispatch, using a fake voxcpm model."""

import importlib
import sys
import types
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT))


def _load_worker():
    # Import the worker module fresh (it imports voxcpm lazily inside _load, so
    # importing the module itself needs no fake).
    import backend.voxcpm_worker as w
    return importlib.reload(w)


def test_auto_mode_passes_plain_text():
    w = _load_worker()
    kwargs, mode = w._build_generate_kwargs(
        {"text": "hello", "mode": "auto", "cfg_value": 2.0, "inference_timesteps": 10}
    )
    assert mode == "auto"
    assert kwargs["text"] == "hello"
    assert "reference_wav_path" not in kwargs
    assert kwargs["cfg_value"] == 2.0
    assert kwargs["inference_timesteps"] == 10


def test_design_mode_prefixes_style():
    w = _load_worker()
    kwargs, mode = w._build_generate_kwargs(
        {"text": "hi", "mode": "design", "instruct": "a young woman, gentle"}
    )
    assert mode == "design"
    assert kwargs["text"] == "(a young woman, gentle)hi"
    assert "reference_wav_path" not in kwargs


def test_design_without_style_downgrades_to_auto():
    w = _load_worker()
    kwargs, mode = w._build_generate_kwargs({"text": "hi", "mode": "design", "instruct": ""})
    assert mode == "auto"
    assert kwargs["text"] == "hi"


def test_clone_mode_sets_reference():
    w = _load_worker()
    kwargs, mode = w._build_generate_kwargs(
        {"text": "hi", "mode": "clone", "ref_audio": "/tmp/v.wav"}
    )
    assert mode == "clone"
    assert kwargs["reference_wav_path"] == "/tmp/v.wav"
    assert kwargs["text"] == "hi"
    assert "prompt_text" not in kwargs


def test_controllable_clone_prefixes_style_with_reference():
    w = _load_worker()
    kwargs, mode = w._build_generate_kwargs(
        {"text": "hi", "mode": "clone", "ref_audio": "/tmp/v.wav", "instruct": "cheerful"}
    )
    assert kwargs["reference_wav_path"] == "/tmp/v.wav"
    assert kwargs["text"] == "(cheerful)hi"


def test_ultimate_clone_sets_prompt_wav_and_text():
    w = _load_worker()
    kwargs, mode = w._build_generate_kwargs(
        {"text": "hi", "mode": "clone", "ref_audio": "/tmp/v.wav", "prompt_text": "a transcript"}
    )
    assert kwargs["reference_wav_path"] == "/tmp/v.wav"
    assert kwargs["prompt_wav_path"] == "/tmp/v.wav"
    assert kwargs["prompt_text"] == "a transcript"


def test_clone_mode_requires_ref():
    w = _load_worker()
    try:
        w._build_generate_kwargs({"text": "hi", "mode": "clone"})
    except ValueError:
        return
    raise AssertionError("expected ValueError when clone mode lacks ref_audio")


def test_synth_end_to_end_with_fake_model(tmp_path):
    """_Worker._synth calls the fake model and writes a 48k WAV."""
    import numpy as np

    w = _load_worker()
    worker = w._Worker()

    class _FakeModel:
        class tts_model:
            sample_rate = 48000

        def generate(self, **kwargs):
            return np.zeros(48000, dtype=np.float32)  # 1 second of silence

    worker._model = _FakeModel()
    out = tmp_path / "out.wav"
    resp = worker._synth({"text": "hi", "mode": "auto", "out_wav": str(out)})
    assert resp["ok"] is True
    assert resp["sample_rate"] == 48000
    assert abs(resp["duration_sec"] - 1.0) < 0.01
    assert out.is_file() and out.stat().st_size > 0
```

- [ ] **Step 3: Run the test to verify it fails**

Run: `./backend/venv/Scripts/python.exe -m pytest backend/tests/test_voxcpm_worker.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'backend.voxcpm_worker'`.

- [ ] **Step 4: Write `backend/voxcpm_worker.py`**

```python
#!/usr/bin/env python3
"""VoxCPM worker — runs INSIDE backend/venv-voxcpm.

Speaks newline-delimited JSON on stdin/stdout. The parent process
(backend/core/engines/voxcpm_engine.py) drives it. All human-readable
logging goes to STDERR so it never corrupts the stdout protocol.

Protocol (one JSON object per line):
  stdin  {"op":"load","device":"cuda","model_id":"openbmb/VoxCPM2"}
         {"op":"synth","mode":"clone|design|auto","text":..,"out_wav":<path>,
          "ref_audio":<path?>,"prompt_text":<str?>,"instruct":<str?>,
          "cfg_value":<float?>,"inference_timesteps":<int?>}
         {"op":"shutdown"}
  stdout {"ok":true}                                            (load)
         {"ok":true,"sample_rate":48000,"duration_sec":..,"inference_ms":..}  (synth)
         {"ok":false,"error":".."}                             (any failure)

VoxCPM expresses voice DESIGN and STYLE STEERING inline as a "(...)" prefix in
the text (NOT a separate argument), so this worker composes the prefixed text.
The generated audio is written to out_wav (16-bit PCM mono WAV at 48 kHz); only
metadata travels over the pipe.
"""

from __future__ import annotations

import json
import os
import sys
import time
import wave

# Protocol output. main() replaces this with the REAL stdout and points fd 1
# (Python AND C-level) at stderr, so model-load/tqdm noise can't corrupt the
# newline-delimited JSON the parent reads.
_OUT = sys.stdout

_DEFAULT_SAMPLE_RATE = 48000


def _log(msg: str) -> None:
    print(msg, file=sys.stderr, flush=True)


def _reply(obj: dict) -> None:
    _OUT.write(json.dumps(obj) + "\n")
    _OUT.flush()


def _write_wav_int16(path: str, samples, sample_rate: int) -> None:
    """Write a mono 16-bit PCM WAV from a float or int16 numpy array."""
    import numpy as np

    arr = np.asarray(samples)
    if arr.ndim > 1:
        arr = arr.reshape(-1)
    if arr.dtype != np.int16:
        arr = np.clip(arr, -1.0, 1.0)
        arr = (arr * 32767.0).astype(np.int16)
    with wave.open(path, "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(int(sample_rate))
        w.writeframes(arr.tobytes())


def _norm_device(device: str | None) -> str:
    d = (device or "cuda").lower()
    if d == "auto":
        d = "cuda"
    return d  # cuda, cpu, mps


def _build_generate_kwargs(req: dict) -> tuple[dict, str]:
    """Translate a synth request into voxcpm.generate(**kwargs).

    Dispatch table (mode, has_ref, has_style, has_transcript):
      auto              -> generate(text)
      design            -> generate("(style)text")
      clone             -> generate(text, reference_wav_path=ref)
      controllable      -> generate("(style)text", reference_wav_path=ref)
      ultimate          -> generate(text, prompt_wav_path=ref, prompt_text=tr,
                                    reference_wav_path=ref)
    An empty design style downgrades to auto.
    """
    text = (req.get("text") or "").strip()
    mode = req.get("mode") or "auto"
    style = (req.get("instruct") or "").strip()
    ref = req.get("ref_audio")
    transcript = (req.get("prompt_text") or "").strip()

    if mode == "design" and not style:
        mode = "auto"

    # Inline "(style)" prefix for design + controllable-clone only.
    prefixed = f"({style}){text}" if style and mode in ("design", "clone") else text
    kwargs: dict = {"text": prefixed}

    if req.get("cfg_value") is not None:
        kwargs["cfg_value"] = float(req["cfg_value"])
    if req.get("inference_timesteps") is not None:
        kwargs["inference_timesteps"] = int(req["inference_timesteps"])

    if mode == "clone":
        if not ref:
            raise ValueError("clone mode requires ref_audio")
        kwargs["reference_wav_path"] = ref
        if transcript:
            # Ultimate cloning: continuation guided by the reference transcript.
            kwargs["prompt_wav_path"] = ref
            kwargs["prompt_text"] = transcript
    return kwargs, mode


class _Worker:
    def __init__(self) -> None:
        self._model = None
        self._sample_rate = _DEFAULT_SAMPLE_RATE

    def handle(self, req: dict) -> dict:
        op = req.get("op")
        if op == "load":
            return self._load(req)
        if op == "synth":
            return self._synth(req)
        if op == "shutdown":
            return {"ok": True}
        return {"ok": False, "error": f"unknown op: {op!r}"}

    def _load(self, req: dict) -> dict:
        device = _norm_device(req.get("device"))
        model_id = req.get("model_id") or "openbmb/VoxCPM2"
        try:
            from voxcpm import VoxCPM
        except Exception as exc:  # noqa: BLE001
            return {"ok": False, "error": f"import voxcpm failed: {exc}"}
        try:
            self._model = VoxCPM.from_pretrained(model_id, load_denoiser=False)
        except Exception as exc:  # noqa: BLE001
            return {"ok": False, "error": f"load failed: {exc}"}
        # Read the model's real output sample rate if exposed; else keep 48k.
        try:
            sr = int(self._model.tts_model.sample_rate)
            if sr > 0:
                self._sample_rate = sr
        except Exception:  # noqa: BLE001
            pass
        _log(f"[voxcpm-worker] model loaded on {device}, sr={self._sample_rate}")
        return {"ok": True}

    def _synth(self, req: dict) -> dict:
        if self._model is None:
            return {"ok": False, "error": "model not loaded"}
        text = (req.get("text") or "").strip()
        out_wav = req.get("out_wav")
        if not text:
            return {"ok": False, "error": "text must be non-empty"}
        if not out_wav:
            return {"ok": False, "error": "out_wav required"}
        try:
            kwargs, _mode = _build_generate_kwargs(req)
        except ValueError as exc:
            return {"ok": False, "error": str(exc)}
        t0 = time.perf_counter()
        try:
            audio = self._model.generate(**kwargs)
        except Exception as exc:  # noqa: BLE001
            return {"ok": False, "error": f"generate failed: {exc}"}
        inference_ms = int((time.perf_counter() - t0) * 1000)

        import numpy as np

        arr = audio[0] if isinstance(audio, (list, tuple)) else audio
        if hasattr(arr, "detach"):
            arr = arr.detach().cpu().float().numpy()
        arr = np.asarray(arr, dtype=np.float32).reshape(-1)
        try:
            _write_wav_int16(out_wav, arr, self._sample_rate)
        except Exception as exc:  # noqa: BLE001
            return {"ok": False, "error": f"write wav failed: {exc}"}
        return {
            "ok": True,
            "sample_rate": self._sample_rate,
            "duration_sec": float(arr.size) / float(self._sample_rate),
            "inference_ms": inference_ms,
        }


def main() -> int:
    global _OUT
    _OUT = os.fdopen(os.dup(1), "w", encoding="utf-8", buffering=1)
    try:
        os.dup2(2, 1)
    except OSError:
        pass
    sys.stdout = sys.stderr

    worker = _Worker()
    for line in sys.stdin:
        line = line.strip()
        if not line:
            continue
        try:
            req = json.loads(line)
        except json.JSONDecodeError as exc:
            _reply({"ok": False, "error": f"bad json: {exc}"})
            continue
        try:
            resp = worker.handle(req)
        except Exception as exc:  # noqa: BLE001
            resp = {"ok": False, "error": f"worker exception: {exc}"}
        _reply(resp)
        if req.get("op") == "shutdown":
            break
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
```

- [ ] **Step 5: Run the test to verify it passes**

Run: `./backend/venv/Scripts/python.exe -m pytest backend/tests/test_voxcpm_worker.py -v`
Expected: PASS (8 tests).

> **Implementation note (verify the real API):** when `backend/venv-voxcpm` exists, confirm the live `generate()` signature before trusting the dispatch:
> `./backend/venv-voxcpm/Scripts/python.exe -c "import inspect, voxcpm; print(inspect.signature(voxcpm.VoxCPM.generate))"`.
> If the parameter names differ (e.g. `reference_wav_path`/`prompt_wav_path`/`prompt_text`/`cfg_value`/`inference_timesteps`), update `_build_generate_kwargs` and its tests to match, then re-run. This is the spec's Risk #1.

- [ ] **Step 6: Commit**

```bash
git add backend/voxcpm_worker.py backend/tests/test_voxcpm_worker.py backend/requirements-voxcpm.txt
git commit -m "feat(voxcpm): worker with five-mode generate dispatch"
```

---

## Task 2: Engine request field + capability methods

**Files:**
- Modify: `backend/core/engines/__init__.py`

Add the `reference_text` request field (carries the per-voice transcript) and two default capability methods used to generalize the voice-mode UI/flow off OmniVoice's hardcode.

- [ ] **Step 1: Add `reference_text` to `EngineSynthRequest`**

In `backend/core/engines/__init__.py`, after the `instruct: str | None = None` field (currently line 81), add:

```python
    # --- VoxCPM only (other engines ignore) ---
    # Transcript of the reference clip, enabling VoxCPM "ultimate cloning"
    # (prompt_wav + prompt_text). Resolved per-voice by SynthService.
    reference_text: str | None = None
```

- [ ] **Step 2: Add default capability methods to `Engine`**

In the `Engine` ABC, after `downloaded()` (currently ends line 140), add:

```python
    def supports_voice_modes(self) -> bool:
        """True if the engine offers per-speaker Clone/Design/Auto modes
        (an empty voice means "design" or "auto", not an error). OmniVoice
        and VoxCPM override this; every other engine is always voice-based."""
        return False

    def supports_style_clone(self) -> bool:
        """True if the engine accepts an inline style prompt WHILE cloning a
        reference voice (VoxCPM "controllable cloning"). OmniVoice's design
        prompt only applies without a reference, so it leaves this False."""
        return False
```

- [ ] **Step 3: Surface the flags in `Engine.info()`**

In `Engine.info()`, add two keys to the returned dict (after `"languages": self.languages(),`):

```python
            "supports_voice_modes": self.supports_voice_modes(),
            "supports_style_clone": self.supports_style_clone(),
```

- [ ] **Step 4: Verify nothing broke**

Run: `./backend/venv/Scripts/python.exe -m pytest backend/tests/test_smoke.py -v`
Expected: PASS (no behavior change; new fields default safely).

- [ ] **Step 5: Commit**

```bash
git add backend/core/engines/__init__.py
git commit -m "feat(engines): reference_text request field + voice-mode capability flags"
```

---

## Task 3: VoxCPMEngine proxy (`voxcpm_engine.py`)

**Files:**
- Create: `backend/core/engines/voxcpm_engine.py`
- Create: `backend/tests/test_voxcpm_engine.py`

- [ ] **Step 1: Write the failing test** `backend/tests/test_voxcpm_engine.py`

```python
"""VoxCPMEngine proxy tests: message building + capability flags.

The proxy's _build_synth_msg is pure logic (no subprocess), so we test the
five-mode → worker-message mapping directly.
"""

import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT))

from backend.core.engines import EngineSynthRequest  # noqa: E402
from backend.core.engines.voxcpm_engine import VoxCPMEngine  # noqa: E402


def _eng():
    return VoxCPMEngine(inference_timesteps=10)


def test_capabilities():
    e = _eng()
    assert e.name == "voxcpm"
    assert e.sample_rate() == 48000
    assert e.max_speakers() == 1
    assert e.supports_voice_cloning() is True
    assert e.supports_voice_modes() is True
    assert e.supports_style_clone() is True
    assert e.supports_streaming() is False


def test_auto_message():
    msg = _eng()._build_synth_msg(
        EngineSynthRequest(text="hi", voice_id="", voice_mode="auto"), "/tmp/o.wav"
    )
    assert msg["mode"] == "auto"
    assert msg["text"] == "hi"
    assert "ref_audio" not in msg
    assert msg["inference_timesteps"] == 10


def test_design_message_carries_instruct():
    msg = _eng()._build_synth_msg(
        EngineSynthRequest(text="hi", voice_id="", voice_mode="design", instruct="warm"),
        "/tmp/o.wav",
    )
    assert msg["mode"] == "design"
    assert msg["instruct"] == "warm"
    assert "ref_audio" not in msg


def test_clone_message():
    msg = _eng()._build_synth_msg(
        EngineSynthRequest(text="hi", voice_id="v", voice_mode="clone", reference_audio="/tmp/v.wav"),
        "/tmp/o.wav",
    )
    assert msg["mode"] == "clone"
    assert msg["ref_audio"] == "/tmp/v.wav"
    assert "prompt_text" not in msg


def test_controllable_clone_carries_style():
    msg = _eng()._build_synth_msg(
        EngineSynthRequest(
            text="hi", voice_id="v", voice_mode="clone",
            reference_audio="/tmp/v.wav", instruct="cheerful",
        ),
        "/tmp/o.wav",
    )
    assert msg["ref_audio"] == "/tmp/v.wav"
    assert msg["instruct"] == "cheerful"


def test_ultimate_clone_carries_transcript():
    msg = _eng()._build_synth_msg(
        EngineSynthRequest(
            text="hi", voice_id="v", voice_mode="clone",
            reference_audio="/tmp/v.wav", reference_text="a transcript",
        ),
        "/tmp/o.wav",
    )
    assert msg["ref_audio"] == "/tmp/v.wav"
    assert msg["prompt_text"] == "a transcript"


def test_clone_without_ref_raises():
    try:
        _eng()._build_synth_msg(
            EngineSynthRequest(text="hi", voice_id="", voice_mode="clone"), "/tmp/o.wav"
        )
    except ValueError:
        return
    raise AssertionError("expected ValueError for clone with no reference")


def test_cfg_value_passed_through():
    msg = _eng()._build_synth_msg(
        EngineSynthRequest(text="hi", voice_id="", voice_mode="auto", cfg_scale=2.5),
        "/tmp/o.wav",
    )
    assert msg["cfg_value"] == 2.5
```

- [ ] **Step 2: Run the test to verify it fails**

Run: `./backend/venv/Scripts/python.exe -m pytest backend/tests/test_voxcpm_engine.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'backend.core.engines.voxcpm_engine'`.

- [ ] **Step 3: Write `backend/core/engines/voxcpm_engine.py`**

```python
"""VoxCPM2 engine — ISOLATED-ENV PROXY.

VoxCPM needs torch>=2.5 / CUDA>=12 plus a heavy dependency tail (funasr,
modelscope, datasets, gradio), so the model never runs in this process: this
class is a thin proxy that drives `backend/voxcpm_worker.py` inside a separate
venv (`backend/venv-voxcpm`). It keeps the exact same Engine surface, so
EngineManager and SynthService are unchanged.

Communication is newline-delimited JSON over the worker's stdin/stdout; the
generated audio is written by the worker to a temp WAV this process reads.

Five modes are derived from the request: auto / design (inline style, no ref) /
clone / controllable clone (clone + style) / ultimate clone (clone + transcript).
The worker composes the inline "(style)" prefix; this proxy only forwards the
raw text + mode + instruct + prompt_text.
"""

from __future__ import annotations

import collections
import json
import logging
import os
import subprocess
import tempfile
import threading
from pathlib import Path
from typing import Any

from . import Engine, EngineResult, EngineSynthRequest

log = logging.getLogger(__name__)

_BACKEND_ROOT = Path(__file__).resolve().parents[2]  # backend/


def _default_worker_python() -> Path:
    venv = _BACKEND_ROOT / "venv-voxcpm"
    if os.name == "nt":
        return venv / "Scripts" / "python.exe"
    return venv / "bin" / "python"


def _default_worker_script() -> Path:
    return _BACKEND_ROOT / "voxcpm_worker.py"


class VoxCPMEngine(Engine):
    """Proxy to a VoxCPM worker running in backend/venv-voxcpm."""

    name = "voxcpm"
    display_name = "VoxCPM2"
    description = (
        "OpenBMB's 2B tokenizer-free multilingual TTS (30 languages, 48 kHz). "
        "Voice design, cloning, controllable + transcript-guided cloning. Runs "
        "in its own isolated environment. ~5 GB weights download on first use."
    )

    def __init__(
        self,
        model_id: str = "openbmb/VoxCPM2",
        device_request: str = "cuda",
        inference_timesteps: int = 10,
        worker_python: Path | None = None,
        worker_script: Path | None = None,
    ) -> None:
        self._model_id = model_id
        self._device_request = device_request
        self._inference_timesteps = inference_timesteps
        self._worker_python = Path(worker_python) if worker_python else _default_worker_python()
        self._worker_script = Path(worker_script) if worker_script else _default_worker_script()
        self._proc: subprocess.Popen | None = None
        self._lock = threading.Lock()
        self._load_lock = threading.Lock()
        self._stderr_tail: collections.deque[str] = collections.deque(maxlen=200)
        self._stderr_thread: threading.Thread | None = None

    # -- lifecycle
    def load(self) -> None:
        with self._load_lock:
            if self.is_loaded():
                return
            if not self._worker_python.is_file():
                raise RuntimeError(
                    "VoxCPM isn't installed in its isolated environment. "
                    "Run `python studio.py install-voxcpm` (or click Install in the UI)."
                )
            device = self._device_request
            if device == "auto":
                device = "cuda"
            env = dict(os.environ)
            models_dir = _BACKEND_ROOT / "models"
            env["HF_HOME"] = str(models_dir)
            env["HUGGINGFACE_HUB_CACHE"] = str(models_dir / "hub")
            log.info("Spawning VoxCPM worker: %s %s", self._worker_python, self._worker_script)
            self._proc = subprocess.Popen(
                [str(self._worker_python), str(self._worker_script)],
                stdin=subprocess.PIPE,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                env=env,
            )
            self._start_stderr_drain()
            resp = self._exchange({"op": "load", "device": device, "model_id": self._model_id})
            if not resp.get("ok"):
                err = resp.get("error", "unknown error")
                self._kill()
                raise RuntimeError(f"VoxCPM worker failed to load: {err}")

    def unload(self) -> None:
        if self._proc is None:
            return
        try:
            if self._proc.poll() is None:
                self._exchange({"op": "shutdown"}, expect_reply=False)
        except Exception:  # noqa: BLE001
            pass
        self._kill()

    def is_loaded(self) -> bool:
        return self._proc is not None and self._proc.poll() is None

    def installed(self) -> bool:
        return self._ready_marker().is_file()

    def _ready_marker(self) -> Path:
        # backend/venv-voxcpm/.voxcpm-ready
        return self._worker_python.parent.parent / ".voxcpm-ready"

    def downloaded(self) -> bool:
        from ..model_cache import model_downloaded

        return model_downloaded(self._model_id)

    def engine_info(self) -> dict[str, Any]:
        device = self._device_request
        if device == "auto":
            device = "cuda"
        return {
            "model_id": self._model_id,
            "device": device,
            "dtype": "bfloat16",
            "attn_implementation": "sdpa",
        }

    # -- capabilities
    def sample_rate(self) -> int:
        return 48000

    def max_speakers(self) -> int:
        return 1

    def supports_voice_cloning(self) -> bool:
        return True

    def supports_streaming(self) -> bool:
        return False

    def supports_voice_modes(self) -> bool:
        return True

    def supports_style_clone(self) -> bool:
        return True

    def default_cfg_scale(self) -> float | None:
        return 2.0

    def available_voices(self) -> list:
        return []

    # -- synthesis
    def _build_synth_msg(self, req: EngineSynthRequest, out_wav: str) -> dict:
        """Build the worker 'synth' message, dispatching on voice_mode.

        Mode resolution mirrors the frontend's effective-mode rule: an explicit
        req.voice_mode wins; otherwise clone if a reference voice is present,
        else auto. An empty design style downgrades to auto so a blank box
        never errors. The worker composes the inline "(style)" prefix.
        """
        text = (req.text or "").strip()
        if not text:
            raise ValueError("text must be non-empty")
        mode = req.voice_mode or ("clone" if req.reference_audio else "auto")
        style = (req.instruct or "").strip()
        if mode == "design" and not style:
            mode = "auto"
        msg: dict[str, Any] = {
            "op": "synth",
            "mode": mode,
            "text": text,
            "out_wav": out_wav,
        }
        if mode == "clone":
            if not req.reference_audio:
                raise ValueError("VoxCPM clone mode requires a reference voice.")
            msg["ref_audio"] = req.reference_audio
            transcript = (req.reference_text or "").strip()
            if transcript:
                msg["prompt_text"] = transcript
        if style and mode in ("design", "clone"):
            msg["instruct"] = style
        cfg = req.cfg_scale
        if cfg is not None:
            msg["cfg_value"] = float(cfg)
        steps = req.inference_steps if req.inference_steps is not None else self._inference_timesteps
        if steps is not None:
            msg["inference_timesteps"] = int(steps)
        return msg

    def synthesize(self, req: EngineSynthRequest) -> EngineResult:
        if not self.is_loaded():
            raise RuntimeError("VoxCPM worker is not loaded")
        fd, out_wav = tempfile.mkstemp(suffix=".wav", prefix="voxcpm-")
        os.close(fd)
        try:
            msg = self._build_synth_msg(req, out_wav)
            resp = self._exchange(msg)
            if not resp.get("ok"):
                raise RuntimeError(f"VoxCPM synth failed: {resp.get('error', 'unknown error')}")
            wav_bytes = Path(out_wav).read_bytes()
        finally:
            try:
                os.unlink(out_wav)
            except OSError:
                pass
        return EngineResult(
            wav_bytes=wav_bytes,
            sample_rate=int(resp.get("sample_rate", self.sample_rate())),
            duration_sec=float(resp.get("duration_sec", 0.0)),
            inference_ms=int(resp.get("inference_ms", 0)),
        )

    # -- internals
    def _exchange(self, msg: dict, expect_reply: bool = True) -> dict:
        """Send one JSON line; read one JSON reply line. Thread-safe."""
        with self._lock:
            if self._proc is None or self._proc.stdin is None or self._proc.stdout is None:
                raise RuntimeError("VoxCPM worker is not running")
            try:
                self._proc.stdin.write(json.dumps(msg) + "\n")
                self._proc.stdin.flush()
            except (BrokenPipeError, OSError) as exc:
                self._kill()
                raise RuntimeError(f"VoxCPM worker pipe broke: {exc}") from exc
            if not expect_reply:
                return {"ok": True}
            while True:
                line = self._proc.stdout.readline()
                if not line:
                    if self._stderr_thread is not None:
                        self._stderr_thread.join(timeout=1.0)
                    stderr = self._recent_stderr()
                    self._kill()
                    raise RuntimeError(
                        "VoxCPM worker closed unexpectedly"
                        + (f": {stderr}" if stderr else "")
                    )
                stripped = line.strip()
                if not stripped:
                    continue
                try:
                    return json.loads(stripped)
                except json.JSONDecodeError:
                    log.debug("voxcpm worker non-protocol stdout: %s", stripped[:200])
                    continue

    def _start_stderr_drain(self) -> None:
        proc = self._proc
        if proc is None or proc.stderr is None:
            return
        self._stderr_tail.clear()

        def _drain(stream, sink) -> None:
            try:
                for line in stream:
                    sink.append(line.rstrip("\n"))
            except Exception:  # noqa: BLE001
                pass

        thread = threading.Thread(
            target=_drain, args=(proc.stderr, self._stderr_tail), daemon=True
        )
        thread.start()
        self._stderr_thread = thread

    def _recent_stderr(self) -> str:
        return "\n".join(self._stderr_tail).strip()

    def _kill(self) -> None:
        proc, self._proc = self._proc, None
        if proc is None:
            return
        try:
            if proc.poll() is None:
                proc.terminate()
                try:
                    proc.wait(timeout=5)
                except subprocess.TimeoutExpired:
                    proc.kill()
        except Exception:  # noqa: BLE001
            pass
```

- [ ] **Step 4: Run the test to verify it passes**

Run: `./backend/venv/Scripts/python.exe -m pytest backend/tests/test_voxcpm_engine.py -v`
Expected: PASS (9 tests).

- [ ] **Step 5: Commit**

```bash
git add backend/core/engines/voxcpm_engine.py backend/tests/test_voxcpm_engine.py
git commit -m "feat(voxcpm): VoxCPMEngine isolated-worker proxy"
```

---

## Task 4: Register VoxCPM in config + EngineManager

**Files:**
- Modify: `backend/config.py:27`, `backend/config.py:56-57`
- Modify: `backend/core/engine_manager.py:21`, `:50-69`, `:77-98`
- Modify: `backend/app.py:171-173`

- [ ] **Step 1: Add settings** in `backend/config.py`

Change the `default_engine` Literal (line 27) to include voxcpm:

```python
    default_engine: Literal["vibevoice", "kokoro", "chatterbox", "omnivoice", "voxcpm"] = "vibevoice"
```

After the omnivoice settings (line 57), add:

```python
    voxcpm_model_id: str = "openbmb/VoxCPM2"
    # Diffusion inference timesteps (5 fast … 25 high quality). Default 10.
    voxcpm_inference_timesteps: int = 10
```

- [ ] **Step 2: Register the engine** in `backend/core/engine_manager.py`

Add the import (after line 21, the omnivoice import):

```python
from .engines.voxcpm_engine import VoxCPMEngine
```

Add constructor params (in `__init__`, after `omnivoice_num_step: int = 32,` on line 67):

```python
        voxcpm_model_id: str = "openbmb/VoxCPM2",
        voxcpm_inference_timesteps: int = 10,
```

Add to the `_engines` dict (after the `"omnivoice": OmniVoiceEngine(...)` block, before the closing `}` on line 98):

```python
            "voxcpm": VoxCPMEngine(
                model_id=voxcpm_model_id,
                device_request=device_request,
                inference_timesteps=voxcpm_inference_timesteps,
            ),
```

- [ ] **Step 3: Pass settings through** in `backend/app.py`

After `omnivoice_num_step=settings.omnivoice_num_step,` (line 172), add:

```python
        voxcpm_model_id=settings.voxcpm_model_id,
        voxcpm_inference_timesteps=settings.voxcpm_inference_timesteps,
```

- [ ] **Step 4: Verify the engine registers and lists**

Run: `./backend/venv/Scripts/python.exe -m pytest backend/tests/test_smoke.py -v`
Expected: PASS. Then sanity-check the registry:
Run: `./backend/venv/Scripts/python.exe -c "from backend.config import get_settings; from backend.core.engine_manager import EngineManager as M; s=get_settings(); em=M(default_engine='vibevoice', voices_dir=s.voices_dir, uploads_dir=s.uploads_dir, model_id=s.model_id, device_request='cpu'); print([e.name for e in em.list_engines()])"`
Expected: a list ending with `'voxcpm'`.

- [ ] **Step 5: Commit**

```bash
git add backend/config.py backend/core/engine_manager.py backend/app.py
git commit -m "feat(voxcpm): register engine in config + EngineManager"
```

---

## Task 5: Per-voice reference transcript (backend storage)

**Files:**
- Modify: `backend/services/voices.py` (`VoiceInfo`, `_load_meta_overrides`, `_scan_*`, `update_meta`, new `get_reference_transcript`)
- Modify: `backend/api/schemas.py` (`VoiceInfoModel`, `VoiceMetaUpdate`)
- Modify: `backend/api/voices.py` (pass transcript through the meta-update route)
- Create/extend: `backend/tests/test_voices.py`

- [ ] **Step 1: Write the failing test** — append to `backend/tests/test_voices.py` (create the file if absent with the imports below)

```python
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT))

import soundfile as sf  # noqa: E402
import numpy as np  # noqa: E402

from backend.services.voices import VoiceRegistry  # noqa: E402


def _make_registry(tmp_path):
    voices = tmp_path / "voices"
    uploads = tmp_path / "uploads"
    voices.mkdir()
    uploads.mkdir()
    # one upload voice
    sr = 24000
    sf.write(str(uploads / "user-test-abc123.wav"), np.zeros(sr, dtype="int16"), sr)
    return VoiceRegistry(voices_dir=voices, uploads_dir=uploads)


def test_reference_transcript_round_trips(tmp_path):
    reg = _make_registry(tmp_path)
    reg.update_meta("user-test-abc123", reference_transcript="hello world")
    assert reg.get_reference_transcript("user-test-abc123") == "hello world"
    # New registry reading the same dir sees the persisted transcript.
    reg2 = _make_registry(tmp_path)
    info = next(v for v in reg2.list() if v.id == "user-test-abc123")
    assert info.reference_transcript == "hello world"


def test_reference_transcript_absent_is_none(tmp_path):
    reg = _make_registry(tmp_path)
    assert reg.get_reference_transcript("user-test-abc123") is None
```

- [ ] **Step 2: Run the test to verify it fails**

Run: `./backend/venv/Scripts/python.exe -m pytest backend/tests/test_voices.py -v`
Expected: FAIL — `TypeError: update_meta() got an unexpected keyword argument 'reference_transcript'`.

- [ ] **Step 3: Add the field to `VoiceInfo`** (`backend/services/voices.py`, after `engine: str | None = None` on line 53):

```python
    # Optional transcript of the reference clip, used by VoxCPM "ultimate
    # cloning". None when unset. Persisted in voices.json.
    reference_transcript: str | None = None
```

- [ ] **Step 4: Load it in both scanners**

In `_load_meta_overrides` (after the `language` clause, before `result[str(voice_id)] = clean` on line 150):

```python
            if "reference_transcript" in meta and isinstance(meta["reference_transcript"], str):
                clean["reference_transcript"] = meta["reference_transcript"].strip()
```

In `_scan_builtin`'s `VoiceInfo(...)` (after `size_bytes=path.stat().st_size,`):

```python
                            reference_transcript=override.get("reference_transcript"),
```

In `_scan_uploads`'s `VoiceInfo(...)` (after `sample_rate=sr,`):

```python
                            reference_transcript=override.get("reference_transcript"),
```

- [ ] **Step 5: Extend `update_meta`** — add the parameter and persist it

Change the signature (lines 234-240) to add a keyword:

```python
    def update_meta(
        self,
        voice_id: str,
        name: str | None = None,
        gender: str | None = None,
        language: str | None = None,
        reference_transcript: str | None = None,
    ) -> VoiceInfo:
```

After the `language` handling block (after line 269), add:

```python
        if reference_transcript is not None:
            rt = reference_transcript.strip()
            current["reference_transcript"] = rt or None
```

- [ ] **Step 6: Add the resolver** — after `get_language` (line 345), add:

```python
    def get_reference_transcript(self, voice_id: str) -> str | None:
        """Return the stored reference transcript for a voice, or None.

        Used by VoxCPM "ultimate cloning" to pass a prompt transcript that
        guides high-fidelity continuation from the reference clip.
        """
        for v in self.list():
            if v.id == voice_id:
                return v.reference_transcript
        return None
```

- [ ] **Step 7: Schemas** — in `backend/api/schemas.py`, add to `VoiceInfoModel` (after `engine: str | None = None`, line 48):

```python
    reference_transcript: str | None = None
```

and to `VoiceMetaUpdate` (after `language: str | None = None`, line 55):

```python
    reference_transcript: str | None = None
```

- [ ] **Step 8: Route** — in `backend/api/voices.py`, find the meta-update handler that calls `registry.update_meta(...)` and pass the new field. Add `reference_transcript=body.reference_transcript` to that `update_meta(...)` call (the handler already forwards `name`/`gender`/`language` from the `VoiceMetaUpdate` body).

- [ ] **Step 9: Run the test to verify it passes**

Run: `./backend/venv/Scripts/python.exe -m pytest backend/tests/test_voices.py -v`
Expected: PASS (2 tests).

- [ ] **Step 10: Commit**

```bash
git add backend/services/voices.py backend/api/schemas.py backend/api/voices.py backend/tests/test_voices.py
git commit -m "feat(voices): optional per-voice reference_transcript for ultimate cloning"
```

---

## Task 6: SynthService — generalize voice modes, resolve transcript, cache key

**Files:**
- Modify: `backend/services/synthesize.py` (`_resolve_request_context`, `synthesize`, multi-speaker path, `_voice_cache_key`)
- Modify: `backend/tests/test_synthesize.py`

- [ ] **Step 1: Write the failing tests** — append to `backend/tests/test_synthesize.py`

```python
from backend.services.synthesize import _voice_cache_key


def test_cache_key_folds_reference_transcript():
    plain = _voice_cache_key("v", "clone", None, "/tmp/v.wav", None, None)
    ult = _voice_cache_key("v", "clone", None, "/tmp/v.wav", "a transcript", None)
    assert plain != ult  # ultimate clone must not collide with plain clone


def test_cache_key_folds_timesteps():
    fast = _voice_cache_key("v", "clone", None, "/tmp/v.wav", None, 5)
    high = _voice_cache_key("v", "clone", None, "/tmp/v.wav", None, 25)
    assert fast != high


def test_cache_key_identical_inputs_collide():
    a = _voice_cache_key("v", "clone", None, "/tmp/v.wav", "t", 10)
    b = _voice_cache_key("v", "clone", None, "/tmp/v.wav", "t", 10)
    assert a == b


def test_cache_key_backwards_compatible_without_new_args():
    # Existing callers passing only the original 4 args still work via defaults.
    assert _voice_cache_key("v", None, None, None) == "v"
```

- [ ] **Step 2: Run to verify it fails**

Run: `./backend/venv/Scripts/python.exe -m pytest backend/tests/test_synthesize.py -k cache_key -v`
Expected: FAIL — `_voice_cache_key()` takes 4 positional args.

- [ ] **Step 3: Extend `_voice_cache_key`** (`backend/services/synthesize.py`, lines 473-491). Replace the function with:

```python
def _voice_cache_key(
    voice_id: str,
    voice_mode: str | None,
    instruct: str | None,
    reference_audio: str | None,
    reference_text: str | None = None,
    timesteps: int | None = None,
) -> str:
    """Cache-key 'voice' component, folding voice-mode/instruct/transcript/quality.

    For engines without voice modes (voice_mode None) and no transcript/quality
    this returns exactly what the old inline logic did, so their cache entries
    don't churn. For VoxCPM/OmniVoice it keeps clone/design/auto, distinct
    design prompts, ultimate-clone transcripts, and Fast/Balanced/High quality
    in separate slots.
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
    if reference_text:
        digest = hashlib.sha256(reference_text.encode("utf-8")).hexdigest()[:8]
        base += f"|rt={digest}"
    if timesteps is not None:
        base += f"|ts={timesteps}"
    return base
```

Ensure `import hashlib` is present at the top of `synthesize.py` (add it if missing).

- [ ] **Step 4: Generalize voice-mode resolution** in `_resolve_request_context`. Replace the gating at lines 196-207 (the `for sp in req.speakers:` block) with a capability-driven version that also resolves the transcript:

```python
        reference_audio: str | None = None
        voice_language: str | None = None
        reference_transcript: str | None = None
        supports_modes = target_engine.supports_voice_modes()
        for sp in req.speakers:
            if supports_modes:
                sp_mode = sp.voice_mode or ("clone" if sp.voice_id else "auto")
            else:
                sp_mode = "clone"
            if sp_mode != "clone":
                continue
            if not sp.voice_id:
                raise TextInvalid("a reference voice is required; pick a voice for each speaker")
            if target_engine.supports_voice_cloning():
                reference_audio = str(self._voices.get(sp.voice_id))
            voice_language = voice_language or self._voices.get_language(sp.voice_id)
            reference_transcript = reference_transcript or self._voices.get_reference_transcript(sp.voice_id)
```

Then update the return tuple at line 218 to append `reference_transcript`:

```python
        return target_engine, target_name, reference_audio, voice_language, cfg, steps_override, text, reference_transcript
```

- [ ] **Step 5: Update the two unpack sites**

In `synthesize()` (line 237-238):

```python
        target_engine, target_name, reference_audio, voice_language, cfg, steps_override, text, reference_transcript = \
            self._resolve_request_context(req)
```

In `stream_synthesize()` (line 385-386) — append one throwaway:

```python
        target_engine, _name, _ref_audio, voice_language, cfg, _steps, text, _ref_text = \
            self._resolve_request_context(req)
```

- [ ] **Step 6: Fold transcript + timesteps into the cache key** in `synthesize()`. Replace the `cache_voice_key = _voice_cache_key(...)` call (lines 250-252) with:

```python
            cache_voice_key = _voice_cache_key(
                sp0.voice_id, sp0.voice_mode, sp0.instruct, reference_audio,
                reference_transcript, steps_override,
            )
```

- [ ] **Step 7: Pass `reference_text` into the engine requests**

In the single-speaker `EngineSynthRequest(...)` (lines 294-304), after `instruct=sp0.instruct,` add:

```python
                reference_text=reference_transcript,
```

In the multi-speaker `EngineSynthRequest(...)` (lines 332-345), after `instruct=req.speakers[0].instruct,` add:

```python
                reference_text=reference_transcript,
```

- [ ] **Step 8: Run the tests**

Run: `./backend/venv/Scripts/python.exe -m pytest backend/tests/test_synthesize.py -v`
Expected: PASS (new cache-key tests + existing tests unaffected).

- [ ] **Step 9: Commit**

```bash
git add backend/services/synthesize.py backend/tests/test_synthesize.py
git commit -m "feat(synth): capability-driven voice modes + transcript/quality cache keys for VoxCPM"
```

---

## Task 7: Capability flags through the engines API

**Files:**
- Modify: `backend/api/engines.py` (`EngineInfoModel`, `_to_model`)
- Modify: `backend/api/schemas.py` (`EngineInfoModel`)
- Modify: `backend/tests/` (add an assertion to an existing engines test, or create `test_engines_api.py`)

- [ ] **Step 1: Write the failing test** — create `backend/tests/test_engines_capabilities.py`

```python
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT))

from fastapi.testclient import TestClient  # noqa: E402

from backend.app import create_app  # noqa: E402


def test_engines_list_exposes_voice_mode_flags():
    client = TestClient(create_app())
    data = client.get("/api/engines").json()
    by_name = {e["name"]: e for e in data["engines"]}
    assert by_name["voxcpm"]["supports_voice_modes"] is True
    assert by_name["voxcpm"]["supports_style_clone"] is True
    assert by_name["omnivoice"]["supports_voice_modes"] is True
    assert by_name["omnivoice"]["supports_style_clone"] is False
    assert by_name["vibevoice"]["supports_voice_modes"] is False
```

> If `create_app` isn't the factory name, check `backend/app.py` / `backend/cli.py` for the actual factory and adjust the import.

- [ ] **Step 2: Run to verify it fails**

Run: `./backend/venv/Scripts/python.exe -m pytest backend/tests/test_engines_capabilities.py -v`
Expected: FAIL — `KeyError: 'supports_voice_modes'` (not yet in the response model).

- [ ] **Step 3: Add fields to `EngineInfoModel` in `backend/api/engines.py`** (after `languages: list[EngineLanguageModel] = []` on line 44):

```python
    supports_voice_modes: bool = False
    supports_style_clone: bool = False
```

In `_to_model` (after `languages=[...]` on line 102), add:

```python
        supports_voice_modes=info.get("supports_voice_modes", False),
        supports_style_clone=info.get("supports_style_clone", False),
```

- [ ] **Step 4: Mirror in `backend/api/schemas.py`'s `EngineInfoModel`** (after `active: bool = False`, line 93):

```python
    supports_voice_modes: bool = False
    supports_style_clone: bool = False
```

- [ ] **Step 5: Run to verify it passes**

Run: `./backend/venv/Scripts/python.exe -m pytest backend/tests/test_engines_capabilities.py -v`
Expected: PASS.

- [ ] **Step 6: Commit**

```bash
git add backend/api/engines.py backend/api/schemas.py backend/tests/test_engines_capabilities.py
git commit -m "feat(api): expose supports_voice_modes/supports_style_clone on engines"
```

---

## Task 8: CUDA-tag detection for VoxCPM

**Files:**
- Modify: `tools/envdetect.py`
- Modify: `backend/tests/test_setup_helpers.py`

VoxCPM needs torch ≥2.5; its CUDA wheels are cu124/cu126/cu128. Reuse the OmniVoice torch-2.8 mapping (cu126/cu128) — it satisfies torch ≥2.5 — exposed under a VoxCPM-named function so the studio.py call site reads clearly.

- [ ] **Step 1: Write the failing test** — append to `backend/tests/test_setup_helpers.py`

```python
from tools.envdetect import detect_voxcpm_cuda_tag, cuda_version_to_voxcpm_tag


def test_cuda_version_to_voxcpm_tag():
    assert cuda_version_to_voxcpm_tag("13.0") == "cu128"
    assert cuda_version_to_voxcpm_tag("12.8") == "cu128"
    assert cuda_version_to_voxcpm_tag("12.6") == "cu126"
    assert cuda_version_to_voxcpm_tag("12.4") is None  # below cu126 → CPU fallback
    assert cuda_version_to_voxcpm_tag(None) is None


def test_detect_voxcpm_cuda_tag_uses_runner():
    fake = lambda: "NVIDIA-SMI ... CUDA Version: 12.8 ..."
    assert detect_voxcpm_cuda_tag(runner=fake) == "cu128"
```

- [ ] **Step 2: Run to verify it fails**

Run: `./backend/venv/Scripts/python.exe -m pytest backend/tests/test_setup_helpers.py -k voxcpm -v`
Expected: FAIL — `ImportError: cannot import name 'detect_voxcpm_cuda_tag'`.

- [ ] **Step 3: Add the functions to `tools/envdetect.py`** (after `detect_omnivoice_cuda_tag`, end of file):

```python
def cuda_version_to_voxcpm_tag(version: str | None) -> str | None:
    """Map a CUDA runtime version to a torch wheel tag for VoxCPM.

    VoxCPM needs torch>=2.5; we install a torch 2.8 CUDA build whose wheels are
    cu126/cu128 (same as OmniVoice). Drivers below CUDA 12.6 fall back to CPU.
    """
    return cuda_version_to_omnivoice_tag(version)


def detect_voxcpm_cuda_tag(runner=None) -> str | None:
    """Detect the torch CUDA wheel tag for VoxCPM. `runner` is injectable."""
    run = runner or _run_nvidia_smi
    text = run()
    if text is None:
        return None
    return cuda_version_to_voxcpm_tag(parse_nvidia_smi_cuda_version(text))
```

- [ ] **Step 4: Run to verify it passes**

Run: `./backend/venv/Scripts/python.exe -m pytest backend/tests/test_setup_helpers.py -k voxcpm -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add tools/envdetect.py backend/tests/test_setup_helpers.py
git commit -m "feat(envdetect): VoxCPM CUDA wheel-tag detection"
```

---

## Task 9: studio.py install-voxcpm (env builder + Python guard)

**Files:**
- Modify: `studio.py` (helpers, `_ensure_voxcpm_env`, `cmd_install_voxcpm`, subparser, dispatch)
- Modify: `backend/tests/test_setup_helpers.py`

- [ ] **Step 1: Write the failing test** — append to `backend/tests/test_setup_helpers.py`

```python
def test_python_supported_for_voxcpm():
    import studio
    assert studio._python_supported_for_voxcpm((3, 11)) is True
    assert studio._python_supported_for_voxcpm((3, 12)) is True
    assert studio._python_supported_for_voxcpm((3, 13)) is False
    assert studio._python_supported_for_voxcpm((3, 9)) is False
```

- [ ] **Step 2: Run to verify it fails**

Run: `./backend/venv/Scripts/python.exe -m pytest backend/tests/test_setup_helpers.py -k voxcpm -v`
Expected: FAIL — `AttributeError: module 'studio' has no attribute '_python_supported_for_voxcpm'`.

- [ ] **Step 3: Add venv-path + marker helpers to `studio.py`** (after `omnivoice_ready_marker`, line 79):

```python
def voxcpm_venv_python(repo_root: Path) -> Path:
    """Path to the ISOLATED VoxCPM venv's Python interpreter."""
    venv = repo_root / "backend" / "venv-voxcpm"
    if os.name == "nt":
        return venv / "Scripts" / "python.exe"
    return venv / "bin" / "python"


def voxcpm_ready_marker(repo_root: Path) -> Path:
    """Sentinel written only after a FULL successful VoxCPM install."""
    return repo_root / "backend" / "venv-voxcpm" / ".voxcpm-ready"


def _python_supported_for_voxcpm(version_info) -> bool:
    """VoxCPM (torchcodec/funasr) supports Python 3.10–3.12 only."""
    major, minor = version_info[0], version_info[1]
    return major == 3 and 10 <= minor <= 12
```

- [ ] **Step 4: Add `_ensure_voxcpm_env`** (after `_ensure_omnivoice_env`, line 234):

```python
def _ensure_voxcpm_env() -> bool:
    """Create backend/venv-voxcpm and install voxcpm into it.

    VoxCPM needs torch>=2.5 / CUDA>=12 plus a heavy dependency tail, so it gets
    its own environment with a CUDA-matched torch + voxcpm. Returns True on
    success, False on any failure.
    """
    if not _python_supported_for_voxcpm(sys.version_info):
        print(
            "  ERROR: VoxCPM requires Python 3.10–3.12 (you have "
            f"{sys.version_info.major}.{sys.version_info.minor}). "
            "Install a supported Python and re-run."
        )
        return False
    marker = voxcpm_ready_marker(REPO_ROOT)
    try:
        marker.unlink()
    except OSError:
        pass
    vpy = voxcpm_venv_python(REPO_ROOT)
    if not vpy.is_file():
        print("  Creating isolated VoxCPM environment (backend/venv-voxcpm) …")
        if _run([sys.executable, "-m", "venv", str(BACKEND_DIR / "venv-voxcpm")]) != 0:
            print("  ERROR: failed to create venv-voxcpm.")
            return False
    print("  Upgrading pip in the VoxCPM env …")
    raw_ok = _run([str(vpy), "-m", "pip", "install", "--upgrade", "pip"]) == 0
    progress = ["--progress-bar", "raw"] if raw_ok else []
    net = ["--retries", "10", "--timeout", "120"]
    # 1. Install voxcpm FIRST (pulls a torch build to satisfy its pin).
    print("  Installing voxcpm into the VoxCPM env …")
    if _run([str(vpy), "-m", "pip", "install", *progress, *net, "-r",
             str(BACKEND_DIR / "requirements-voxcpm.txt")]) != 0:
        print("  ERROR: voxcpm install failed.")
        return False
    # 2. Swap in the CUDA build of torch+torchaudio for GPU. Let pip pick the
    #    newest matching pair the CUDA index has (VoxCPM only needs torch>=2.5);
    #    pinning an exact PyPI version 404s on the wheel-only CUDA index.
    vx_tag = envdetect.detect_voxcpm_cuda_tag()
    index = envdetect.torch_index_url(vx_tag) if vx_tag else None
    if index:
        print(f"  Installing the CUDA build of torch+torchaudio ({vx_tag}) for GPU …")
        if _run([str(vpy), "-m", "pip", "install", *progress, *net, "--force-reinstall",
                 "--no-deps", "--index-url", index, "torch", "torchaudio"]) != 0:
            print("  ERROR: CUDA torch install failed.")
            return False
    else:
        print("  No matching torch CUDA build for this driver — leaving the "
              "default (CPU) torch in place. VoxCPM will run on CPU (slow).")
    try:
        marker.parent.mkdir(parents=True, exist_ok=True)
        marker.write_text("ok\n", encoding="utf-8")
    except OSError as exc:
        print(f"  ERROR: could not write ready marker: {exc}")
        return False
    print("  VoxCPM environment ready.")
    return True
```

- [ ] **Step 5: Add `cmd_install_voxcpm`** (after `cmd_install_omnivoice`, line 407):

```python
def cmd_install_voxcpm(_args: argparse.Namespace) -> int:
    """Non-interactive: build/refresh the isolated VoxCPM env. Used by the
    backend's in-UI installer. Returns 0 on success, 1 on failure."""
    print(BANNER)
    ok = _ensure_voxcpm_env()
    return 0 if ok else 1
```

- [ ] **Step 6: Register the subcommand + dispatch** in `main()` (around lines 565 and 575):

After `sub.add_parser("install-omnivoice", ...)`:

```python
    sub.add_parser("install-voxcpm", help="build the isolated VoxCPM env (non-interactive)")
```

After the `if args.command == "install-omnivoice":` block:

```python
    if args.command == "install-voxcpm":
        return cmd_install_voxcpm(args)
```

- [ ] **Step 7: Run to verify it passes**

Run: `./backend/venv/Scripts/python.exe -m pytest backend/tests/test_setup_helpers.py -k voxcpm -v`
Expected: PASS.

- [ ] **Step 8: Commit**

```bash
git add studio.py backend/tests/test_setup_helpers.py
git commit -m "feat(studio): install-voxcpm isolated env builder with Python 3.10–3.12 guard"
```

---

## Task 10: Download / delete / uninstall registration

**Files:**
- Modify: `backend/scripts/download_models.py` (`MODEL_CATALOG`)
- Modify: `backend/services/model_download.py` (`DOWNLOADABLE`)
- Modify: `backend/services/model_delete.py` (`DELETABLE`)
- Modify: `backend/services/engine_uninstall.py` (`UNINSTALLABLE`)
- Modify: `backend/app.py` (installers + uninstallers)
- Modify: `backend/tests/test_chatterbox_install.py` (extend to assert voxcpm install endpoint)

- [ ] **Step 1: Add the catalog entry** in `backend/scripts/download_models.py` (after the `"omnivoice"` entry, line 37):

```python
    "voxcpm": {
        "repo_id": "openbmb/VoxCPM2",
        "size": "~5 GB",
        "label": "VoxCPM2",
    },
```

> Confirm the real repo size with `./backend/venv/Scripts/python.exe -c "from huggingface_hub import HfApi; i=HfApi().model_info('openbmb/VoxCPM2', files_metadata=True); print(sum((s.size or (s.lfs.size if s.lfs else 0) or 0) for s in i.siblings)/1e9, 'GB')"` and update the `"size"` string if materially different. (Spec Risk #2.)

- [ ] **Step 2: Add to the lifecycle frozensets**

`backend/services/model_download.py:21`:

```python
DOWNLOADABLE: frozenset[str] = frozenset({"vibevoice", "kokoro", "omnivoice", "voxcpm"})
```

`backend/services/model_delete.py:22`:

```python
DELETABLE: frozenset[str] = frozenset({"vibevoice", "kokoro", "omnivoice", "chatterbox", "voxcpm"})
```

`backend/services/engine_uninstall.py:24`:

```python
UNINSTALLABLE: frozenset[str] = frozenset({"chatterbox", "omnivoice", "voxcpm"})
```

- [ ] **Step 3: Wire installer + uninstaller** in `backend/app.py`

In `app.state.engine_installers` (line 208-211), add:

```python
        "voxcpm": EngineEnvInstaller("install-voxcpm"),
```

In `app.state.engine_uninstallers` (line 214-217), add:

```python
        "voxcpm": EngineEnvUninstaller("voxcpm", em=engine_manager),
```

- [ ] **Step 4: Write the failing test** — append to `backend/tests/test_chatterbox_install.py`

```python
def test_install_endpoint_supports_voxcpm():
    vx = EngineEnvInstaller("install-voxcpm", runner=_fake_runner(["hi"], 0))
    from fastapi import FastAPI
    from fastapi.testclient import TestClient
    from backend.api.engines import router
    app = FastAPI()
    app.include_router(router)
    app.state.engine_installers = {"voxcpm": vx}
    client = TestClient(app)
    assert client.get("/api/engines/voxcpm/install").json()["state"] == "not_installed"
    assert client.post("/api/engines/voxcpm/install").status_code == 200
    _wait(vx)
    assert "hi" in client.get("/api/engines/voxcpm/install").json()["log"]
```

- [ ] **Step 5: Run the lifecycle tests**

Run: `./backend/venv/Scripts/python.exe -m pytest backend/tests/test_chatterbox_install.py backend/tests/test_model_delete.py backend/tests/test_engine_uninstall.py -v`
Expected: PASS (existing + new voxcpm install test). If `test_model_delete.py` / `test_engine_uninstall.py` assert exact frozenset contents, update those expectations to include `voxcpm`.

- [ ] **Step 6: Commit**

```bash
git add backend/scripts/download_models.py backend/services/model_download.py backend/services/model_delete.py backend/services/engine_uninstall.py backend/app.py backend/tests/test_chatterbox_install.py
git commit -m "feat(voxcpm): wire download/delete/uninstall lifecycle"
```

---

## Task 11: Run the full backend suite

**Files:** none (verification gate).

- [ ] **Step 1: Run everything**

Run: `./backend/venv/Scripts/python.exe -m pytest backend/tests/ -q`
Expected: all pass. Fix any regressions (most likely: a test asserting the exact engine count or a frozenset's exact membership — update those to include `voxcpm`).

- [ ] **Step 2: Commit any fixes**

```bash
git add -A
git commit -m "test(voxcpm): update suite expectations for the new engine"
```

---

## Task 12: Frontend types

**Files:**
- Modify: `frontend/src/types/models.ts`

- [ ] **Step 1: Add the capability flags to `EngineInfo`** (after `languages: EngineLanguage[];`, line 67):

```typescript
  supports_voice_modes: boolean;
  supports_style_clone: boolean;
```

- [ ] **Step 2: Add the transcript to `Voice`** (after `engine: string | null;`, line 31):

```typescript
  reference_transcript: string | null;
```

- [ ] **Step 3: Add it to `VoiceMetadata`** (after `language?: string;`, line 37):

```typescript
  reference_transcript?: string;
```

- [ ] **Step 4: Typecheck**

Run (from `frontend/`): `npm run typecheck`
Expected: new errors only where these fields are now required (EngineInfo construction in tests/mocks). Fix mocks to include the two new booleans (default `false`). If the `Voice` literal is constructed anywhere in tests, add `reference_transcript: null`.

- [ ] **Step 5: Commit**

```bash
git add frontend/src/types/models.ts frontend/src
git commit -m "feat(frontend): VoxCPM capability flags + voice reference_transcript types"
```

---

## Task 13: Rename `lib/omnivoice.ts` → `lib/voiceModes.ts` (generalized)

**Files:**
- Create: `frontend/src/lib/voiceModes.ts`
- Delete: `frontend/src/lib/omnivoice.ts`
- Modify: every importer of `@/lib/omnivoice`

- [ ] **Step 1: Find all importers**

Run (from repo root): `grep -rl "@/lib/omnivoice" frontend/src`
Expected: `SpeakerRoster.tsx`, `App.tsx`, and any TTS editor/components (note the exact list).

- [ ] **Step 2: Create `frontend/src/lib/voiceModes.ts`** with the generalized API (superset of the old module — keeps OmniVoice's chips, adds a shared mode type):

```typescript
// Shared per-speaker voice-mode helpers for engines that support
// Clone/Design/Auto (OmniVoice and VoxCPM). OmniVoice-specific design-chip
// vocabulary is kept here but only surfaced for OmniVoice in the UI.

export type VoiceMode = "clone" | "design" | "auto";
// Back-compat alias for existing call sites.
export type OmniMode = VoiceMode;

// OmniVoice's official valid English instruct vocabulary (the worker rejects
// unknown items). VoxCPM uses FREE-TEXT design/style, so it does NOT use these.
export const DESIGN_CHIPS: string[] = [
  "female",
  "male",
  "child",
  "teenager",
  "young adult",
  "middle-aged",
  "elderly",
  "very low pitch",
  "low pitch",
  "moderate pitch",
  "high pitch",
  "very high pitch",
  "american accent",
  "british accent",
  "australian accent",
  "canadian accent",
  "indian accent",
  "chinese accent",
  "japanese accent",
  "korean accent",
  "russian accent",
  "portuguese accent",
  "whisper",
];

export const NONVERBAL_TAGS: string[] = [
  "[laughter]",
  "[sigh]",
  "[confirmation-en]",
  "[question-en]",
  "[question-ah]",
  "[question-oh]",
  "[question-ei]",
  "[question-yi]",
  "[surprise-ah]",
  "[surprise-oh]",
  "[surprise-wa]",
  "[surprise-yo]",
  "[dissatisfaction-hnn]",
];

/**
 * The speaker's effective voice mode. An explicit choice wins; otherwise clone
 * if a reference voice is set, else auto. Keeping it derived means switching
 * engines never mutates speaker state.
 */
export function effectiveMode(speaker: { voice: string; omnivoiceMode?: VoiceMode }): VoiceMode {
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

- [ ] **Step 3: Update every importer** — change `from "@/lib/omnivoice"` to `from "@/lib/voiceModes"` in each file from Step 1. Leave the imported symbol names unchanged (`effectiveMode`, `OmniMode`, `DESIGN_CHIPS`, `appendDesignChip`).

- [ ] **Step 4: Delete the old module**

```bash
git rm frontend/src/lib/omnivoice.ts
```

- [ ] **Step 5: Typecheck**

Run (from `frontend/`): `npm run typecheck`
Expected: PASS (no dangling `@/lib/omnivoice` imports).

- [ ] **Step 6: Commit**

```bash
git add frontend/src/lib/voiceModes.ts frontend/src
git commit -m "refactor(frontend): generalize lib/omnivoice → lib/voiceModes"
```

---

## Task 14: SpeakerRoster — capability gating + Clone-mode style field

**Files:**
- Modify: `frontend/src/components/SpeakerRoster.tsx`

The roster must (a) show the Clone/Design/Auto toggle for any engine with `supports_voice_modes`, and (b) when `supports_style_clone`, show an optional "Style (optional)" input in Clone mode (controllable cloning). It needs the active `EngineInfo`, not just the name string.

- [ ] **Step 1: Accept the active engine's capability flags**

Change the `Props` (lines 6-15) — replace `activeEngine: string | null;` with:

```typescript
  activeEngine: string | null;
  supportsVoiceModes: boolean;
  supportsStyleClone: boolean;
```

Thread both through `SpeakerRoster` to each `SpeakerRow` (add to the destructure, the `<SpeakerRow … />` props, and the `SpeakerRow` signature/type).

- [ ] **Step 2: Gate on the capability flag**

Replace `const isOmni = activeEngine === "omnivoice";` (line 139) with:

```typescript
  const showModes = supportsVoiceModes;
```

Replace the `if (!isOmni)` guard (line 143) with `if (!showModes)`.

- [ ] **Step 3: Make the Design chips OmniVoice-only and add the Clone-mode style field**

Replace the `return (...)` block of `SpeakerRow` (lines 168-209) with:

```tsx
  return (
    <div className={`p-3 rounded-lg border ${panelBg} ${panelBorder}`}>
      {nameHeader}
      <div className="flex gap-1 mb-2">
        {segBtn("clone", "Clone")}
        {segBtn("design", "Design")}
        {segBtn("auto", "Auto")}
      </div>
      {mode === "clone" && (
        <div className="space-y-1.5">
          {voiceSelect}
          {supportsStyleClone && (
            <input
              type="text"
              value={speaker.voiceDesign ?? ""}
              onChange={(e) => onUpdate({ voiceDesign: e.target.value })}
              placeholder="Style (optional) — e.g. cheerful, slightly faster"
              className={`w-full border rounded-md px-2 py-1.5 text-xs focus:outline-none focus:border-orange-500 ${selectBg} ${selectBorder} ${selectText}`}
            />
          )}
        </div>
      )}
      {mode === "design" && (
        <div className="space-y-1.5">
          <input
            type="text"
            value={speaker.voiceDesign ?? ""}
            onChange={(e) => onUpdate({ voiceDesign: e.target.value })}
            placeholder={activeEngine === "voxcpm" ? "e.g. a young woman, gentle and sweet" : "e.g. female, low pitch, british accent"}
            className={`w-full border rounded-md px-2 py-1.5 text-xs focus:outline-none focus:border-orange-500 ${selectBg} ${selectBorder} ${selectText}`}
          />
          {activeEngine === "omnivoice" && (
            <div className="flex flex-wrap gap-1">
              {DESIGN_CHIPS.map((chip) => (
                <button
                  key={chip}
                  type="button"
                  onClick={() => onUpdate({ voiceDesign: appendDesignChip(speaker.voiceDesign ?? "", chip) })}
                  className={`px-1.5 py-0.5 text-[10px] rounded border transition-colors ${
                    isDark
                      ? "border-zinc-700 text-zinc-400 hover:border-orange-500 hover:text-orange-300"
                      : "border-gray-300 text-gray-600 hover:border-orange-500 hover:text-orange-600"
                  } ${focusRing}`}
                >
                  {chip}
                </button>
              ))}
            </div>
          )}
        </div>
      )}
      {mode === "auto" && (
        <p className={`text-[11px] italic ${isDark ? "text-zinc-400" : "text-gray-600"}`}>
          {activeEngine === "voxcpm"
            ? "VoxCPM will design a fresh voice for this speaker."
            : "OmniVoice will invent a voice for this speaker."}
        </p>
      )}
    </div>
  );
```

- [ ] **Step 4: Update the caller** — in the component that renders `<SpeakerRoster>` (search: `grep -rn "SpeakerRoster" frontend/src`), pass the two new props from the active engine's `EngineInfo`. The active engine object is available where `activeEngine` is computed; pass `supportsVoiceModes={activeEngineInfo?.supports_voice_modes ?? false}` and `supportsStyleClone={activeEngineInfo?.supports_style_clone ?? false}`. If only the name is in scope there, look it up from the engines list (`engines.find(e => e.name === activeEngine)`).

- [ ] **Step 5: Typecheck**

Run (from `frontend/`): `npm run typecheck`
Expected: PASS.

- [ ] **Step 6: Commit**

```bash
git add frontend/src/components/SpeakerRoster.tsx frontend/src
git commit -m "feat(frontend): capability-gated voice modes + VoxCPM controllable-clone style field"
```

---

## Task 15: App.tsx — generalize synth mapping to capability flag

**Files:**
- Modify: `frontend/src/App.tsx`

App.tsx currently keys voice-mode logic on `activeEngine === "omnivoice"` (lines 225, 394, 444, 587) and only sends `instruct` in design mode. For VoxCPM, the mapping must (a) use the capability flag and (b) also send `instruct` (style) in Clone mode.

- [ ] **Step 1: Compute a capability helper near the active engine**

Where `activeEngine` / the engines list is available, derive:

```typescript
const activeEngineInfo = engines.find((e) => e.name === activeEngine) ?? null;
const supportsVoiceModes = activeEngineInfo?.supports_voice_modes ?? false;
```

- [ ] **Step 2: Replace each `activeEngine === "omnivoice"` / `isOmni` gate** used for mode resolution (lines ~225, ~394, ~444, ~587) with `supportsVoiceModes`. Keep the `effectiveMode(...)` calls unchanged.

- [ ] **Step 3: Send `instruct` in Clone mode too**

At each site that computes `const instruct = mode === "design" ? (speaker.voiceDesign ?? "") : undefined;` (lines ~231, ~451, ~595), broaden it so a Clone-mode style is also sent:

```typescript
const instruct =
  (mode === "design" || mode === "clone")
    ? (speaker.voiceDesign?.trim() ? speaker.voiceDesign.trim() : undefined)
    : undefined;
```

(The `...(instruct ? { instruct } : {})` spreads already guard the empty case, so plain clones still send no `instruct`.)

- [ ] **Step 4: Typecheck + smoke test**

Run (from `frontend/`): `npm run typecheck`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add frontend/src/App.tsx
git commit -m "feat(frontend): capability-driven synth mapping + clone-mode style for VoxCPM"
```

---

## Task 16: CFG hints for VoxCPM

**Files:**
- Modify: `frontend/src/lib/engineHints.ts`

- [ ] **Step 1: Add a VoxCPM hints entry** (after `OMNIVOICE_HINTS`, line 102):

```typescript
// VoxCPM `cfg_value` — classifier-free guidance, ~1.0–3.0, default 2.0.
const VOXCPM_HINTS: EngineCfgHints = {
  name: "voxcpm",
  min: 1.0,
  max: 3.0,
  step: 0.1,
  presets: [1.5, 2.0, 2.5, 3.0],
  minLabel: "natural",
  midLabel: "balanced",
  maxLabel: "strict",
  default: 2.0,
  precision: 1,
  hint:
    "VoxCPM CFG (cfg_value). Higher adheres more strictly to the reference voice or design prompt; lower is more natural. Pairs with the Quality control.",
  highlight: "Quality",
};
```

- [ ] **Step 2: Register it** in `HINTS_BY_ENGINE` (line 104-109):

```typescript
  voxcpm: VOXCPM_HINTS,
```

- [ ] **Step 3: Typecheck**

Run (from `frontend/`): `npm run typecheck`
Expected: PASS.

- [ ] **Step 4: Commit**

```bash
git add frontend/src/lib/engineHints.ts
git commit -m "feat(frontend): VoxCPM CFG slider hints (cfg_value 1.0–3.0)"
```

---

## Task 17: Quality control (inference_timesteps) — UI + plumbing

**Files:**
- Modify: `frontend/src/lib/api.ts` (`synthesizeWav` options)
- Modify: `frontend/src/components/ControlPanel.tsx` (the Quality selector, VoxCPM-only)
- Modify: `frontend/src/App.tsx` (state + pass `inferenceSteps` into synth calls)

- [ ] **Step 1: Add the `inferenceSteps` option to `synthesizeWav`** (`frontend/src/lib/api.ts`, lines 271-289)

Add to the `options` type:

```typescript
    inferenceSteps?: number | null;
```

And to the request body builder (inside the `JSON.stringify({...})`, alongside the other optional spreads):

```typescript
      ...(options.inferenceSteps != null ? { inference_steps: options.inferenceSteps } : {}),
```

- [ ] **Step 2: Add a Quality selector to `ControlPanel.tsx`**

`ControlPanel` already receives the active engine. Render this block only when `activeEngine === "voxcpm"`, near the CFG slider. It reads/writes a `quality` value owned by `App.tsx` via new props `quality` + `onQualityChange` (added in Step 3). Add to `ControlPanel`'s Props:

```typescript
  quality?: "fast" | "balanced" | "high";
  onQualityChange?: (q: "fast" | "balanced" | "high") => void;
```

And render (place near the CFG controls; mirror the existing button styling in this file):

```tsx
{activeEngine === "voxcpm" && onQualityChange && (
  <div className="space-y-1.5">
    <div className={`text-xs font-medium ${isDark ? "text-zinc-300" : "text-gray-700"}`}>
      Quality
    </div>
    <div className="flex gap-1">
      {(["fast", "balanced", "high"] as const).map((q) => (
        <button
          key={q}
          type="button"
          onClick={() => onQualityChange(q)}
          className={`flex-1 px-2 py-1.5 text-xs font-medium rounded border transition-colors ${
            (quality ?? "balanced") === q
              ? "bg-orange-600 text-white border-orange-500 hover:bg-orange-500"
              : isDark
                ? "bg-zinc-800 text-zinc-300 hover:bg-zinc-700 border-zinc-700"
                : "bg-gray-100 text-gray-600 hover:bg-gray-200 border-gray-300"
          } ${focusRing}`}
        >
          {q[0].toUpperCase() + q.slice(1)}
        </button>
      ))}
    </div>
    <p className={`text-[11px] ${isDark ? "text-zinc-400" : "text-gray-600"}`}>
      Diffusion steps: Fast 5 · Balanced 10 · High 25. Higher = better quality, slower.
    </p>
  </div>
)}
```

- [ ] **Step 3: Own the state in `App.tsx`** and map to timesteps

Add state (with localStorage persistence, mirroring existing `vs.*` keys):

```typescript
const [quality, setQuality] = useState<"fast" | "balanced" | "high">(
  () => (localStorage.getItem("vs.voxcpm.quality") as "fast" | "balanced" | "high") ?? "balanced",
);
const onQualityChange = (q: "fast" | "balanced" | "high") => {
  setQuality(q);
  localStorage.setItem("vs.voxcpm.quality", q);
};
const QUALITY_TIMESTEPS = { fast: 5, balanced: 10, high: 25 } as const;
```

Pass `quality`/`onQualityChange` to `<ControlPanel>`. In each `synthesizeWav(...)` call, add to the options object (only meaningful for VoxCPM; harmless elsewhere since other engines ignore `inference_steps` unless they use it — guard on the active engine):

```typescript
        ...(activeEngine === "voxcpm" ? { inferenceSteps: QUALITY_TIMESTEPS[quality] } : {}),
```

> Note: VibeVoice also reads `inference_steps` (DDPM steps). Guarding with `activeEngine === "voxcpm"` keeps VibeVoice behavior unchanged.

- [ ] **Step 4: Typecheck**

Run (from `frontend/`): `npm run typecheck`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add frontend/src/lib/api.ts frontend/src/components/ControlPanel.tsx frontend/src/App.tsx
git commit -m "feat(frontend): VoxCPM Quality control → inference_timesteps"
```

---

## Task 18: Voice reference-transcript editor field

**Files:**
- Modify: `frontend/src/lib/api.ts` (`updateVoiceMeta` / `VoiceMetadata`)
- Modify: `frontend/src/components/VoiceLibrary.tsx` (edit form)

- [ ] **Step 1: Carry the field through the API wrapper** — `frontend/src/lib/api.ts`

Add to the local `VoiceMetadata` interface (lines 119-123):

```typescript
  reference_transcript?: string;
```

(`updateVoiceMeta` already JSON-stringifies the whole `meta` object, so no further change is needed there.)

- [ ] **Step 2: Add the textarea to the voice edit form** in `VoiceLibrary.tsx`

Locate the voice edit UI (the form that already edits name/gender/language and calls `updateVoiceMeta`/`editBuiltInVoice`). Add an optional textarea bound to the edited voice's `reference_transcript`, shown for upload voices (and built-ins). Mirror the existing field markup; include it in the `updateVoiceMeta({ ... })` payload. Concretely, add to the editable local state and the save payload:

```tsx
{/* Reference transcript — improves VoxCPM "ultimate cloning" fidelity. */}
<label className={`block text-xs font-medium ${isDark ? "text-zinc-300" : "text-gray-700"}`}>
  Reference transcript <span className="opacity-60">(optional, for VoxCPM)</span>
  <textarea
    value={editTranscript}
    onChange={(e) => setEditTranscript(e.target.value)}
    rows={2}
    placeholder="Exact words spoken in this voice's reference clip"
    className={`mt-1 w-full border rounded-md px-2 py-1.5 text-xs focus:outline-none focus:border-orange-500 ${
      isDark ? "bg-zinc-800 border-zinc-700 text-white" : "bg-white border-gray-300 text-gray-900"
    }`}
  />
</label>
```

with `const [editTranscript, setEditTranscript] = useState(voice.reference_transcript ?? "");` initialized when the editor opens, and `reference_transcript: editTranscript.trim()` added to the `updateVoiceMeta(voice.id, { ... })` call.

- [ ] **Step 3: Typecheck**

Run (from `frontend/`): `npm run typecheck`
Expected: PASS.

- [ ] **Step 4: Commit**

```bash
git add frontend/src/lib/api.ts frontend/src/components/VoiceLibrary.tsx
git commit -m "feat(frontend): per-voice reference transcript editor (VoxCPM ultimate cloning)"
```

---

## Task 19: Engine selector + dialog gating for VoxCPM

**Files:**
- Modify: `frontend/src/components/EngineSelector.tsx` (uninstall gating set)
- Modify: `frontend/src/components/DeleteWeightsDialog.tsx` (`MODEL_SIZES`)
- Modify: `frontend/src/components/DownloadModelDialog.tsx` (`MODEL_SIZES`)

- [ ] **Step 1: Add VoxCPM to the uninstall gating** in `EngineSelector.tsx`

There are two spots gating the "Uninstall environment" button on the engine name (lines 265 and 283): `(e.name === "chatterbox" || e.name === "omnivoice")`. Add `|| e.name === "voxcpm"` to both:

```tsx
(e.name === "chatterbox" || e.name === "omnivoice" || e.name === "voxcpm")
```

- [ ] **Step 2: Add VoxCPM to `DeleteWeightsDialog.tsx` `MODEL_SIZES`** (lines 16-21):

```typescript
  voxcpm: "~5 GB",
```

- [ ] **Step 3: Add VoxCPM to `DownloadModelDialog.tsx`'s size map** — open the file, find its `MODEL_SIZES` (or equivalent label map mirroring `download_models.py`), and add:

```typescript
  voxcpm: "~5 GB",
```

- [ ] **Step 4: Typecheck**

Run (from `frontend/`): `npm run typecheck`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add frontend/src/components/EngineSelector.tsx frontend/src/components/DeleteWeightsDialog.tsx frontend/src/components/DownloadModelDialog.tsx
git commit -m "feat(frontend): VoxCPM gating in engine selector + size labels in dialogs"
```

---

## Task 20: Frontend test pass + final checks

**Files:**
- Modify: frontend test mocks as needed.

- [ ] **Step 1: Run frontend tests**

Run (from `frontend/`): `npm test`
Expected: PASS. Update any test/mock that constructs an `EngineInfo` to include `supports_voice_modes` + `supports_style_clone`, or a `Voice` to include `reference_transcript: null`.

- [ ] **Step 2: Build**

Run (from `frontend/`): `npm run build`
Expected: clean build.

- [ ] **Step 3: Commit any fixes**

```bash
git add frontend/src
git commit -m "test(frontend): update mocks for VoxCPM capability + transcript fields"
```

---

## Task 21: Docs — update CLAUDE.md

**Files:**
- Modify: `CLAUDE.md`

- [ ] **Step 1: Update the engine list and notes**

- In the "What this is" line, add VoxCPM2 to the engine list.
- In the Architecture isolated-engines paragraph, add VoxCPM alongside Chatterbox/OmniVoice (own venv `backend/venv-voxcpm`, `requirements-voxcpm.txt`, `voxcpm_worker.py`, torch ≥2.5 / CUDA ≥12 / Python 3.10–3.12, cu126/cu128 wheel).
- Note the generalized voice-mode capability flags (`supports_voice_modes`/`supports_style_clone`) replacing the OmniVoice hardcode, `lib/voiceModes.ts`, the per-voice `reference_transcript` (ultimate cloning), and the VoxCPM Quality control (`inference_timesteps`).
- Note VoxCPM is downloadable (`openbmb/VoxCPM2`, shared HF cache) and the five generation modes.

- [ ] **Step 2: Commit**

```bash
git add CLAUDE.md
git commit -m "docs: document VoxCPM2 engine integration in CLAUDE.md"
```

---

## Task 22: Final holistic review + manual verification

- [ ] **Step 1: Full backend + frontend suites green**

Run: `./backend/venv/Scripts/python.exe -m pytest backend/tests/ -q` and (from `frontend/`) `npm test`.
Expected: all pass.

- [ ] **Step 2: Dispatch a final code-reviewer** over the whole VoxCPM diff (`git diff main...feat/voxcpm-engine`) for correctness, parity with OmniVoice, and any missed wiring. Address findings.

- [ ] **Step 3 (manual, requires GPU + install):** install and smoke-test end-to-end. This is NOT run during automated CI:
  - `python studio.py install-voxcpm` → env builds, `.voxcpm-ready` written.
  - Start the app, switch to VoxCPM (Download prompts if weights absent), and exercise: Auto, Design (free-text prompt), Clone (pick a voice), Controllable clone (Clone + style), Ultimate clone (set a voice's reference transcript), the Quality Fast/Balanced/High control, and CFG. Confirm 48 kHz audio and that distinct modes don't share cache entries.
  - Verify Delete weights + Uninstall environment for VoxCPM behave like OmniVoice.

- [ ] **Step 4:** Hand off to `superpowers:finishing-a-development-branch`.

---

## Self-review notes (author)

- **Spec coverage:** isolated proxy (T1, T3), five modes (T1 dispatch + T3 message + T14/T15 UI), per-voice transcript (T5, T18), CFG (T16), Quality/timesteps (T17), capability-driven toggle (T2, T6, T7, T13, T14, T15), install/download/delete/uninstall (T9, T10), CUDA/Python guards (T8, T9), 48 kHz + no-streaming (T3), testing mirrors OmniVoice (T1, T3, T7, T10), CLAUDE.md (T21). All spec sections map to a task.
- **Risks:** `generate()` signature (T1 Step 5 verify), weights size (T10 Step 1 verify), Python <3.13 (T9 guard) — each has an explicit verification step.
- **Type consistency:** `reference_text` (request) / `reference_transcript` (voice + API) are used consistently; `_voice_cache_key` new params are keyword-defaulted so existing 4-arg callers are unaffected (T6 Step 3 test). `supports_voice_modes`/`supports_style_clone` names match across backend `info()`, both `EngineInfoModel`s, and the TS `EngineInfo`.
