# Qwen3-TTS CustomVoice Engine — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add `Qwen/Qwen3-TTS-12Hz-1.7B-CustomVoice` as a sixth TTS engine — an isolated-venv worker proxy with 9 built-in voices, an always-available free-text style prompt, 10 languages + Auto, and a full advanced sampling panel (temperature/top_p/top_k/repetition_penalty/seed).

**Architecture:** A `QwenEngine` proxy (mirroring the merged `VoxCPMEngine`) drives `backend/qwen_worker.py` inside `backend/venv-qwen` over newline-JSON; audio passes as temp WAVs. CustomVoice is a Kokoro-style built-in-voice engine (no cloning, no clone/design/auto toggle) with a new `supports_style_prompt` capability and Qwen-only quality params threaded like Chatterbox's `cfg_weight`.

**Tech Stack:** Python 3.9–3.13 (isolated venv), `qwen-tts` (pins `transformers==4.57.3`), FastAPI, React + TS + Vite + Tailwind. Backend tests via `./backend/venv/Scripts/python.exe -m pytest`; frontend via `npm run typecheck` / `npm test` from `frontend/`.

**Spec:** `docs/superpowers/specs/2026-06-30-qwen-customvoice-engine-design.md`

**Conventions (every task):**
- Backend tests use the venv Python: `./backend/venv/Scripts/python.exe -m pytest backend/tests/<file> -v` (system Python has no pytest).
- Frontend from `frontend/`: `npm run typecheck`, `npm test`.
- Commit after each task. Subagents only `git add` / `git commit` — never checkout/switch/reset/merge/push.
- The merged **VoxCPM** files are the templates: `backend/voxcpm_worker.py`, `backend/core/engines/voxcpm_engine.py`, and the VoxCPM lines in every shared file. Read them when a task says "mirror VoxCPM".

**Engine identity:** name `qwen`, display `Qwen3-TTS CustomVoice`, model `Qwen/Qwen3-TTS-12Hz-1.7B-CustomVoice`, venv `backend/venv-qwen`, marker `.qwen-ready`, install subcommand `install-qwen`.

---

## File Structure

**New (backend):** `backend/qwen_worker.py`, `backend/core/engines/qwen_engine.py`, `backend/requirements-qwen.txt`, `backend/tests/test_qwen_worker.py`, `backend/tests/test_qwen_engine.py`.
**Modified (backend):** `core/engines/__init__.py`, `core/engine_manager.py`, `config.py`, `app.py`, `services/synthesize.py`, `api/schemas.py`, `api/engines.py`, `api/health.py`, `scripts/download_models.py`, `services/model_download.py`, `services/model_delete.py`, `services/engine_uninstall.py`, `studio.py`, `tools/envdetect.py`, `tests/test_setup_helpers.py`, `tests/test_synthesize.py`, `tests/test_engines_capabilities.py`, `tests/test_chatterbox_install.py`.
**Modified (frontend):** `types/models.ts`, `lib/engineHints.ts`, `lib/api.ts`, `components/SpeakerRoster.tsx`, `components/TtsEditor.tsx`, `components/ControlPanel.tsx`, `components/EngineSelector.tsx`, `components/DownloadModelDialog.tsx`, `components/DeleteWeightsDialog.tsx`, `App.tsx`, `backend/api/download.py` (export-quality parity).

---

## Task 1: Qwen worker — generate_custom_voice dispatch

**Files:** Create `backend/qwen_worker.py`, `backend/tests/test_qwen_worker.py`, `backend/requirements-qwen.txt`.

The worker is pure-Python, testable with a fake `qwen_tts` model. `_build_generate_kwargs` maps the request to `generate_custom_voice` kwargs.

- [ ] **Step 1: `backend/requirements-qwen.txt`**

```text
qwen-tts
# torch + torchaudio are installed separately by studio.py with a CUDA-matched
# wheel (see _ensure_qwen_env). Do NOT pin torch here.
```

- [ ] **Step 2: Write the failing test** `backend/tests/test_qwen_worker.py`

```python
"""Tests for the Qwen worker's generate_custom_voice dispatch (fake model)."""

import importlib
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT))


def _load_worker():
    import backend.qwen_worker as w
    return importlib.reload(w)


def test_basic_kwargs():
    w = _load_worker()
    k = w._build_generate_kwargs(
        {"text": "hi", "speaker": "Vivian", "language": "English"}
    )
    assert k["text"] == "hi"
    assert k["speaker"] == "Vivian"
    assert k["language"] == "English"
    assert "instruct" not in k
    assert k["max_new_tokens"] > 0  # auto-computed


def test_language_defaults_to_auto():
    w = _load_worker()
    k = w._build_generate_kwargs({"text": "hi", "speaker": "Aiden"})
    assert k["language"] == "Auto"


def test_instruct_passed_when_present():
    w = _load_worker()
    k = w._build_generate_kwargs(
        {"text": "hi", "speaker": "Vivian", "instruct": "Very happy."}
    )
    assert k["instruct"] == "Very happy."


def test_empty_instruct_omitted():
    w = _load_worker()
    k = w._build_generate_kwargs(
        {"text": "hi", "speaker": "Vivian", "instruct": "   "}
    )
    assert "instruct" not in k


def test_quality_kwargs_passed_through_only_when_set():
    w = _load_worker()
    k = w._build_generate_kwargs(
        {"text": "hi", "speaker": "Vivian",
         "temperature": 0.8, "top_p": 0.9, "top_k": 40, "repetition_penalty": 1.1}
    )
    assert k["temperature"] == 0.8
    assert k["top_p"] == 0.9
    assert k["top_k"] == 40
    assert k["repetition_penalty"] == 1.1
    # seed is NOT a generate kwarg (handled via torch.manual_seed in _synth)
    assert "seed" not in k


def test_missing_speaker_raises():
    w = _load_worker()
    try:
        w._build_generate_kwargs({"text": "hi"})
    except ValueError:
        return
    raise AssertionError("expected ValueError when speaker is missing")


def test_max_new_tokens_scales_with_text():
    w = _load_worker()
    short = w._build_generate_kwargs({"text": "hi", "speaker": "Vivian"})["max_new_tokens"]
    long = w._build_generate_kwargs({"text": "x" * 1000, "speaker": "Vivian"})["max_new_tokens"]
    assert long >= short


def test_synth_end_to_end_with_fake_model(tmp_path):
    import numpy as np

    w = _load_worker()
    worker = w._Worker()

    class _FakeModel:
        def generate_custom_voice(self, **kwargs):
            return [np.zeros(24000, dtype=np.float32)], 24000  # 1s @ 24k

    worker._model = _FakeModel()
    out = tmp_path / "o.wav"
    resp = worker._synth({"text": "hi", "speaker": "Vivian", "out_wav": str(out)})
    assert resp["ok"] is True
    assert resp["sample_rate"] == 24000
    assert abs(resp["duration_sec"] - 1.0) < 0.01
    assert out.is_file() and out.stat().st_size > 0
```

- [ ] **Step 3: Run to verify it fails**

Run: `./backend/venv/Scripts/python.exe -m pytest backend/tests/test_qwen_worker.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'backend.qwen_worker'`.

- [ ] **Step 4: Write `backend/qwen_worker.py`** (mirrors `voxcpm_worker.py`'s protocol/fd-redirection/WAV writing; differs in `_build_generate_kwargs`, `_load`, and `_synth`)

```python
#!/usr/bin/env python3
"""Qwen3-TTS CustomVoice worker — runs INSIDE backend/venv-qwen.

Speaks newline-delimited JSON on stdin/stdout. The parent process
(backend/core/engines/qwen_engine.py) drives it. All human-readable logging
goes to STDERR so it never corrupts the stdout protocol.

Protocol (one JSON object per line):
  stdin  {"op":"load","device":"cuda","model_id":"Qwen/Qwen3-TTS-12Hz-1.7B-CustomVoice"}
         {"op":"synth","text":..,"out_wav":<path>,"speaker":<str>,"language":<str>,
          "instruct":<str?>,"temperature":<float?>,"top_p":<float?>,"top_k":<int?>,
          "repetition_penalty":<float?>,"seed":<int?>}
         {"op":"shutdown"}
  stdout {"ok":true}                                            (load)
         {"ok":true,"sample_rate":24000,"duration_sec":..,"inference_ms":..}  (synth)
         {"ok":false,"error":".."}                             (any failure)

CustomVoice picks one of 9 built-in speakers and steers it with an optional
free-text `instruct` string. Quality kwargs are forwarded to the package's
generate_custom_voice (which forwards to HF model.generate). The audio is
written to out_wav (16-bit PCM mono WAV at the model's sample rate).
"""

from __future__ import annotations

import json
import os
import sys
import time
import wave

_OUT = sys.stdout
_DEFAULT_SAMPLE_RATE = 24000


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
    if d == "cuda":
        return "cuda:0"
    return d  # cpu, mps, cuda:N


def _auto_max_new_tokens(text: str) -> int:
    """Generous max_new_tokens from text length so normal segments never
    truncate (12 Hz tokenizer; the app caps text at 5000 chars). Capped."""
    return min(8192, 512 + len(text) * 8)


def _build_generate_kwargs(req: dict) -> dict:
    """Map a synth request to generate_custom_voice(**kwargs).

    speaker (one of 9) + language (default Auto) are required structure; an
    optional free-text instruct steers style; quality kwargs are forwarded
    only when present. `seed` is handled in _synth (torch.manual_seed), not
    here. max_new_tokens is auto-computed.
    """
    text = (req.get("text") or "").strip()
    speaker = req.get("speaker")
    if not text:
        raise ValueError("text must be non-empty")
    if not speaker:
        raise ValueError("speaker (voice) is required for Qwen CustomVoice")
    language = req.get("language") or "Auto"
    instruct = (req.get("instruct") or "").strip()

    kwargs: dict = {"text": text, "language": language, "speaker": speaker}
    if instruct:
        kwargs["instruct"] = instruct
    for key in ("temperature", "top_p", "top_k", "repetition_penalty"):
        if req.get(key) is not None:
            kwargs[key] = req[key]
    kwargs["max_new_tokens"] = _auto_max_new_tokens(text)
    return kwargs


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
        model_id = req.get("model_id") or "Qwen/Qwen3-TTS-12Hz-1.7B-CustomVoice"
        try:
            import torch
            from qwen_tts import Qwen3TTSModel
        except Exception as exc:  # noqa: BLE001
            return {"ok": False, "error": f"import qwen_tts failed: {exc}"}
        try:
            self._model = Qwen3TTSModel.from_pretrained(
                model_id,
                device_map=device,
                dtype=torch.bfloat16,
                attn_implementation="sdpa",  # flash_attention_2 optional, not assumed
            )
        except Exception as exc:  # noqa: BLE001
            return {"ok": False, "error": f"load failed: {exc}"}
        _log(f"[qwen-worker] model loaded on {device}")
        return {"ok": True}

    def _synth(self, req: dict) -> dict:
        if self._model is None:
            return {"ok": False, "error": "model not loaded"}
        out_wav = req.get("out_wav")
        if not out_wav:
            return {"ok": False, "error": "out_wav required"}
        try:
            kwargs = _build_generate_kwargs(req)
        except ValueError as exc:
            return {"ok": False, "error": str(exc)}
        if req.get("seed") is not None:
            try:
                import torch
                torch.manual_seed(int(req["seed"]))
            except Exception:  # noqa: BLE001
                pass
        t0 = time.perf_counter()
        try:
            wavs, sr = self._model.generate_custom_voice(**kwargs)
        except Exception as exc:  # noqa: BLE001
            return {"ok": False, "error": f"generate failed: {exc}"}
        inference_ms = int((time.perf_counter() - t0) * 1000)

        import numpy as np

        arr = wavs[0] if isinstance(wavs, (list, tuple)) else wavs
        if hasattr(arr, "detach"):
            arr = arr.detach().cpu().float().numpy()
        arr = np.asarray(arr, dtype=np.float32).reshape(-1)
        rate = int(sr) if sr else self._sample_rate
        try:
            _write_wav_int16(out_wav, arr, rate)
        except Exception as exc:  # noqa: BLE001
            return {"ok": False, "error": f"write wav failed: {exc}"}
        return {
            "ok": True,
            "sample_rate": rate,
            "duration_sec": float(arr.size) / float(rate),
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

- [ ] **Step 5: Run to verify it passes**

Run: `./backend/venv/Scripts/python.exe -m pytest backend/tests/test_qwen_worker.py -v`
Expected: PASS (8 tests).

> **Implementation note (verify the real API in Task 1):** once `backend/venv-qwen` exists, confirm the live signatures:
> `./backend/venv-qwen/Scripts/python.exe -c "import inspect, qwen_tts; m=qwen_tts.Qwen3TTSModel; print(inspect.signature(m.generate_custom_voice)); print(inspect.signature(m.from_pretrained))"`.
> Confirm (a) the **return is `(wavs, sr)`** and the real `sr` value (assumed 24000), (b) that `temperature/top_p/top_k/repetition_penalty/max_new_tokens` are accepted, (c) whether `seed` is accepted directly (if so, pass it as a kwarg instead of `torch.manual_seed`), and (d) the `from_pretrained` device/dtype/attn args. Update `_build_generate_kwargs`/`_load`/`_synth` + tests to match, then re-run. (Spec Risk #1/#2.)

- [ ] **Step 6: Commit**

```bash
git add backend/qwen_worker.py backend/tests/test_qwen_worker.py backend/requirements-qwen.txt
git commit -m "feat(qwen): worker with generate_custom_voice dispatch"
```

---

## Task 2: Engine quality fields + `supports_style_prompt` capability

**Files:** Modify `backend/core/engines/__init__.py`.

- [ ] **Step 1: Add 5 quality fields to `EngineSynthRequest`.** It currently ends with the VoxCPM `reference_text` field (line 85). Add AFTER it:

```python
    # --- Qwen3-TTS CustomVoice only (other engines ignore) ---
    # HF generation sampling params forwarded to generate_custom_voice.
    temperature: float | None = None
    top_p: float | None = None
    top_k: int | None = None
    repetition_penalty: float | None = None
    seed: int | None = None
```

- [ ] **Step 2: Add the `supports_style_prompt` ABC method.** After `supports_style_clone()` (ends line 156), add:

```python
    def supports_style_prompt(self) -> bool:
        """True if the engine accepts an always-available free-text style
        prompt alongside a built-in voice (Qwen CustomVoice), independent of
        any Clone/Design/Auto toggle. The value rides the `instruct` field."""
        return False
```

- [ ] **Step 3: Surface it in `info()`.** In the `info()` dict, after `"supports_style_clone": self.supports_style_clone(),` (line 227), add:

```python
            "supports_style_prompt": self.supports_style_prompt(),
```

- [ ] **Step 4: Verify**

Run: `./backend/venv/Scripts/python.exe -m pytest backend/tests/test_smoke.py -v`
Expected: PASS (additive; new fields default safely).

- [ ] **Step 5: Commit**

```bash
git add backend/core/engines/__init__.py
git commit -m "feat(engines): Qwen quality fields + supports_style_prompt capability"
```

---

## Task 3: QwenEngine proxy + 9 voices

**Files:** Create `backend/core/engines/qwen_engine.py`, `backend/tests/test_qwen_engine.py`.

- [ ] **Step 1: Write the failing test** `backend/tests/test_qwen_engine.py`

```python
"""QwenEngine proxy tests: capabilities, voices, message building (no subprocess)."""

import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT))

from backend.core.engines import EngineSynthRequest  # noqa: E402
from backend.core.engines.qwen_engine import QwenEngine  # noqa: E402


def _eng():
    return QwenEngine()


def test_capabilities():
    e = _eng()
    assert e.name == "qwen"
    assert e.sample_rate() == 24000
    assert e.max_speakers() == 1
    assert e.supports_voice_cloning() is False
    assert e.supports_voice_modes() is False
    assert e.supports_style_prompt() is True
    assert e.supports_streaming() is False
    assert e.default_cfg_scale() is None


def test_nine_builtin_voices():
    voices = _eng().available_voices()
    ids = {v.id for v in voices}
    assert ids == {
        "Vivian", "Serena", "Uncle_Fu", "Dylan", "Eric",
        "Ryan", "Aiden", "Ono_Anna", "Sohee",
    }
    vivian = next(v for v in voices if v.id == "Vivian")
    assert vivian.source == "builtin"
    assert vivian.gender == "woman"
    assert vivian.language == "zh"
    assert "young female" in vivian.name.lower()


def test_languages_include_auto_first():
    langs = _eng().languages()
    codes = [l["code"] for l in langs]
    assert codes[0] == "Auto"
    assert "Chinese" in codes and "English" in codes
    assert len(codes) == 11  # Auto + 10


def test_build_msg_basic():
    msg = _eng()._build_synth_msg(
        EngineSynthRequest(text="hi", voice_id="Vivian", language_id="English"), "/tmp/o.wav"
    )
    assert msg["speaker"] == "Vivian"
    assert msg["language"] == "English"
    assert msg["text"] == "hi"
    assert "instruct" not in msg


def test_build_msg_language_defaults_auto():
    msg = _eng()._build_synth_msg(
        EngineSynthRequest(text="hi", voice_id="Aiden"), "/tmp/o.wav"
    )
    assert msg["language"] == "Auto"


def test_build_msg_instruct_and_quality():
    msg = _eng()._build_synth_msg(
        EngineSynthRequest(
            text="hi", voice_id="Vivian", instruct="Very happy.",
            temperature=0.8, top_p=0.9, top_k=40, repetition_penalty=1.1, seed=7,
        ),
        "/tmp/o.wav",
    )
    assert msg["instruct"] == "Very happy."
    assert msg["temperature"] == 0.8
    assert msg["top_p"] == 0.9
    assert msg["top_k"] == 40
    assert msg["repetition_penalty"] == 1.1
    assert msg["seed"] == 7


def test_build_msg_requires_speaker():
    try:
        _eng()._build_synth_msg(EngineSynthRequest(text="hi", voice_id=""), "/tmp/o.wav")
    except ValueError:
        return
    raise AssertionError("expected ValueError when no voice/speaker")
```

- [ ] **Step 2: Run to verify it fails**

Run: `./backend/venv/Scripts/python.exe -m pytest backend/tests/test_qwen_engine.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'backend.core.engines.qwen_engine'`.

- [ ] **Step 3: Write `backend/core/engines/qwen_engine.py`**

The lifecycle/`_exchange`/`_start_stderr_drain`/`_recent_stderr`/`_kill`/`load`/`unload`/`is_loaded`/`installed`/`downloaded`/`synthesize` internals are **identical to `backend/core/engines/voxcpm_engine.py`** except: the engine name/marker/worker paths (`qwen`/`.qwen-ready`/`qwen_worker.py`/`venv-qwen`), the `model_id` default, the capability methods, the voice catalog, `languages()`, and `_build_synth_msg`. Copy `voxcpm_engine.py` as the base, then make it read exactly as below:

```python
"""Qwen3-TTS CustomVoice engine — ISOLATED-ENV PROXY.

qwen-tts hard-pins transformers==4.57.3, incompatible with every other engine,
so the model runs in a separate venv (backend/venv-qwen). This class is a thin
proxy that drives backend/qwen_worker.py, keeping the normal Engine surface.

CustomVoice is a built-in-voice engine (9 premium speakers, like Kokoro) with
an always-available free-text style prompt and HF sampling quality params. It
does NOT clone reference audio and has no Clone/Design/Auto modes.
"""

from __future__ import annotations

import collections
import json
import logging
import os
import subprocess
import tempfile
import threading
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from . import Engine, EngineResult, EngineSynthRequest

log = logging.getLogger(__name__)

_BACKEND_ROOT = Path(__file__).resolve().parents[2]  # backend/


@dataclass(frozen=True)
class _QwenVoiceSpec:
    id: str       # the speaker name passed to generate_custom_voice
    name: str     # UI label
    gender: str   # "man" | "woman"
    language: str # native language code


# The 9 premium CustomVoice speakers (from the model card).
_QWEN_VOICES: tuple[_QwenVoiceSpec, ...] = (
    _QwenVoiceSpec("Vivian",   "Vivian — bright young female",   "woman", "zh"),
    _QwenVoiceSpec("Serena",   "Serena — warm gentle female",    "woman", "zh"),
    _QwenVoiceSpec("Uncle_Fu", "Uncle Fu — seasoned mellow male", "man",  "zh"),
    _QwenVoiceSpec("Dylan",    "Dylan — Beijing male",           "man",   "zh"),
    _QwenVoiceSpec("Eric",     "Eric — Chengdu male",            "man",   "zh"),
    _QwenVoiceSpec("Ryan",     "Ryan — dynamic male",            "man",   "en"),
    _QwenVoiceSpec("Aiden",    "Aiden — sunny American male",    "man",   "en"),
    _QwenVoiceSpec("Ono_Anna", "Ono Anna — playful female",      "woman", "ja"),
    _QwenVoiceSpec("Sohee",    "Sohee — warm Korean female",     "woman", "ko"),
)

# CustomVoice languages (the `language` arg). "Auto" first = default.
_QWEN_LANGUAGES: tuple[str, ...] = (
    "Auto", "Chinese", "English", "Japanese", "Korean", "German",
    "French", "Russian", "Portuguese", "Spanish", "Italian",
)


def _default_worker_python() -> Path:
    venv = _BACKEND_ROOT / "venv-qwen"
    if os.name == "nt":
        return venv / "Scripts" / "python.exe"
    return venv / "bin" / "python"


def _default_worker_script() -> Path:
    return _BACKEND_ROOT / "qwen_worker.py"


class QwenEngine(Engine):
    """Proxy to a Qwen3-TTS CustomVoice worker in backend/venv-qwen."""

    name = "qwen"
    display_name = "Qwen3-TTS CustomVoice"
    description = (
        "Alibaba Qwen's 1.7B TTS with 9 premium voices, free-text style "
        "control, and 10 languages. Runs in its own isolated environment. "
        "~3.5 GB weights download on first use."
    )

    def __init__(
        self,
        model_id: str = "Qwen/Qwen3-TTS-12Hz-1.7B-CustomVoice",
        device_request: str = "cuda",
        worker_python: Path | None = None,
        worker_script: Path | None = None,
    ) -> None:
        self._model_id = model_id
        self._device_request = device_request
        self._worker_python = Path(worker_python) if worker_python else _default_worker_python()
        self._worker_script = Path(worker_script) if worker_script else _default_worker_script()
        self._proc: subprocess.Popen | None = None
        self._lock = threading.Lock()
        self._load_lock = threading.Lock()
        self._stderr_tail: collections.deque[str] = collections.deque(maxlen=200)
        self._stderr_thread: threading.Thread | None = None

    # -- lifecycle (identical to VoxCPMEngine, qwen paths)
    def load(self) -> None:
        with self._load_lock:
            if self.is_loaded():
                return
            if not self._worker_python.is_file():
                raise RuntimeError(
                    "Qwen isn't installed in its isolated environment. "
                    "Run `python studio.py install-qwen` (or click Install in the UI)."
                )
            device = self._device_request
            if device == "auto":
                device = "cuda"
            env = dict(os.environ)
            models_dir = _BACKEND_ROOT / "models"
            env["HF_HOME"] = str(models_dir)
            env["HUGGINGFACE_HUB_CACHE"] = str(models_dir / "hub")
            log.info("Spawning Qwen worker: %s %s", self._worker_python, self._worker_script)
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
                raise RuntimeError(f"Qwen worker failed to load: {err}")

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
        return self._worker_python.parent.parent / ".qwen-ready"

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
        return 24000

    def max_speakers(self) -> int:
        return 1

    def supports_voice_cloning(self) -> bool:
        return False

    def supports_streaming(self) -> bool:
        return False

    def supports_style_prompt(self) -> bool:
        return True

    def default_cfg_scale(self) -> float | None:
        return None

    def available_voices(self) -> list:
        from ...services.voices import VoiceInfo

        return [
            VoiceInfo(
                id=v.id, name=v.name, gender=v.gender, language=v.language,
                source="builtin", sample_rate=24000,
            )
            for v in _QWEN_VOICES
        ]

    def languages(self) -> list[dict[str, str]]:
        return [
            {"code": c, "label": ("Auto-detect" if c == "Auto" else c)}
            for c in _QWEN_LANGUAGES
        ]

    # -- synthesis
    def _build_synth_msg(self, req: EngineSynthRequest, out_wav: str) -> dict:
        text = (req.text or "").strip()
        if not text:
            raise ValueError("text must be non-empty")
        speaker = req.voice_id
        if not speaker:
            raise ValueError("Qwen CustomVoice requires a voice (one of the 9 speakers).")
        msg: dict[str, Any] = {
            "op": "synth",
            "text": text,
            "out_wav": out_wav,
            "speaker": speaker,
            "language": req.language_id or "Auto",
        }
        instruct = (req.instruct or "").strip()
        if instruct:
            msg["instruct"] = instruct
        for attr in ("temperature", "top_p", "top_k", "repetition_penalty", "seed"):
            val = getattr(req, attr, None)
            if val is not None:
                msg[attr] = val
        return msg

    def synthesize(self, req: EngineSynthRequest) -> EngineResult:
        if not self.is_loaded():
            raise RuntimeError("Qwen worker is not loaded")
        fd, out_wav = tempfile.mkstemp(suffix=".wav", prefix="qwen-")
        os.close(fd)
        try:
            msg = self._build_synth_msg(req, out_wav)
            resp = self._exchange(msg)
            if not resp.get("ok"):
                raise RuntimeError(f"Qwen synth failed: {resp.get('error', 'unknown error')}")
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

    # -- internals (identical to VoxCPMEngine)
    def _exchange(self, msg: dict, expect_reply: bool = True) -> dict:
        with self._lock:
            if self._proc is None or self._proc.stdin is None or self._proc.stdout is None:
                raise RuntimeError("Qwen worker is not running")
            try:
                self._proc.stdin.write(json.dumps(msg) + "\n")
                self._proc.stdin.flush()
            except (BrokenPipeError, OSError) as exc:
                self._kill()
                raise RuntimeError(f"Qwen worker pipe broke: {exc}") from exc
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
                        "Qwen worker closed unexpectedly" + (f": {stderr}" if stderr else "")
                    )
                stripped = line.strip()
                if not stripped:
                    continue
                try:
                    return json.loads(stripped)
                except json.JSONDecodeError:
                    log.debug("qwen worker non-protocol stdout: %s", stripped[:200])
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

        thread = threading.Thread(target=_drain, args=(proc.stderr, self._stderr_tail), daemon=True)
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

- [ ] **Step 4: Run to verify it passes**

Run: `./backend/venv/Scripts/python.exe -m pytest backend/tests/test_qwen_engine.py -v`
Expected: PASS (7 tests).

- [ ] **Step 5: Commit**

```bash
git add backend/core/engines/qwen_engine.py backend/tests/test_qwen_engine.py
git commit -m "feat(qwen): QwenEngine proxy + 9 built-in voices + languages"
```

---

## Task 4: Register Qwen in config + EngineManager + app

**Files:** `backend/config.py`, `backend/core/engine_manager.py`, `backend/app.py`.

- [ ] **Step 1: `config.py`** — extend the Literal (line 27) and add a setting after the voxcpm block (line 61):

```python
    default_engine: Literal["vibevoice", "kokoro", "chatterbox", "omnivoice", "voxcpm", "qwen"] = "vibevoice"
```
```python
    qwen_model_id: str = "Qwen/Qwen3-TTS-12Hz-1.7B-CustomVoice"
```

- [ ] **Step 2: `core/engine_manager.py`** — import (after the voxcpm import, line 23):

```python
from .engines.qwen_engine import QwenEngine
```
ctor param (after `voxcpm_inference_timesteps: int = 10,`):
```python
        qwen_model_id: str = "Qwen/Qwen3-TTS-12Hz-1.7B-CustomVoice",
```
registry entry (after the `"voxcpm": VoxCPMEngine(...)` block, before the closing `}`):
```python
            "qwen": QwenEngine(
                model_id=qwen_model_id,
                device_request=device_request,
            ),
```

- [ ] **Step 3: `app.py`** — pass the setting in the `EngineManager(...)` call (after `voxcpm_inference_timesteps=settings.voxcpm_inference_timesteps,`):

```python
        qwen_model_id=settings.qwen_model_id,
```

- [ ] **Step 4: Verify the registry**

Run: `./backend/venv/Scripts/python.exe -m pytest backend/tests/test_smoke.py -v`
Then: `./backend/venv/Scripts/python.exe -c "from backend.config import get_settings; from backend.core.engine_manager import EngineManager as M; s=get_settings(); em=M(default_engine='vibevoice', voices_dir=s.voices_dir, uploads_dir=s.uploads_dir, model_id=s.model_id, device_request='cpu'); print([e.name for e in em.list_engines()])"`
Expected: list ending with `'qwen'`.

- [ ] **Step 5: Commit**

```bash
git add backend/config.py backend/core/engine_manager.py backend/app.py
git commit -m "feat(qwen): register engine in config + EngineManager"
```

---

## Task 5: SynthService — thread quality params + style prompt + cache key

**Files:** `backend/api/schemas.py`, `backend/services/synthesize.py`, `backend/tests/test_synthesize.py`.

- [ ] **Step 1: Add quality fields to `SynthRequestBody`** (`api/schemas.py`). After `language_id: str | None = None` (line 138):

```python
    # --- Qwen3-TTS CustomVoice only (other engines ignore) ---
    temperature: float | None = Field(default=None, ge=0.1, le=2.0)
    top_p: float | None = Field(default=None, ge=0.0, le=1.0)
    top_k: int | None = Field(default=None, ge=0, le=200)
    repetition_penalty: float | None = Field(default=None, ge=1.0, le=2.0)
    seed: int | None = Field(default=None, ge=0)
```

- [ ] **Step 2: Write failing cache-key tests** — append to `backend/tests/test_synthesize.py`:

```python
from backend.services.synthesize import _voice_cache_key as _vck_qwen  # noqa: E402


def test_cache_key_folds_qwen_quality():
    base = dict(voice_id="Vivian", voice_mode=None, instruct=None, reference_audio=None)
    a = _vck_qwen(**base)
    b = _vck_qwen(**base, qwen_gen="t0.8|p0.9|k40|r1.1|s7")
    c = _vck_qwen(**base, qwen_gen="t0.5|p0.9|k40|r1.1|s7")
    assert a != b and b != c  # quality signature changes the slot


def test_cache_key_qwen_omitted_when_absent():
    # No qwen_gen → unchanged key (no churn for other engines)
    assert _vck_qwen("Vivian", None, None, None) == "Vivian"
```

- [ ] **Step 3: Extend `_voice_cache_key`** (`services/synthesize.py`). Add a keyword param and fold it. The signature currently ends `..., reference_text: str | None = None, timesteps: int | None = None) -> str:`. Add `qwen_gen: str | None = None,` and, before `return base`, add:

```python
    if qwen_gen:
        base += f"|qg={qwen_gen}"
```

- [ ] **Step 4: Build the Qwen gen signature + thread the fields** in `synthesize()`. After the existing `effective_*` locals in `synthesize()` (where `effective_language_id`/`effective_cfg_weight`/`effective_exaggeration` are computed), add:

```python
        qwen_gen = None
        if target_name == "qwen":
            qwen_gen = "|".join(
                f"{k}={v}" for k, v in (
                    ("t", req.temperature), ("p", req.top_p), ("k", req.top_k),
                    ("r", req.repetition_penalty), ("s", req.seed),
                ) if v is not None
            ) or None
```
Then pass `qwen_gen=qwen_gen` into the `_voice_cache_key(...)` call in `synthesize()` (currently 6 positional args). It becomes:
```python
            cache_voice_key = _voice_cache_key(
                sp0.voice_id, sp0.voice_mode, sp0.instruct, reference_audio,
                reference_transcript, steps_override, qwen_gen=qwen_gen,
            )
```

- [ ] **Step 5: Pass language + quality into BOTH `EngineSynthRequest` constructions.** In the **single-speaker** construction (currently lacks `language_id` and the quality fields), add after `reference_text=reference_transcript,`:

```python
                language_id=effective_language_id,
                temperature=req.temperature,
                top_p=req.top_p,
                top_k=req.top_k,
                repetition_penalty=req.repetition_penalty,
                seed=req.seed,
```
In the **multi-speaker** construction (already has `language_id`), add after `reference_text=reference_transcript,`:
```python
                temperature=req.temperature,
                top_p=req.top_p,
                top_k=req.top_k,
                repetition_penalty=req.repetition_penalty,
                seed=req.seed,
```

> Note: adding `language_id` to the single-speaker path also makes Chatterbox honor a selected language in single-speaker requests (previously only multi-speaker passed it) — a consistent improvement, not a regression (it's `None` unless a language is chosen).

`instruct` is already passed in both constructions (`instruct=sp0.instruct` / `req.speakers[0].instruct`), so the Qwen style prompt flows with no further change — the worker uses it when present.

- [ ] **Step 6: Run the tests**

Run: `./backend/venv/Scripts/python.exe -m pytest backend/tests/test_synthesize.py backend/tests/test_smoke.py -q`
Expected: PASS.

- [ ] **Step 7: Commit**

```bash
git add backend/api/schemas.py backend/services/synthesize.py backend/tests/test_synthesize.py
git commit -m "feat(qwen): thread quality params + style + language through SynthService"
```

---

## Task 6: `supports_style_prompt` through the engines API

**Files:** `backend/api/schemas.py`, `backend/api/engines.py`, `backend/api/health.py`, `backend/tests/test_engines_capabilities.py`.

- [ ] **Step 1: Write the failing test** — append to `backend/tests/test_engines_capabilities.py`:

```python
def test_engines_expose_style_prompt_flag():
    from fastapi.testclient import TestClient
    from backend.app import create_app
    client = TestClient(create_app())
    by_name = {e["name"]: e for e in client.get("/api/engines").json()["engines"]}
    assert by_name["qwen"]["supports_style_prompt"] is True
    assert by_name["vibevoice"]["supports_style_prompt"] is False
    assert by_name["voxcpm"]["supports_style_prompt"] is False
```

- [ ] **Step 2: Run to verify it fails**

Run: `./backend/venv/Scripts/python.exe -m pytest backend/tests/test_engines_capabilities.py -k style_prompt -v`
Expected: FAIL — `KeyError: 'supports_style_prompt'`.

- [ ] **Step 3: `api/schemas.py` `EngineInfoModel`** — after `supports_style_clone: bool = False` (line 98) add:

```python
    supports_style_prompt: bool = False
```

- [ ] **Step 4: `api/engines.py` `EngineInfoModel`** — add the same field to that class, and in `_to_model(info)` after `supports_style_clone=...` add:

```python
        supports_style_prompt=info.get("supports_style_prompt", False),
```

- [ ] **Step 5: `api/health.py` `/config`** — in the `EngineInfoModel(...)` comprehension, after `supports_style_clone=info.get("supports_style_clone", False),` add:

```python
            supports_style_prompt=info.get("supports_style_prompt", False),
```

- [ ] **Step 6: Run to verify it passes**

Run: `./backend/venv/Scripts/python.exe -m pytest backend/tests/test_engines_capabilities.py backend/tests/test_smoke.py -q`
Expected: PASS.

- [ ] **Step 7: Commit**

```bash
git add backend/api/schemas.py backend/api/engines.py backend/api/health.py backend/tests/test_engines_capabilities.py
git commit -m "feat(api): expose supports_style_prompt on engines"
```

---

## Task 7: CUDA-tag detection for Qwen

**Files:** `tools/envdetect.py`, `backend/tests/test_setup_helpers.py`.

- [ ] **Step 1: Write the failing test** — append to `backend/tests/test_setup_helpers.py`:

```python
from tools.envdetect import detect_qwen_cuda_tag, cuda_version_to_qwen_tag


def test_cuda_version_to_qwen_tag():
    assert cuda_version_to_qwen_tag("13.0") == "cu128"
    assert cuda_version_to_qwen_tag("12.8") == "cu128"
    assert cuda_version_to_qwen_tag("12.6") == "cu126"
    assert cuda_version_to_qwen_tag("12.4") is None
    assert cuda_version_to_qwen_tag(None) is None


def test_detect_qwen_cuda_tag_uses_runner():
    assert detect_qwen_cuda_tag(runner=lambda: "CUDA Version: 12.8") == "cu128"
```

- [ ] **Step 2: Run to verify it fails**

Run: `./backend/venv/Scripts/python.exe -m pytest backend/tests/test_setup_helpers.py -k qwen -v`
Expected: FAIL — `ImportError: cannot import name 'detect_qwen_cuda_tag'`.

- [ ] **Step 3: Add to `tools/envdetect.py`** (after `detect_voxcpm_cuda_tag`):

```python
def cuda_version_to_qwen_tag(version: str | None) -> str | None:
    """Map a CUDA runtime version to a torch wheel tag for Qwen3-TTS.

    qwen-tts needs a modern torch (transformers==4.57.3); we install a torch
    2.8 CUDA build (cu126/cu128, same as OmniVoice/VoxCPM). Below 12.6 → CPU.
    """
    return cuda_version_to_omnivoice_tag(version)


def detect_qwen_cuda_tag(runner=None) -> str | None:
    """Detect the torch CUDA wheel tag for Qwen. `runner` is injectable."""
    run = runner or _run_nvidia_smi
    text = run()
    if text is None:
        return None
    return cuda_version_to_qwen_tag(parse_nvidia_smi_cuda_version(text))
```

- [ ] **Step 4: Run to verify it passes**

Run: `./backend/venv/Scripts/python.exe -m pytest backend/tests/test_setup_helpers.py -k qwen -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add tools/envdetect.py backend/tests/test_setup_helpers.py
git commit -m "feat(envdetect): Qwen CUDA wheel-tag detection"
```

---

## Task 8: studio.py install-qwen

**Files:** `studio.py`.

Mirror `_ensure_voxcpm_env` / `cmd_install_voxcpm` / the venv-path + marker helpers exactly, with qwen paths. No special Python-version guard (qwen-tts allows 3.9–3.13; the repo baseline is 3.10+).

- [ ] **Step 1: Add venv-path + marker helpers** (after `voxcpm_ready_marker`):

```python
def qwen_venv_python(repo_root: Path) -> Path:
    """Path to the ISOLATED Qwen venv's Python interpreter."""
    venv = repo_root / "backend" / "venv-qwen"
    if os.name == "nt":
        return venv / "Scripts" / "python.exe"
    return venv / "bin" / "python"


def qwen_ready_marker(repo_root: Path) -> Path:
    """Sentinel written only after a FULL successful Qwen install."""
    return repo_root / "backend" / "venv-qwen" / ".qwen-ready"
```

- [ ] **Step 2: Add `_ensure_qwen_env`** (after `_ensure_voxcpm_env`) — identical structure, qwen paths + `detect_qwen_cuda_tag`:

```python
def _ensure_qwen_env() -> bool:
    """Create backend/venv-qwen and install qwen-tts into it.

    qwen-tts pins transformers==4.57.3 (incompatible with every other engine),
    so it gets its own environment with a CUDA-matched torch + qwen-tts.
    Returns True on success, False on any failure.
    """
    marker = qwen_ready_marker(REPO_ROOT)
    try:
        marker.unlink()
    except OSError:
        pass
    qpy = qwen_venv_python(REPO_ROOT)
    if not qpy.is_file():
        print("  Creating isolated Qwen environment (backend/venv-qwen) …")
        if _run([sys.executable, "-m", "venv", str(BACKEND_DIR / "venv-qwen")]) != 0:
            print("  ERROR: failed to create venv-qwen.")
            return False
    print("  Upgrading pip in the Qwen env …")
    raw_ok = _run([str(qpy), "-m", "pip", "install", "--upgrade", "pip"]) == 0
    progress = ["--progress-bar", "raw"] if raw_ok else []
    net = ["--retries", "10", "--timeout", "120"]
    # 1. Install qwen-tts FIRST (pulls a torch build to satisfy its deps).
    print("  Installing qwen-tts into the Qwen env …")
    if _run([str(qpy), "-m", "pip", "install", *progress, *net, "-r",
             str(BACKEND_DIR / "requirements-qwen.txt")]) != 0:
        print("  ERROR: qwen-tts install failed.")
        return False
    # 2. Swap in the CUDA build of torch+torchaudio for GPU.
    qtag = envdetect.detect_qwen_cuda_tag()
    index = envdetect.torch_index_url(qtag) if qtag else None
    if index:
        print(f"  Installing the CUDA build of torch+torchaudio ({qtag}) for GPU …")
        if _run([str(qpy), "-m", "pip", "install", *progress, *net, "--force-reinstall",
                 "--no-deps", "--index-url", index, "torch", "torchaudio"]) != 0:
            print("  ERROR: CUDA torch install failed.")
            return False
    else:
        print("  No matching torch CUDA build for this driver — leaving the "
              "default (CPU) torch in place. Qwen will run on CPU (slow).")
    try:
        marker.parent.mkdir(parents=True, exist_ok=True)
        marker.write_text("ok\n", encoding="utf-8")
    except OSError as exc:
        print(f"  ERROR: could not write ready marker: {exc}")
        return False
    print("  Qwen environment ready.")
    return True
```

- [ ] **Step 3: Add `cmd_install_qwen`** (after `cmd_install_voxcpm`):

```python
def cmd_install_qwen(_args: argparse.Namespace) -> int:
    """Non-interactive: build/refresh the isolated Qwen env. Used by the
    backend's in-UI installer. Returns 0 on success, 1 on failure."""
    print(BANNER)
    ok = _ensure_qwen_env()
    return 0 if ok else 1
```

- [ ] **Step 4: Register subcommand + dispatch** in `main()`. After `sub.add_parser("install-voxcpm", ...)`:

```python
    sub.add_parser("install-qwen", help="build the isolated Qwen env (non-interactive)")
```
After the `install-voxcpm` dispatch block:
```python
    if args.command == "install-qwen":
        return cmd_install_qwen(args)
```

- [ ] **Step 5: Verify the CLI registers** (no venv build)

Run: `python studio.py --help` (system python, repo root) — confirm `install-qwen` is listed. Do NOT run `python studio.py install-qwen`.

- [ ] **Step 6: Commit**

```bash
git add studio.py
git commit -m "feat(studio): install-qwen isolated env builder"
```

---

## Task 9: Download / delete / uninstall lifecycle registration

**Files:** `backend/scripts/download_models.py`, `backend/services/model_download.py`, `backend/services/model_delete.py`, `backend/services/engine_uninstall.py`, `backend/app.py`, `backend/tests/test_chatterbox_install.py`, `backend/tests/test_setup_helpers.py`.

- [ ] **Step 1: Add the catalog entry** (`scripts/download_models.py`, after the `"voxcpm"` entry):

```python
    "qwen": {
        "repo_id": "Qwen/Qwen3-TTS-12Hz-1.7B-CustomVoice",
        "size": "~3.5 GB",
        "label": "Qwen3-TTS CustomVoice",
    },
```

> Confirm the real size at impl: `./backend/venv/Scripts/python.exe -c "from huggingface_hub import HfApi; i=HfApi().model_info('Qwen/Qwen3-TTS-12Hz-1.7B-CustomVoice', files_metadata=True); print(sum((s.size or (s.lfs.size if s.lfs else 0) or 0) for s in i.siblings)/1e9, 'GB')"`. Update the size string + the frontend MODEL_SIZES (Task 19) if materially different.

- [ ] **Step 2: Add `qwen` to the three frozensets:**

`model_download.py`: `DOWNLOADABLE = frozenset({"vibevoice", "kokoro", "omnivoice", "voxcpm", "qwen"})`
`model_delete.py`: `DELETABLE = frozenset({"vibevoice", "kokoro", "omnivoice", "chatterbox", "voxcpm", "qwen"})`
`engine_uninstall.py`: `UNINSTALLABLE = frozenset({"chatterbox", "omnivoice", "voxcpm", "qwen"})`

- [ ] **Step 3: Wire installer + uninstaller in `app.py`:**

In `engine_installers`: `"qwen": EngineEnvInstaller("install-qwen"),`
In `engine_uninstallers`: `"qwen": EngineEnvUninstaller("qwen", em=engine_manager),`

- [ ] **Step 4: Update the catalog-membership test.** In `backend/tests/test_setup_helpers.py`, `test_catalog_has_expected_engines` asserts the exact `MODEL_CATALOG` set — add `"qwen"`:

```python
    assert set(dm.MODEL_CATALOG) == {"vibevoice", "kokoro", "chatterbox", "omnivoice", "voxcpm", "qwen"}
```

- [ ] **Step 5: Add an install-endpoint test** — append to `backend/tests/test_chatterbox_install.py`:

```python
def test_install_endpoint_supports_qwen():
    q = EngineEnvInstaller("install-qwen", runner=_fake_runner(["hi"], 0))
    from fastapi import FastAPI
    from fastapi.testclient import TestClient
    from backend.api.engines import router
    app = FastAPI()
    app.include_router(router)
    app.state.engine_installers = {"qwen": q}
    client = TestClient(app)
    assert client.get("/api/engines/qwen/install").json()["state"] == "not_installed"
    assert client.post("/api/engines/qwen/install").status_code == 200
    _wait(q)
    assert "hi" in client.get("/api/engines/qwen/install").json()["log"]
```

- [ ] **Step 6: Run the lifecycle + setup tests**

Run: `./backend/venv/Scripts/python.exe -m pytest backend/tests/test_chatterbox_install.py backend/tests/test_engine_uninstall.py backend/tests/test_setup_helpers.py -q`
Expected: PASS.

- [ ] **Step 7: Commit**

```bash
git add backend/scripts/download_models.py backend/services/model_download.py backend/services/model_delete.py backend/services/engine_uninstall.py backend/app.py backend/tests/test_chatterbox_install.py backend/tests/test_setup_helpers.py
git commit -m "feat(qwen): wire download/delete/uninstall lifecycle"
```

---

## Task 10: Full backend suite gate

- [ ] **Step 1:** Run `./backend/venv/Scripts/python.exe -m pytest backend/tests/ -q`. Expected: 0 failures. Fix any test that asserts an exact engine count / frozenset membership to include `qwen`.
- [ ] **Step 2:** Commit any fixes: `git commit -am "test(qwen): update suite expectations for the new engine"`.

---

## Task 11: Frontend types

**Files:** `frontend/src/types/models.ts`.

- [ ] **Step 1: Add the capability flag** to `EngineInfo` (after `supports_style_clone: boolean;`):

```typescript
  supports_style_prompt: boolean;
```

- [ ] **Step 2: Typecheck** (from `frontend/`): `npm run typecheck`. Fix any `EngineInfo` literal in tests/mocks to include `supports_style_prompt: false` (there are typically none in `frontend/src`).

- [ ] **Step 3: Commit**

```bash
git add frontend/src/types/models.ts frontend/src
git commit -m "feat(frontend): EngineInfo.supports_style_prompt type"
```

---

## Task 12: SpeakerRoster + TtsEditor — always-available style field

**Files:** `frontend/src/components/SpeakerRoster.tsx`, `frontend/src/components/TtsEditor.tsx`.

Both already render an optional style/`voiceDesign` field for VoxCPM's controllable-clone (gated on `supportsStyleClone`). Add a parallel `supportsStylePrompt` path that shows the field **unconditionally** (no mode toggle, no voice picker gating — Qwen always has a built-in voice + optional style).

- [ ] **Step 1: SpeakerRoster Props** — add after `supportsStyleClone: boolean;`:

```typescript
  supportsStylePrompt: boolean;
```
Thread it through `SpeakerRoster` → each `<SpeakerRow>` → `SpeakerRow`'s params + inline prop-type object (same as `supportsStyleClone`).

- [ ] **Step 2: SpeakerRow render — Qwen branch.** Near the top of `SpeakerRow`'s return logic, BEFORE the `if (!showModes) { ... }` early return, add a branch: when `supportsStylePrompt` (and not a voice-mode engine), render the voice picker + an always-shown style field:

```tsx
  if (supportsStylePrompt) {
    return (
      <div className={`p-3 rounded-lg border ${panelBg} ${panelBorder}`}>
        {nameHeader}
        <div className="space-y-1.5">
          {voiceSelect}
          <input
            type="text"
            value={speaker.voiceDesign ?? ""}
            onChange={(e) => onUpdate({ voiceDesign: e.target.value })}
            placeholder="Style (optional) — e.g. cheerful, slightly faster, whispering"
            className={`w-full border rounded-md px-2 py-1.5 text-xs focus:outline-none focus:border-orange-500 ${selectBg} ${selectBorder} ${selectText}`}
          />
        </div>
      </div>
    );
  }
```
(`voiceDesign` is the existing per-speaker field that already maps to `instruct` in App.tsx; `nameHeader`/`voiceSelect`/`selectBg`/etc. already exist in `SpeakerRow`.)

- [ ] **Step 3: TtsEditor Props + render.** Add `supportsStylePrompt: boolean;` to Props, destructure it. Add a branch (before the `supportsVoiceModes` block) that, when `supportsStylePrompt`, shows an always-on style input bound to `voiceDesign`/`onVoiceDesignChange`:

```tsx
      {supportsStylePrompt && (
        <div className={`rounded-xl border p-3 ${isDark ? "border-zinc-800 bg-zinc-900/50" : "border-gray-200 bg-gray-50"}`}>
          <input
            type="text"
            value={voiceDesign}
            onChange={(e) => onVoiceDesignChange(e.target.value)}
            placeholder="Style (optional) — e.g. cheerful, slightly faster, whispering"
            className={`w-full border rounded-md px-2 py-1.5 text-sm focus:outline-none focus:border-orange-500 ${selectBg}`}
          />
        </div>
      )}
```
Also ensure `showVoiceNote` still shows the active voice for Qwen (since Qwen always uses a built-in voice): it currently reads `!supportsVoiceModes || omniMode === "clone"`, which is `true` for Qwen (supportsVoiceModes false) — correct, the "Voice: X" note shows.

- [ ] **Step 4: Typecheck** (from `frontend/`): `npm run typecheck`. (Callers wired in Task 13.)

- [ ] **Step 5: Commit**

```bash
git add frontend/src/components/SpeakerRoster.tsx frontend/src/components/TtsEditor.tsx
git commit -m "feat(frontend): always-available style field for supports_style_prompt engines"
```

---

## Task 13: App.tsx — derive capability, quality state, thread to UI + synth

**Files:** `frontend/src/App.tsx`, `frontend/src/lib/api.ts`.

- [ ] **Step 1: `lib/api.ts` — add quality options to `synthesizeWav`.** In the `options` type add:

```typescript
    temperature?: number | null;
    topP?: number | null;
    topK?: number | null;
    repetitionPenalty?: number | null;
    seed?: number | null;
```
And in the JSON body builder (alongside the other optional spreads):
```typescript
      ...(options.temperature != null ? { temperature: options.temperature } : {}),
      ...(options.topP != null ? { top_p: options.topP } : {}),
      ...(options.topK != null ? { top_k: options.topK } : {}),
      ...(options.repetitionPenalty != null ? { repetition_penalty: options.repetitionPenalty } : {}),
      ...(options.seed != null ? { seed: options.seed } : {}),
```

- [ ] **Step 2: App.tsx — derive `supportsStylePrompt`.** Near the existing `const supportsVoiceModes = activeEngineInfo?.supports_voice_modes ?? false;` add:

```typescript
const supportsStylePrompt = activeEngineInfo?.supports_style_prompt ?? false;
```

- [ ] **Step 3: App.tsx — Qwen advanced-params state.** Add module-scope defaults near `QUALITY_TIMESTEPS`:

```typescript
const QWEN_DEFAULTS = { temperature: 0.9, topP: 0.9, topK: 50, repetitionPenalty: 1.1, seed: null as number | null };
type QwenParams = typeof QWEN_DEFAULTS;
```
And component state (validating localStorage, mirroring the `quality` pattern):
```typescript
const [qwenParams, setQwenParams] = useState<QwenParams>(() => {
  try {
    const raw = localStorage.getItem("vs.qwen.params");
    if (raw) return { ...QWEN_DEFAULTS, ...JSON.parse(raw) };
  } catch { /* ignore */ }
  return QWEN_DEFAULTS;
});
const onQwenParamsChange = (p: QwenParams) => {
  setQwenParams(p);
  localStorage.setItem("vs.qwen.params", JSON.stringify(p));
};
```

- [ ] **Step 4: App.tsx — a stable gen-signature helper** (for the frontend cache + the synth options). Near the top of the component:

```typescript
const qwenGenSig =
  activeEngine === "qwen"
    ? `t${qwenParams.temperature}|p${qwenParams.topP}|k${qwenParams.topK}|r${qwenParams.repetitionPenalty}|s${qwenParams.seed ?? ""}`
    : undefined;
const qwenSynthOpts =
  activeEngine === "qwen"
    ? {
        temperature: qwenParams.temperature,
        topP: qwenParams.topP,
        topK: qwenParams.topK,
        repetitionPenalty: qwenParams.repetitionPenalty,
        seed: qwenParams.seed,
      }
    : {};
```

- [ ] **Step 5: App.tsx — pass quality into BOTH `synthesizeWav` calls.** At each call site (the segment generate ~L274 and the TTS generate), add `...qwenSynthOpts,` to the options object (alongside the existing `...(activeEngine === "voxcpm" ? { inferenceSteps } : {})`). Add `qwenParams` to those `useCallback` dependency arrays.

- [ ] **Step 6: App.tsx — pass props to `<SpeakerRoster>` and `<TtsEditor>`.** Add `supportsStylePrompt={supportsStylePrompt}` to both. (SpeakerRoster/TtsEditor consume it from Task 12.)

- [ ] **Step 7: Typecheck** (from `frontend/`): `npm run typecheck`. Expected: PASS (ControlPanel advanced panel wired in Task 14; the panel props are added there).

- [ ] **Step 8: Commit**

```bash
git add frontend/src/App.tsx frontend/src/lib/api.ts
git commit -m "feat(frontend): Qwen advanced-params state + style-prompt wiring + synth threading"
```

---

## Task 14: ControlPanel — Qwen "Advanced generation" panel

**Files:** `frontend/src/components/ControlPanel.tsx`, `frontend/src/App.tsx`.

- [ ] **Step 1: ControlPanel Props** — add:

```typescript
  qwenParams?: { temperature: number; topP: number; topK: number; repetitionPenalty: number; seed: number | null };
  onQwenParamsChange?: (p: { temperature: number; topP: number; topK: number; repetitionPenalty: number; seed: number | null }) => void;
  qwenDefaults?: { temperature: number; topP: number; topK: number; repetitionPenalty: number; seed: number | null };
```

- [ ] **Step 2: Render the panel** (Qwen-only), near the existing VoxCPM Quality block. Match the file's Tailwind/dark-mode conventions and reuse `focusRing`:

```tsx
{activeEngine === "qwen" && qwenParams && onQwenParamsChange && (
  <div className="space-y-2 mt-4">
    <div className={`text-xs font-medium ${isDark ? "text-zinc-300" : "text-gray-700"}`}>
      Advanced generation
    </div>
    {([
      { key: "temperature", label: "Temperature", min: 0.1, max: 2.0, step: 0.05 },
      { key: "topP", label: "Top-p", min: 0.0, max: 1.0, step: 0.05 },
      { key: "topK", label: "Top-k", min: 0, max: 200, step: 1 },
      { key: "repetitionPenalty", label: "Repetition penalty", min: 1.0, max: 2.0, step: 0.05 },
    ] as const).map((f) => (
      <label key={f.key} className={`block text-[11px] ${isDark ? "text-zinc-400" : "text-gray-600"}`}>
        <span className="flex justify-between"><span>{f.label}</span><span>{qwenParams[f.key]}</span></span>
        <input
          type="range" min={f.min} max={f.max} step={f.step}
          value={qwenParams[f.key]}
          onChange={(e) => onQwenParamsChange({ ...qwenParams, [f.key]: Number(e.target.value) })}
          className="w-full accent-orange-600"
        />
      </label>
    ))}
    <label className={`block text-[11px] ${isDark ? "text-zinc-400" : "text-gray-600"}`}>
      Seed (optional)
      <input
        type="number"
        value={qwenParams.seed ?? ""}
        onChange={(e) => onQwenParamsChange({ ...qwenParams, seed: e.target.value === "" ? null : Number(e.target.value) })}
        placeholder="random"
        className={`mt-1 w-full border rounded-md px-2 py-1 text-xs focus:outline-none focus:border-orange-500 ${
          isDark ? "bg-zinc-800 border-zinc-700 text-white" : "bg-white border-gray-300 text-gray-900"
        }`}
      />
    </label>
    {qwenDefaults && (
      <button
        type="button"
        onClick={() => onQwenParamsChange(qwenDefaults)}
        className={`text-[11px] underline ${isDark ? "text-zinc-400 hover:text-orange-400" : "text-gray-600 hover:text-orange-600"} ${focusRing}`}
      >
        Reset to defaults
      </button>
    )}
  </div>
)}
```

- [ ] **Step 3: App.tsx — pass the panel props to `<ControlPanel>`:**

```tsx
              qwenParams={qwenParams}
              onQwenParamsChange={onQwenParamsChange}
              qwenDefaults={QWEN_DEFAULTS}
```

- [ ] **Step 4: Typecheck** (from `frontend/`): `npm run typecheck`. Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add frontend/src/components/ControlPanel.tsx frontend/src/App.tsx
git commit -m "feat(frontend): Qwen Advanced generation panel (sampling params + seed + reset)"
```

---

## Task 15: CFG hints for Qwen

**Files:** `frontend/src/lib/engineHints.ts`.

- [ ] **Step 1: Add a `QWEN_HINTS` entry** (after `VOXCPM_HINTS`) — Qwen has no CFG, so the slider is a no-op (mirror `KOKORO_HINTS`/`OMNIVOICE_HINTS`):

```typescript
const QWEN_HINTS: EngineCfgHints = {
  ...VIBEVOICE_HINTS,
  name: "qwen",
  hint:
    "Qwen CustomVoice doesn't use CFG — this slider is a no-op. Tune output via the Advanced generation panel (temperature / top-p / top-k / repetition penalty).",
};
```

- [ ] **Step 2: Register** in `HINTS_BY_ENGINE`: `qwen: QWEN_HINTS,`

- [ ] **Step 3: Typecheck + commit**

```bash
cd frontend && npm run typecheck && cd ..
git add frontend/src/lib/engineHints.ts
git commit -m "feat(frontend): Qwen CFG hints (slider no-op; points to Advanced panel)"
```

---

## Task 16: Frontend cache — fold Qwen gen-signature into isSegmentCached

**Files:** `frontend/src/App.tsx`, `frontend/src/types/models.ts`.

The frontend `isSegmentCached` must re-synth when Qwen advanced params change (the backend cache key already folds them via `qwen_gen`). Add a generic gen-signature alongside the existing VoxCPM `quality` fold.

- [ ] **Step 1: `types/models.ts` `CachedAudio`** — add (next to `quality?`):

```typescript
  // Engine-specific generation signature (Qwen advanced params) — re-synth
  // when it changes. Undefined for engines that don't use it.
  genSig?: string;
```

- [ ] **Step 2: App.tsx — store `genSig` on cache write.** Wherever a `CachedAudio` entry is written (the `generateFor` and `generateTts` cache writes that already set `quality`), add:

```typescript
        genSig: qwenGenSig,
```

- [ ] **Step 3: App.tsx — fold it into `isSegmentCached`.** Add a parameter `effectiveGenSig: string | undefined` (after `effectiveQuality`), and in EVERY return branch add `&& entry.genSig === effectiveGenSig` to the `cached` boolean and `::${effectiveGenSig ?? ""}` to the `signature`. At every `isSegmentCached(...)` call site, pass `qwenGenSig` as the new argument. Add `qwenGenSig` (or `qwenParams`/`activeEngine`) to the relevant `useMemo`/`useCallback` dependency arrays.

- [ ] **Step 4: Typecheck** (from `frontend/`): `npm run typecheck`. Expected: PASS. Parity: for non-Qwen engines `qwenGenSig` is `undefined` on both write and compare → no behavior change.

- [ ] **Step 5: Commit**

```bash
git add frontend/src/App.tsx frontend/src/types/models.ts
git commit -m "fix(frontend): fold Qwen gen-signature into segment cache"
```

---

## Task 17: Export path honors Qwen params

**Files:** `backend/api/download.py`, `frontend/src/lib/api.ts`, `frontend/src/App.tsx`.

Mirror how the export path already carries `inference_steps` for VoxCPM (added in the VoxCPM work).

- [ ] **Step 1: `backend/api/download.py` `DownloadSegment`** — add the 5 quality fields (`temperature: float | None = None`, etc., same as VoxCPM's `inference_steps`). Pass them into the per-segment `SynthRequest`. Fold them into `_join_canonical`'s per-segment dict (e.g. `"q": [s.temperature, s.top_p, s.top_k, s.repetition_penalty, s.seed]`) so different params → different join-cache slot.
- [ ] **Step 2: `frontend/src/lib/api.ts` `DownloadSegmentPayload`** — add `temperature?: number; top_p?: number; top_k?: number; repetition_penalty?: number; seed?: number;`.
- [ ] **Step 3: `frontend/src/App.tsx`** — at the `downloadPodcast(...)` payload builder, add the Qwen params (gated on `activeEngine === "qwen"`, using `qwenParams`), mirroring the `inference_steps` voxcpm gating.
- [ ] **Step 4:** Run `./backend/venv/Scripts/python.exe -m pytest backend/tests/ -q` and (from `frontend/`) `npm run typecheck`. Update any `_join_canonical` test that asserts exact output. Expected: green.
- [ ] **Step 5: Commit**

```bash
git add backend/api/download.py frontend/src/lib/api.ts frontend/src/App.tsx
git commit -m "feat(qwen): export path honors Qwen sampling params"
```

---

## Task 18: Engine selector + dialog gating + sizes

**Files:** `frontend/src/components/EngineSelector.tsx`, `frontend/src/components/DownloadModelDialog.tsx`, `frontend/src/components/DeleteWeightsDialog.tsx`.

- [ ] **Step 1: EngineSelector** — add `|| e.name === "qwen"` to BOTH uninstall-gating conditions (the secondary-actions row guard + the Uninstall button), so they read `(... || e.name === "voxcpm" || e.name === "qwen")`.
- [ ] **Step 2: DeleteWeightsDialog `MODEL_SIZES`** — add `qwen: "~3.5 GB",`.
- [ ] **Step 3: DownloadModelDialog `MODEL_SIZES`** — add `qwen: "~3.5 GB",`.
- [ ] **Step 4: Typecheck + commit**

```bash
cd frontend && npm run typecheck && cd ..
git add frontend/src/components/EngineSelector.tsx frontend/src/components/DownloadModelDialog.tsx frontend/src/components/DeleteWeightsDialog.tsx
git commit -m "feat(frontend): Qwen gating in engine selector + dialog size labels"
```

---

## Task 19: Frontend test pass + build

- [ ] **Step 1:** From `frontend/`: `npm test`. Expected: PASS. Update any mock constructing an `EngineInfo` to include `supports_style_prompt: false`, or a `CachedAudio` to include the new optional fields (optional fields → usually no change needed).
- [ ] **Step 2:** From `frontend/`: `npm run build`. Expected: clean.
- [ ] **Step 3:** Commit any fixes: `git add frontend/src && git commit -m "test(frontend): mocks for Qwen capability + cache fields"`.

---

## Task 20: Docs — update CLAUDE.md + README

**Files:** `CLAUDE.md`. (README is on a separate PR; if merged, also add Qwen there.)

- [ ] **Step 1: CLAUDE.md** — add Qwen3-TTS CustomVoice to the engine list and the isolated-engines paragraph (own venv `backend/venv-qwen`, `requirements-qwen.txt`, `qwen_worker.py`, `transformers==4.57.3` pin, `install-qwen`, cu126/cu128 via `detect_qwen_cuda_tag`). Note: built-in-voice engine (9 voices, Kokoro-style), new `supports_style_prompt` capability (always-available style field gated in SpeakerRoster + TtsEditor), 10 languages + Auto via `language_id`, the Qwen-only Advanced generation panel (temperature/top_p/top_k/repetition_penalty/seed) folded into the cache key, and that it's downloadable.
- [ ] **Step 2: Commit**

```bash
git add CLAUDE.md
git commit -m "docs: document Qwen3-TTS CustomVoice engine in CLAUDE.md"
```

---

## Task 21: Final holistic review + manual verification handoff

- [ ] **Step 1:** Full suites green — `./backend/venv/Scripts/python.exe -m pytest backend/tests/ -q` and (from `frontend/`) `npm test` + `npm run build`.
- [ ] **Step 2:** Dispatch a final holistic reviewer over `git diff main...feat/qwen-tts-engine`, focused on the integration seams: the 5-field quality flow (frontend panel → api.ts → SynthRequestBody → SynthService both paths → EngineSynthRequest → QwenEngine._build_synth_msg → worker generate_custom_voice); `supports_style_prompt` consistency across `/api/engines` + `/api/config` + SpeakerRoster + TtsEditor; the `genSig` cache fold (frontend) vs `qwen_gen` (backend) agreement (no false cache hits when a param changes); the single-speaker `language_id` addition not regressing other engines; lifecycle completeness. Address findings.
- [ ] **Step 3 (manual, GPU + install — NOT in CI):** `python studio.py install-qwen` → env builds, `.qwen-ready` written. Switch to Qwen (Download if absent), pick each of the 9 voices, exercise the style field, the 10 languages + Auto, and the Advanced panel (temperature/top_p/top_k/repetition_penalty/seed + reset); confirm 24 kHz audio and that changing any quality param re-synthesizes (no stale cache). Verify Delete weights + Uninstall behave like VoxCPM. Confirm the real `generate_custom_voice` signature + sample rate matched Task 1's assumptions.
- [ ] **Step 4:** Hand off to `superpowers:finishing-a-development-branch`.

---

## Self-review notes (author)

- **Spec coverage:** isolated proxy (T1, T3); 9 built-in voices Kokoro-style (T3); `supports_style_prompt` + always-on style field (T2, T6, T12, T13); 10 languages + Auto via `language_id` (T3, T5); full quality panel folded into cache (T5, T13, T14, T16); CFG no-op (T15); install/download/delete/uninstall (T8, T9); CUDA tag (T7); 24 kHz + no streaming + no cloning + no voice modes (T3); export parity (T17); testing mirrors VoxCPM (T1/T3/T6/T9 + cache T5/T16); docs (T20). All spec sections map to a task.
- **Risks:** `generate_custom_voice` signature + sr + seed (T1 Step 5 verify), weights size (T9 Step 1 verify), `sox`/flash-attn (T8 + manual T21).
- **Type consistency:** quality field names are consistent backend (`temperature/top_p/top_k/repetition_penalty/seed`) ↔ API body (snake_case) ↔ frontend options (`temperature/topP/topK/repetitionPenalty/seed` → mapped to snake_case in api.ts). `supports_style_prompt` consistent across ABC `info()`, both `EngineInfoModel`s, `/config`, and TS `EngineInfo`. `qwenGenSig`/`genSig` (frontend) ↔ `qwen_gen`/`|qg=` (backend) are independent but both fold the same params.
