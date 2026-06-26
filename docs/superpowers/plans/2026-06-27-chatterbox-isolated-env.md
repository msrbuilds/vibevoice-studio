# Chatterbox Isolated Environment Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Run the Chatterbox TTS engine in its own `backend/venv-chatterbox` (transformers 5.x) via a persistent stdio worker subprocess, behind an unchanged `Engine` proxy, so it can no longer break VibeVoice's pinned `transformers==4.51.3`.

**Architecture:** The in-process `ChatterboxEngine` becomes a thin proxy implementing the same `Engine` ABC. It spawns a standalone worker script (`backend/chatterbox_worker.py`) using a separate venv's Python, exchanges newline-delimited JSON over stdin/stdout, and passes audio as filesystem paths (reference clip in, generated WAV out via a temp file). `studio.py` builds/installs that venv only when the user opts into Chatterbox.

**Tech Stack:** Python stdlib (`subprocess`, `json`, `wave`, `tempfile`, `threading`), `chatterbox-tts` (isolated venv only), `numpy`, pytest.

---

## Context for the implementer

- **Repo root** `f:\Vibe Projects\vibe-podcast`. Python package is `backend`, run as `python -m backend.cli`.
- **venv Python (main):** `backend\venv\Scripts\python.exe`. Run tests from the repo root:
  `backend\venv\Scripts\python.exe -m pytest backend/tests/<file>.py -v`
- **DO NOT install `chatterbox-tts` into the main venv** — it pulls `transformers==5.2.0` and breaks VibeVoice. All tests in this plan run with the main venv and must NOT require `chatterbox-tts`; they use a **stub worker** instead.
- The `Engine` ABC lives in `backend/core/engines/__init__.py`. Relevant types: `EngineSynthRequest` (fields incl. `text`, `voice_id`, `reference_audio`, `cfg_weight`, `exaggeration`, `language_id`) and `EngineResult` (`wav_bytes`, `sample_rate`, `duration_sec`, `inference_ms`, `is_final=False`).
- `backend/tests/test_setup_helpers.py` already exists; it inserts the repo root into `sys.path` (`parents[2]`), so `import studio` and `from backend... import` both resolve. New test files must do the same `sys.path` insert (copy the 2-line pattern from the top of that file).
- The **current** `ChatterboxEngine` (`backend/core/engines/chatterbox_engine.py`) is an in-process model wrapper. Keep its public surface identical: class attrs `name="chatterbox"`, `display_name`, `description`; methods `load/unload/is_loaded/synthesize/sample_rate()->24000/max_speakers()->1/supports_voice_cloning()->True/supports_streaming()->False/default_cfg_scale()/available_voices()->[]/engine_info()`. Keep `SUPPORTED_LANGUAGE_IDS` and `_normalize_language_id` in the module.
- `EngineManager` constructs it in `backend/core/engine_manager.py` as `ChatterboxEngine(model_id=..., default_language_id=..., default_cfg_weight=..., default_exaggeration=..., watermark=..., device_request=...)`. **This call must keep working unchanged.**
- `studio.py` is stdlib-only and imports `from tools import envdetect`. It already has `venv_python(repo_root)`, `build_backend_cmd`, `_run`, `_npm`, `_interactive_model_picker(py)`, `_confirm`, `cmd_setup`, `cmd_models`. The model picker shells `backend.scripts.download_models --models <keys>`.

## File Structure

| Path | Responsibility |
|------|----------------|
| `backend/chatterbox_worker.py` | New — standalone stdio worker (stdlib + chatterbox + numpy + wave). Runs in venv-chatterbox. |
| `backend/core/engines/chatterbox_engine.py` | Rewritten — proxy over the worker subprocess; same Engine surface. |
| `backend/requirements-chatterbox.txt` | New — `chatterbox-tts` isolated. |
| `backend/requirements.txt` | Modify — remove `chatterbox-tts`, add pointer comment. |
| `studio.py` | Modify — `chatterbox_venv_python()` + build/install venv-chatterbox when Chatterbox is picked. |
| `backend/tests/test_chatterbox_proxy.py` | New — stub-worker plumbing + missing-venv tests. |
| `backend/tests/test_setup_helpers.py` | Modify — `chatterbox_venv_python()` path-shape test. |
| `README.md`, `CLAUDE.md` | Modify — document the isolated-env install + architecture. |

---

## Task 1: Isolate the Chatterbox requirement

**Files:**
- Create: `backend/requirements-chatterbox.txt`
- Modify: `backend/requirements.txt`

- [ ] **Step 1: Create `backend/requirements-chatterbox.txt`**

```
# Chatterbox Multilingual V3 — ISOLATED ENVIRONMENT ONLY.
#
# Chatterbox hard-pins transformers==5.2.0, which is INCOMPATIBLE with the
# `vibevoice` package (transformers==4.51.3) in the main backend venv.
# These deps therefore install into a SEPARATE venv (backend/venv-chatterbox)
# and are driven by backend/chatterbox_worker.py as a subprocess.
#
# Install with:  python studio.py models   (select Chatterbox)
#
# Install PyTorch FIRST with a CUDA-matched wheel into this venv, same as the
# main backend (studio.py does this automatically). Then:
#   pip install -r backend/requirements-chatterbox.txt
chatterbox-tts>=0.1.7
```

- [ ] **Step 2: Remove `chatterbox-tts` from `backend/requirements.txt`**

In `backend/requirements.txt`, replace the existing Chatterbox block:

```
# Chatterbox Multilingual V3 TTS engine (Resemble AI, 0.5B params,
# 23+ languages, voice cloning, MIT licensed). ~500 MB on first run.
# Models: https://huggingface.co/ResembleAI/chatterbox
# If pip fails on Windows, use `pip install --user chatterbox-tts` to
# bypass the Scripts/ launcher race condition.
chatterbox-tts>=0.1.3
```

with this comment-only block (no install line):

```
# Chatterbox Multilingual V3 is NOT installed here. It hard-pins
# transformers==5.2.0, which conflicts with vibevoice's transformers==4.51.3.
# It installs into a separate environment (backend/venv-chatterbox) and runs
# as a subprocess worker. Install it with:  python studio.py models
# (select Chatterbox). See backend/requirements-chatterbox.txt.
```

- [ ] **Step 3: Verify the main requirements no longer reference the package as an install**

Run: `cd "f:/Vibe Projects/vibe-podcast" && grep -nE '^chatterbox-tts' backend/requirements.txt; echo "exit=$?"`
Expected: no matching line (grep prints nothing, `exit=1`).

- [ ] **Step 4: Commit**

```bash
git add backend/requirements.txt backend/requirements-chatterbox.txt
git commit -m "build: isolate chatterbox-tts into its own requirements file"
```

---

## Task 2: The standalone worker (`backend/chatterbox_worker.py`)

**Files:**
- Create: `backend/chatterbox_worker.py`

This script runs in venv-chatterbox and is NOT imported by the backend package. It is
tested indirectly in Task 3 via a stub; here we only write it and smoke-check that it
parses and rejects bad input cleanly without importing `chatterbox`.

- [ ] **Step 1: Create `backend/chatterbox_worker.py`**

```python
#!/usr/bin/env python3
"""Chatterbox worker — runs INSIDE backend/venv-chatterbox.

Speaks newline-delimited JSON on stdin/stdout. The parent process
(backend/core/engines/chatterbox_engine.py) drives it. All human-readable
logging goes to STDERR so it never corrupts the stdout protocol.

Protocol (one JSON object per line):
  stdin  {"op":"load","device":"cuda"}
         {"op":"synth","text":..,"reference_audio":<path>,"language_id":..,
          "cfg_weight":..,"exaggeration":..,"watermark":bool,"out_wav":<path>}
         {"op":"shutdown"}
  stdout {"ok":true}                                            (load)
         {"ok":true,"sample_rate":24000,"duration_sec":..,"inference_ms":..}  (synth)
         {"ok":false,"error":".."}                             (any failure)

The generated audio is written to out_wav (16-bit PCM mono WAV); only metadata
travels over the pipe.
"""

from __future__ import annotations

import json
import sys
import time
import wave


def _log(msg: str) -> None:
    print(msg, file=sys.stderr, flush=True)


def _reply(obj: dict) -> None:
    sys.stdout.write(json.dumps(obj) + "\n")
    sys.stdout.flush()


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


class _Worker:
    SAMPLE_RATE = 24000

    def __init__(self) -> None:
        self._model = None

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
        device = req.get("device") or "cuda"
        if device == "auto":
            device = "cuda"
        try:
            from chatterbox.mtl_tts import ChatterboxMultilingualTTS
        except Exception as exc:  # noqa: BLE001
            return {"ok": False, "error": f"import chatterbox failed: {exc}"}
        try:
            try:
                self._model = ChatterboxMultilingualTTS.from_pretrained(
                    device=device, t3_model="v3"
                )
            except TypeError as exc:
                if "t3_model" in str(exc):
                    self._model = ChatterboxMultilingualTTS.from_pretrained(device=device)
                else:
                    raise
        except Exception as exc:  # noqa: BLE001
            return {"ok": False, "error": f"load failed: {exc}"}
        _log(f"[chatterbox-worker] model loaded on {device}")
        return {"ok": True}

    def _synth(self, req: dict) -> dict:
        if self._model is None:
            return {"ok": False, "error": "model not loaded"}
        text = (req.get("text") or "").strip()
        ref = req.get("reference_audio")
        out_wav = req.get("out_wav")
        if not text:
            return {"ok": False, "error": "text must be non-empty"}
        if not ref:
            return {"ok": False, "error": "reference_audio required"}
        if not out_wav:
            return {"ok": False, "error": "out_wav required"}
        kwargs = dict(
            language_id=req.get("language_id") or "en",
            audio_prompt_path=ref,
            exaggeration=float(req.get("exaggeration", 0.5)),
            cfg_weight=float(req.get("cfg_weight", 0.5)),
        )
        watermark = req.get("watermark", True)
        t0 = time.perf_counter()
        try:
            try:
                wav = self._model.generate(text, watermark=watermark, **kwargs)
            except TypeError as exc:
                if "watermark" in str(exc):
                    wav = self._model.generate(text, **kwargs)
                else:
                    raise
        except Exception as exc:  # noqa: BLE001
            return {"ok": False, "error": f"generate failed: {exc}"}
        inference_ms = int((time.perf_counter() - t0) * 1000)

        import numpy as np

        if hasattr(wav, "detach"):
            arr = wav.detach().cpu().float().numpy()
        else:
            arr = np.asarray(wav, dtype=np.float32)
        if arr.ndim > 1:
            arr = arr.reshape(-1)
        try:
            _write_wav_int16(out_wav, arr, self.SAMPLE_RATE)
        except Exception as exc:  # noqa: BLE001
            return {"ok": False, "error": f"write wav failed: {exc}"}
        return {
            "ok": True,
            "sample_rate": self.SAMPLE_RATE,
            "duration_sec": float(arr.size) / float(self.SAMPLE_RATE),
            "inference_ms": inference_ms,
        }


def main() -> int:
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

- [ ] **Step 2: Smoke-check the worker handles bad input without needing chatterbox**

Run (from repo root):
```bash
printf '%s\n' '{"op":"bogus"}' 'not json' '{"op":"shutdown"}' | backend/venv/Scripts/python.exe backend/chatterbox_worker.py
```
Expected: three stdout lines —
```
{"ok": false, "error": "unknown op: 'bogus'"}
{"ok": false, "error": "bad json: ..."}
{"ok": true}
```
(The `load`/`synth` paths need chatterbox and are exercised via a stub in Task 3.)

- [ ] **Step 3: Commit**

```bash
git add backend/chatterbox_worker.py
git commit -m "feat: add standalone chatterbox stdio worker"
```

---

## Task 3: Rewrite `ChatterboxEngine` as a proxy over the worker

**Files:**
- Rewrite: `backend/core/engines/chatterbox_engine.py`
- Test: `backend/tests/test_chatterbox_proxy.py`

- [ ] **Step 1: Write the failing tests**

Create `backend/tests/test_chatterbox_proxy.py`:

```python
"""Tests for the Chatterbox proxy engine using a STUB worker.

No real chatterbox-tts is required: we point the proxy at a tiny stub
worker script run by the MAIN venv's Python. The stub speaks the same
JSON protocol and writes a small valid WAV.
"""

import sys
import textwrap
import wave
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT))

from backend.core.engines import EngineSynthRequest  # noqa: E402
from backend.core.engines.chatterbox_engine import ChatterboxEngine  # noqa: E402

# A stub worker: same protocol, writes 100 samples of silence as a WAV.
_STUB_WORKER = textwrap.dedent('''
    import json, sys, wave
    def reply(o): sys.stdout.write(json.dumps(o)+"\\n"); sys.stdout.flush()
    for line in sys.stdin:
        line = line.strip()
        if not line: continue
        req = json.loads(line)
        op = req.get("op")
        if op == "load":
            reply({"ok": True})
        elif op == "synth":
            with wave.open(req["out_wav"], "wb") as w:
                w.setnchannels(1); w.setsampwidth(2); w.setframerate(24000)
                w.writeframes(b"\\x00\\x00" * 100)
            reply({"ok": True, "sample_rate": 24000, "duration_sec": 100/24000, "inference_ms": 7})
        elif op == "shutdown":
            reply({"ok": True}); break
        else:
            reply({"ok": False, "error": "bad op"})
''')


def _make_stub_engine(tmp_path: Path) -> ChatterboxEngine:
    stub = tmp_path / "stub_worker.py"
    stub.write_text(_STUB_WORKER, encoding="utf-8")
    return ChatterboxEngine(
        worker_python=Path(sys.executable),  # the main venv python runs the stub
        worker_script=stub,
    )


def test_load_then_is_loaded(tmp_path):
    eng = _make_stub_engine(tmp_path)
    assert eng.is_loaded() is False
    eng.load()
    assert eng.is_loaded() is True
    eng.unload()
    assert eng.is_loaded() is False


def test_synthesize_returns_wav_bytes(tmp_path):
    eng = _make_stub_engine(tmp_path)
    eng.load()
    ref = tmp_path / "ref.wav"
    ref.write_bytes(b"RIFF")  # stub ignores contents
    req = EngineSynthRequest(
        text="hello", voice_id="x", reference_audio=str(ref),
        language_id="en", cfg_weight=0.5, exaggeration=0.5,
    )
    result = eng.synthesize(req)
    assert result.sample_rate == 24000
    assert result.wav_bytes[:4] == b"RIFF"
    assert result.wav_bytes[8:12] == b"WAVE"
    eng.unload()


def test_load_raises_when_venv_missing(tmp_path):
    # Point at a non-existent python so the friendly error fires.
    eng = ChatterboxEngine(
        worker_python=tmp_path / "no" / "such" / "python.exe",
        worker_script=tmp_path / "missing_worker.py",
    )
    try:
        eng.load()
        assert False, "expected RuntimeError"
    except RuntimeError as exc:
        assert "studio.py models" in str(exc)


def test_capabilities_unchanged(tmp_path):
    eng = _make_stub_engine(tmp_path)
    assert eng.name == "chatterbox"
    assert eng.sample_rate() == 24000
    assert eng.max_speakers() == 1
    assert eng.supports_voice_cloning() is True
    assert eng.supports_streaming() is False
    assert eng.available_voices() == []
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd "f:/Vibe Projects/vibe-podcast" && backend/venv/Scripts/python.exe -m pytest backend/tests/test_chatterbox_proxy.py -v`
Expected: FAIL — the current `ChatterboxEngine.__init__` doesn't accept `worker_python`/`worker_script` (TypeError), and there's no subprocess proxy yet.

- [ ] **Step 3: Rewrite `backend/core/engines/chatterbox_engine.py`**

Replace the ENTIRE file with:

```python
"""Chatterbox Multilingual V3 engine — ISOLATED-ENV PROXY.

Chatterbox hard-pins transformers==5.2.0, which is incompatible with the
`vibevoice` package (transformers==4.51.3) in the main backend venv. So the
model never runs in this process: this class is a thin proxy that drives
`backend/chatterbox_worker.py` running inside a separate venv
(`backend/venv-chatterbox`). It keeps the exact same Engine surface, so
EngineManager and SynthService are unchanged.

Communication is newline-delimited JSON over the worker's stdin/stdout; the
generated audio is written by the worker to a temp WAV that this process reads.
"""

from __future__ import annotations

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

SUPPORTED_LANGUAGE_IDS: frozenset[str] = frozenset({
    "ar", "da", "de", "el", "en", "es", "fi", "fr", "he", "hi",
    "it", "ja", "ko", "ms", "nl", "no", "pl", "pt", "ru", "sv",
    "sw", "tr", "zh",
})


def _normalize_language_id(value: str | None, default: str) -> str:
    """Coerce a voice-language code into a Chatterbox-compatible id."""
    if not value:
        return default
    candidate = value.strip().lower().split("-")[0].split("_")[0][:2]
    if candidate in SUPPORTED_LANGUAGE_IDS:
        return candidate
    log.warning(
        "Unsupported Chatterbox language_id %r (got %r); falling back to %r.",
        candidate, value, default,
    )
    return default


def _default_worker_python() -> Path:
    venv = _BACKEND_ROOT / "venv-chatterbox"
    if os.name == "nt":
        return venv / "Scripts" / "python.exe"
    return venv / "bin" / "python"


def _default_worker_script() -> Path:
    return _BACKEND_ROOT / "chatterbox_worker.py"


class ChatterboxEngine(Engine):
    """Proxy to a Chatterbox worker running in backend/venv-chatterbox."""

    name = "chatterbox"
    display_name = "Chatterbox Multilingual V3"
    description = (
        "Resemble AI's 0.5B multilingual TTS. 23 languages, voice cloning, "
        "watermarked output. Runs in its own isolated environment. ~500 MB."
    )

    def __init__(
        self,
        model_id: str = "ResembleAI/chatterbox",
        default_language_id: str = "en",
        default_cfg_weight: float = 0.5,
        default_exaggeration: float = 0.5,
        watermark: bool = True,
        device_request: str = "cuda",
        worker_python: Path | None = None,
        worker_script: Path | None = None,
    ) -> None:
        self._model_id = model_id
        self._default_language_id = _normalize_language_id(default_language_id, "en")
        self._default_cfg_weight = float(default_cfg_weight)
        self._default_exaggeration = float(default_exaggeration)
        self._watermark = bool(watermark)
        self._device_request = device_request
        self._worker_python = Path(worker_python) if worker_python else _default_worker_python()
        self._worker_script = Path(worker_script) if worker_script else _default_worker_script()
        self._proc: subprocess.Popen | None = None
        self._lock = threading.Lock()

    # -- lifecycle
    def load(self) -> None:
        if self.is_loaded():
            return
        if not self._worker_python.is_file():
            raise RuntimeError(
                "Chatterbox isn't installed in its isolated environment. "
                "Run `python studio.py models` and select Chatterbox."
            )
        device = self._device_request
        if device == "auto":
            device = "cuda"
        env = dict(os.environ)
        models_dir = _BACKEND_ROOT / "models"
        env["HF_HOME"] = str(models_dir)
        env["HUGGINGFACE_HUB_CACHE"] = str(models_dir / "hub")
        log.info("Spawning Chatterbox worker: %s %s", self._worker_python, self._worker_script)
        self._proc = subprocess.Popen(
            [str(self._worker_python), str(self._worker_script)],
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            env=env,
        )
        resp = self._exchange({"op": "load", "device": device})
        if not resp.get("ok"):
            err = resp.get("error", "unknown error")
            self._kill()
            raise RuntimeError(f"Chatterbox worker failed to load: {err}")

    def unload(self) -> None:
        if self._proc is None:
            return
        try:
            if self._proc.poll() is None:
                self._exchange({"op": "shutdown"}, expect_reply=True)
        except Exception:  # noqa: BLE001
            pass
        self._kill()

    def is_loaded(self) -> bool:
        return self._proc is not None and self._proc.poll() is None

    def engine_info(self) -> dict[str, Any]:
        device = self._device_request
        if device == "auto":
            device = "cuda"
        dtype = "bfloat16" if device == "cuda" else "float32"
        return {
            "model_id": self._model_id,
            "device": device,
            "dtype": dtype,
            "attn_implementation": "sdpa",
        }

    # -- capabilities
    def sample_rate(self) -> int:
        return 24000

    def max_speakers(self) -> int:
        return 1

    def supports_voice_cloning(self) -> bool:
        return True

    def supports_streaming(self) -> bool:
        return False

    def default_cfg_scale(self) -> float | None:
        return self._default_cfg_weight

    def available_voices(self) -> list:
        return []

    # -- synthesis
    def synthesize(self, req: EngineSynthRequest) -> EngineResult:
        if not self.is_loaded():
            raise RuntimeError("Chatterbox worker is not loaded")
        text = (req.text or "").strip()
        if not text:
            raise ValueError("text must be non-empty")
        if not req.reference_audio:
            raise ValueError("Chatterbox requires a reference_audio path for voice cloning")

        language_id = _normalize_language_id(req.language_id, self._default_language_id)
        cfg_weight = req.cfg_weight if req.cfg_weight is not None else self._default_cfg_weight
        exaggeration = req.exaggeration if req.exaggeration is not None else self._default_exaggeration
        cfg_weight = max(0.0, min(1.0, float(cfg_weight)))
        exaggeration = max(0.0, min(2.0, float(exaggeration)))

        fd, out_wav = tempfile.mkstemp(suffix=".wav", prefix="chatterbox-")
        os.close(fd)
        try:
            resp = self._exchange({
                "op": "synth",
                "text": text,
                "reference_audio": req.reference_audio,
                "language_id": language_id,
                "cfg_weight": cfg_weight,
                "exaggeration": exaggeration,
                "watermark": self._watermark,
                "out_wav": out_wav,
            })
            if not resp.get("ok"):
                raise RuntimeError(f"Chatterbox synth failed: {resp.get('error', 'unknown error')}")
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
                raise RuntimeError("Chatterbox worker is not running")
            try:
                self._proc.stdin.write(json.dumps(msg) + "\n")
                self._proc.stdin.flush()
            except (BrokenPipeError, OSError) as exc:
                self._kill()
                raise RuntimeError(f"Chatterbox worker pipe broke: {exc}") from exc
            if not expect_reply:
                return {"ok": True}
            line = self._proc.stdout.readline()
            if not line:
                stderr = ""
                try:
                    if self._proc.stderr is not None:
                        stderr = self._proc.stderr.read() or ""
                except Exception:  # noqa: BLE001
                    pass
                self._kill()
                raise RuntimeError(
                    "Chatterbox worker closed unexpectedly"
                    + (f": {stderr.strip()}" if stderr.strip() else "")
                )
            return json.loads(line)

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

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd "f:/Vibe Projects/vibe-podcast" && backend/venv/Scripts/python.exe -m pytest backend/tests/test_chatterbox_proxy.py -v`
Expected: PASS (4 tests).

- [ ] **Step 5: Run the full suite to confirm no regression**

Run: `cd "f:/Vibe Projects/vibe-podcast" && backend/venv/Scripts/python.exe -m pytest backend/tests/ -q`
Expected: PASS (existing 24 + 4 new = 28). The app still constructs (`EngineManager` builds `ChatterboxEngine()` with no worker args — the proxy just won't be `is_loaded()` until used).

- [ ] **Step 6: Commit**

```bash
git add backend/core/engines/chatterbox_engine.py backend/tests/test_chatterbox_proxy.py
git commit -m "feat: drive Chatterbox via isolated-venv worker subprocess"
```

---

## Task 4: `studio.py` — build/install venv-chatterbox on opt-in

**Files:**
- Modify: `studio.py`
- Test: `backend/tests/test_setup_helpers.py`

- [ ] **Step 1: Write the failing test**

Append to `backend/tests/test_setup_helpers.py`:

```python
def test_chatterbox_venv_python_path_shape():
    repo = Path("/repo")
    p = studio.chatterbox_venv_python(repo)
    assert p.name in ("python.exe", "python")
    assert "venv-chatterbox" in p.parts
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd "f:/Vibe Projects/vibe-podcast" && backend/venv/Scripts/python.exe -m pytest backend/tests/test_setup_helpers.py -k chatterbox_venv -v`
Expected: FAIL — `AttributeError: module 'studio' has no attribute 'chatterbox_venv_python'`.

- [ ] **Step 3: Add `chatterbox_venv_python` + install helper to `studio.py`**

In `studio.py`, immediately AFTER the existing `venv_python` function, add:

```python
def chatterbox_venv_python(repo_root: Path) -> Path:
    """Path to the ISOLATED Chatterbox venv's Python interpreter."""
    venv = repo_root / "backend" / "venv-chatterbox"
    if os.name == "nt":
        return venv / "Scripts" / "python.exe"
    return venv / "bin" / "python"


def _ensure_chatterbox_env() -> None:
    """Create backend/venv-chatterbox and install chatterbox-tts into it.

    Chatterbox can't share the main venv (transformers pin conflict), so it
    gets its own environment with a CUDA-matched torch + chatterbox-tts.
    """
    cpy = chatterbox_venv_python(REPO_ROOT)
    if not cpy.is_file():
        print("  Creating isolated Chatterbox environment (backend/venv-chatterbox) …")
        if _run([sys.executable, "-m", "venv", str(BACKEND_DIR / "venv-chatterbox")]) != 0:
            print("  ERROR: failed to create venv-chatterbox.")
            return
    # CUDA-matched torch first (same detection as the main setup).
    tag = envdetect.detect_cuda_tag()
    index = envdetect.torch_index_url(tag)
    pip_torch = [str(cpy), "-m", "pip", "install", "torch", "torchaudio"]
    if index:
        pip_torch += ["--index-url", index]
    print("  Installing PyTorch into the Chatterbox env …")
    if _run(pip_torch) != 0:
        print("  ERROR: torch install into venv-chatterbox failed.")
        return
    print("  Installing chatterbox-tts into the Chatterbox env …")
    if _run([str(cpy), "-m", "pip", "install", "-r",
             str(BACKEND_DIR / "requirements-chatterbox.txt")]) != 0:
        print("  ERROR: chatterbox-tts install failed.")
        return
    print("  Chatterbox environment ready.")
```

- [ ] **Step 4: Hook it into the model picker**

In `studio.py`, find `_interactive_model_picker` and locate the block that runs the
download for the picked keys:

```python
    _run([str(py), "-m", "backend.scripts.download_models",
          "--models", ",".join(picked)], cwd=REPO_ROOT)
```

Immediately AFTER that line (still inside the function, same indentation level), add:

```python
    if "chatterbox" in picked:
        print("  Chatterbox selected — setting up its isolated environment …")
        _ensure_chatterbox_env()
```

- [ ] **Step 5: Run the test to verify it passes**

Run: `cd "f:/Vibe Projects/vibe-podcast" && backend/venv/Scripts/python.exe -m pytest backend/tests/test_setup_helpers.py -k chatterbox_venv -v`
Expected: PASS.

- [ ] **Step 6: Smoke-check studio.py still parses**

Run: `cd "f:/Vibe Projects/vibe-podcast" && backend/venv/Scripts/python.exe studio.py --help`
Expected: help text, exit 0, no traceback.

- [ ] **Step 7: Commit**

```bash
git add studio.py backend/tests/test_setup_helpers.py
git commit -m "feat: build isolated Chatterbox venv when selected in setup"
```

---

## Task 5: Documentation

**Files:**
- Modify: `README.md`
- Modify: `CLAUDE.md`

- [ ] **Step 1: Add a Chatterbox note to `README.md`**

In `README.md`, find the `### 2. Quick setup (recommended)` section. Immediately BEFORE the
`### Manual setup & running (alternative)` heading, insert:

```markdown
> **Chatterbox installs separately.** The Chatterbox engine requires a different
> (newer) `transformers` version than VibeVoice, so it runs in its own isolated
> environment (`backend/venv-chatterbox`) as a subprocess. Pick **Chatterbox** in
> `python studio.py setup` (or run `python studio.py models` later) and it's built
> automatically — VibeVoice and Kokoro are unaffected.
```

- [ ] **Step 2: Add an architecture note to `CLAUDE.md`**

In `CLAUDE.md`, find the architecture bullet that begins with `- **\`core/engine_manager.py\`**`.
Immediately AFTER that bullet, insert:

```markdown
- **Chatterbox runs out-of-process.** `chatterbox-tts` hard-pins `transformers==5.2.0`, which is incompatible with VibeVoice's pinned `transformers==4.51.3`, so the two **cannot share a venv**. `core/engines/chatterbox_engine.py` is therefore a **proxy**: it keeps the normal `Engine` interface but drives `backend/chatterbox_worker.py` running in a separate `backend/venv-chatterbox` (built on demand by `studio.py` when Chatterbox is selected). They talk newline-delimited JSON over stdin/stdout; audio passes as temp-file paths. `chatterbox-tts` lives in `requirements-chatterbox.txt`, never the main `requirements.txt`.
```

- [ ] **Step 3: Verify both inserts landed**

Run: `cd "f:/Vibe Projects/vibe-podcast" && grep -c "venv-chatterbox" README.md CLAUDE.md`
Expected: each file reports at least 1.

- [ ] **Step 4: Commit**

```bash
git add README.md CLAUDE.md
git commit -m "docs: document Chatterbox isolated-env install and architecture"
```

---

## Task 6: Final verification

**No code — verification run-through.**

- [ ] **Step 1: Full test suite green**

Run: `cd "f:/Vibe Projects/vibe-podcast" && backend/venv/Scripts/python.exe -m pytest backend/tests/ -q`
Expected: all PASS (28+ tests). Confirms the proxy, stub plumbing, and studio helper work,
and that nothing regressed — all WITHOUT `chatterbox-tts` in the main venv.

- [ ] **Step 2: Confirm the main venv is still VibeVoice-clean**

Run: `cd "f:/Vibe Projects/vibe-podcast" && backend/venv/Scripts/python.exe -c "import transformers; print('transformers', transformers.__version__); from vibevoice.modular.modeling_vibevoice_inference import VibeVoiceForConditionalGenerationInference; print('vibevoice OK')"`
Expected: `transformers 4.51.3` and `vibevoice OK` (proves the isolation goal holds — the main env is untouched by Chatterbox work).

- [ ] **Step 3: Confirm backend boots without the degraded-mode error**

Active engine is already `vibevoice` (in `backend/.last_engine`). Optionally start the app:
`python studio.py start --dev` → backend logs should show no `EngineLoadError`/chatterbox
traceback at startup. Ctrl+C to stop. (Selecting Chatterbox in the UI without having run the
opt-in install will surface the friendly "run `python studio.py models`" error — expected.)

- [ ] **Step 4 (optional, heavy, manual): Real Chatterbox end-to-end**

Only if you want to validate real generation: `python studio.py models`, select Chatterbox
(builds `backend/venv-chatterbox`), then in the UI switch to Chatterbox, assign a voice, and
Generate. Expected: audio is produced via the worker subprocess; switching back to VibeVoice
still works (proving the envs don't collide).

- [ ] **Step 5: Finish**

Use the `superpowers:finishing-a-development-branch` skill to integrate the work.

---

## Self-Review Notes

- **Spec coverage:** worker (T2), proxy with same Engine surface + test seam (T3), requirements split (T1), studio.py opt-in venv build reusing envdetect (T4), docs (T5), tests via stub worker + missing-venv + studio helper (T3/T4), final verification incl. VibeVoice-still-clean (T6). All spec sections map to a task.
- **Type/name consistency:** `ChatterboxEngine(worker_python=, worker_script=)`, `chatterbox_venv_python()`, `_ensure_chatterbox_env()`, `_default_worker_python()`, `_exchange()`, `_kill()`, worker ops `load`/`synth`/`shutdown`, response keys `ok`/`error`/`sample_rate`/`duration_sec`/`inference_ms`, request keys incl. `out_wav`/`reference_audio` — used identically across worker (T2), proxy (T3), and tests.
- **Isolation invariant:** every test runs on the main venv and uses a stub worker; none import `chatterbox-tts`. T6 step 2 explicitly re-verifies VibeVoice/transformers are untouched.
- **EngineManager unchanged:** the proxy's new constructor args are optional (default to real paths); the existing `ChatterboxEngine(...)` call in `engine_manager.py` needs no edit.
