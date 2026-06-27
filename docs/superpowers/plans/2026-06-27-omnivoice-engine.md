# OmniVoice Engine (Spec A — clone) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add OmniVoice (k2-fsa/OmniVoice) as a fourth TTS engine running out-of-process in its own `backend/venv-omnivoice`, with voice cloning, an on-demand in-UI install, and zero new per-segment UI — mirroring the proven Chatterbox isolation pattern.

**Architecture:** OmniVoice pins `transformers>=5.3.0` + `torch 2.8`, incompatible with every existing venv, so it runs as an isolated subprocess worker (`omnivoice_worker.py` in `venv-omnivoice`) driven by a proxy `OmniVoiceEngine` over newline-delimited JSON, exactly like Chatterbox. The install flow and install dialog are lightly generalized to serve both Chatterbox and OmniVoice. The worker implements clone/design/auto so Spec B (voice-design UX) needs no worker changes; Spec A exercises clone only.

**Tech Stack:** Python / FastAPI / `omnivoice` (in an isolated venv) / `huggingface_hub` (backend); React + TypeScript + Vite + Tailwind (frontend). Tests: `pytest` (backend, via `backend/venv`), `tsc` typecheck + `vite build` (frontend).

**Reference spec:** `docs/superpowers/specs/2026-06-27-omnivoice-engine-design.md`

**Conventions:** Backend tests run from `backend/` with the project venv: `cd backend && ./venv/Scripts/python.exe -m pytest …` (Windows). Frontend commands run from `frontend/`. All file paths below are exact.

---

## File Structure

- **Modify** `tools/envdetect.py` — cu126/cu128 index URLs + OmniVoice CUDA→tag mapper.
- **Modify** `studio.py` — `omnivoice_venv_python`, `omnivoice_ready_marker`, `_ensure_omnivoice_env`, `install-omnivoice` subcommand.
- **Create** `backend/requirements-omnivoice.txt` — `omnivoice` only.
- **Create** `backend/omnivoice_worker.py` — isolated stdio JSON worker (clone/design/auto).
- **Create** `backend/core/engines/omnivoice_engine.py` — proxy engine.
- **Create** `backend/tests/test_omnivoice_proxy.py` — proxy tests with a stub worker + message-building unit tests.
- **Modify** `backend/core/engine_manager.py` + `backend/config.py` + `backend/app.py` — register the engine + defaults.
- **Modify** `backend/services/chatterbox_install.py` — generalize to `EngineEnvInstaller(subcommand)` with a `ChatterboxInstaller` alias.
- **Modify** `backend/app.py` + `backend/api/deps.py` + `backend/api/engines.py` + `backend/tests/test_chatterbox_install.py` — installer registry + generalized install endpoints.
- **Rename/modify** `frontend/src/components/InstallChatterboxDialog.tsx` → `InstallEngineDialog.tsx`; **modify** `frontend/src/lib/api.ts`, `frontend/src/App.tsx`, `frontend/src/lib/engineHints.ts`.

---

## Task 1: envdetect — torch 2.8 CUDA tags for OmniVoice

**Files:**
- Modify: `tools/envdetect.py`
- Test: `backend/tests/test_setup_helpers.py`

- [ ] **Step 1: Write the failing test**

Append to `backend/tests/test_setup_helpers.py` (after the existing `test_cuda_version_to_tag`):

```python
def test_cuda_version_to_omnivoice_tag():
    # torch 2.8 wheels: cu128 (CUDA 12.8+/13.x), cu126 (12.6-12.7), else CPU.
    assert envdetect.cuda_version_to_omnivoice_tag("13.2") == "cu128"
    assert envdetect.cuda_version_to_omnivoice_tag("12.8") == "cu128"
    assert envdetect.cuda_version_to_omnivoice_tag("12.6") == "cu126"
    assert envdetect.cuda_version_to_omnivoice_tag("12.4") is None
    assert envdetect.cuda_version_to_omnivoice_tag("11.8") is None
    assert envdetect.cuda_version_to_omnivoice_tag(None) is None


def test_omnivoice_torch_index_urls_present():
    assert envdetect.torch_index_url("cu128") == "https://download.pytorch.org/whl/cu128"
    assert envdetect.torch_index_url("cu126") == "https://download.pytorch.org/whl/cu126"


def test_detect_omnivoice_cuda_tag_with_injected_runner():
    smi = "Driver Version: 596.21       CUDA Version: 13.2"
    assert envdetect.detect_omnivoice_cuda_tag(runner=lambda: smi) == "cu128"
    assert envdetect.detect_omnivoice_cuda_tag(runner=lambda: None) is None
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd backend && ./venv/Scripts/python.exe -m pytest tests/test_setup_helpers.py::test_cuda_version_to_omnivoice_tag -v`
Expected: FAIL with `AttributeError: module 'tools.envdetect' has no attribute 'cuda_version_to_omnivoice_tag'`

- [ ] **Step 3: Implement**

In `tools/envdetect.py`, add `cu128`/`cu126` to `CUDA_TAG_TO_INDEX` (it currently has cu124/cu121/cu118):

```python
CUDA_TAG_TO_INDEX: dict[str, str] = {
    "cu128": "https://download.pytorch.org/whl/cu128",
    "cu126": "https://download.pytorch.org/whl/cu126",
    "cu124": "https://download.pytorch.org/whl/cu124",
    "cu121": "https://download.pytorch.org/whl/cu121",
    "cu118": "https://download.pytorch.org/whl/cu118",
}
```

Then add these two functions at the end of `tools/envdetect.py`:

```python
def cuda_version_to_omnivoice_tag(version: str | None) -> str | None:
    """Map a CUDA runtime version to a torch 2.8 wheel tag for OmniVoice.

    OmniVoice needs torch 2.8, whose CUDA builds are cu126 and cu128 (there is
    no cu124 torch-2.8 wheel). Drivers below CUDA 12.6 fall back to the CPU
    build. This is separate from `cuda_version_to_tag`, which targets the
    torch 2.6 builds used by the main/Chatterbox venvs.
    """
    if not version:
        return None
    try:
        major, minor = (int(p) for p in version.split(".")[:2])
    except ValueError:
        return None
    if major >= 13:
        return "cu128"
    if major == 12:
        if minor >= 8:
            return "cu128"
        if minor >= 6:
            return "cu126"
    return None


def detect_omnivoice_cuda_tag(runner=None) -> str | None:
    """Detect the torch-2.8 CUDA wheel tag for OmniVoice. `runner` is injectable."""
    run = runner or _run_nvidia_smi
    text = run()
    if text is None:
        return None
    return cuda_version_to_omnivoice_tag(parse_nvidia_smi_cuda_version(text))
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd backend && ./venv/Scripts/python.exe -m pytest tests/test_setup_helpers.py -k "omnivoice or torch_index" -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add tools/envdetect.py backend/tests/test_setup_helpers.py
git commit -m "feat: envdetect torch-2.8 CUDA tags for OmniVoice"
```

---

## Task 2: studio.py — OmniVoice isolated-env install

**Files:**
- Modify: `studio.py`
- Create: `backend/requirements-omnivoice.txt`
- Test: `backend/tests/test_setup_helpers.py`

- [ ] **Step 1: Write the failing test**

Append to `backend/tests/test_setup_helpers.py`:

```python
def test_omnivoice_venv_python_path_shape():
    repo = Path("/repo")
    p = studio.omnivoice_venv_python(repo)
    assert p.name in ("python.exe", "python")
    assert "venv-omnivoice" in p.parts


def test_omnivoice_ready_marker_path():
    repo = Path("/repo")
    m = studio.omnivoice_ready_marker(repo)
    assert m.name == ".omnivoice-ready"
    assert "venv-omnivoice" in m.parts


def test_install_omnivoice_subcommand_success(monkeypatch):
    calls = {"n": 0}
    def _fake():
        calls["n"] += 1
        return True
    monkeypatch.setattr(studio, "_ensure_omnivoice_env", _fake)
    assert studio.main(["install-omnivoice"]) == 0
    assert calls["n"] == 1


def test_install_omnivoice_subcommand_failure(monkeypatch):
    monkeypatch.setattr(studio, "_ensure_omnivoice_env", lambda: False)
    assert studio.main(["install-omnivoice"]) == 1
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd backend && ./venv/Scripts/python.exe -m pytest tests/test_setup_helpers.py::test_omnivoice_venv_python_path_shape -v`
Expected: FAIL with `AttributeError: module 'studio' has no attribute 'omnivoice_venv_python'`

- [ ] **Step 3: Implement**

Create `backend/requirements-omnivoice.txt`:

```
# OmniVoice runs in an ISOLATED venv (backend/venv-omnivoice). It pins
# transformers>=5.3.0 and torch 2.8, which conflict with the main venv
# (VibeVoice transformers==4.51.3) and the Chatterbox venv (transformers==5.2.0).
# torch is installed separately with the right CUDA wheel by studio.py, so it
# is intentionally NOT pinned here.
omnivoice
```

In `studio.py`, add these helpers next to the Chatterbox equivalents (after `chatterbox_ready_marker`, ~line 62):

```python
def omnivoice_venv_python(repo_root: Path) -> Path:
    """Path to the ISOLATED OmniVoice venv's Python interpreter."""
    venv = repo_root / "backend" / "venv-omnivoice"
    if os.name == "nt":
        return venv / "Scripts" / "python.exe"
    return venv / "bin" / "python"


def omnivoice_ready_marker(repo_root: Path) -> Path:
    """Sentinel written only after a FULL successful OmniVoice install.

    Mirrors chatterbox_ready_marker: the venv Python exists right after
    `python -m venv`, long before packages are installed, so only this
    marker (written last) means "fully installed".
    """
    return repo_root / "backend" / "venv-omnivoice" / ".omnivoice-ready"
```

In `studio.py`, add `_ensure_omnivoice_env` after `_ensure_chatterbox_env` (~line 159). It mirrors the Chatterbox installer but uses the OmniVoice torch tag:

```python
def _ensure_omnivoice_env() -> bool:
    """Create backend/venv-omnivoice and install omnivoice into it.

    OmniVoice can't share any existing venv (transformers>=5.3.0 + torch 2.8),
    so it gets its own environment with a CUDA-matched torch + omnivoice.
    Returns True on success, False on any failure.
    """
    marker = omnivoice_ready_marker(REPO_ROOT)
    try:
        marker.unlink()
    except OSError:
        pass
    opy = omnivoice_venv_python(REPO_ROOT)
    if not opy.is_file():
        print("  Creating isolated OmniVoice environment (backend/venv-omnivoice) …")
        if _run([sys.executable, "-m", "venv", str(BACKEND_DIR / "venv-omnivoice")]) != 0:
            print("  ERROR: failed to create venv-omnivoice.")
            return False
    print("  Upgrading pip in the OmniVoice env …")
    raw_ok = _run([str(opy), "-m", "pip", "install", "--upgrade", "pip"]) == 0
    progress = ["--progress-bar", "raw"] if raw_ok else []
    net = ["--retries", "10", "--timeout", "120"]
    # 1. Install omnivoice FIRST (pulls a torch build to satisfy its pin).
    print("  Installing omnivoice into the OmniVoice env …")
    if _run([str(opy), "-m", "pip", "install", *progress, *net, "-r",
             str(BACKEND_DIR / "requirements-omnivoice.txt")]) != 0:
        print("  ERROR: omnivoice install failed.")
        return False
    # 2. Swap in the CUDA build of the SAME torch version for GPU. --no-deps
    #    avoids re-resolving deps from the wheel-only CUDA index.
    ov_tag = envdetect.detect_omnivoice_cuda_tag()
    index = envdetect.torch_index_url(ov_tag) if ov_tag else None
    if index:
        tv = _pip_pkg_version(opy, "torch")
        av = _pip_pkg_version(opy, "torchaudio")
        if tv:
            specs = [f"torch=={tv}+{ov_tag}"]
            if av:
                specs.append(f"torchaudio=={av}+{ov_tag}")
            print(f"  Installing the CUDA build of torch {tv} ({ov_tag}) for GPU …")
            if _run([str(opy), "-m", "pip", "install", *progress, *net, "--force-reinstall",
                     "--no-deps", "--index-url", index, *specs]) != 0:
                print("  ERROR: CUDA torch install failed.")
                return False
    else:
        print("  No torch-2.8 CUDA build for this driver — leaving the default "
              "(CPU) torch in place. OmniVoice will run on CPU (slow).")
    try:
        marker.parent.mkdir(parents=True, exist_ok=True)
        marker.write_text("ok\n", encoding="utf-8")
    except OSError as exc:
        print(f"  ERROR: could not write ready marker: {exc}")
        return False
    print("  OmniVoice environment ready.")
    return True
```

Add the non-interactive subcommand handler after `cmd_install_chatterbox` (~line 324):

```python
def cmd_install_omnivoice(_args: argparse.Namespace) -> int:
    """Non-interactive: build/refresh the isolated OmniVoice env. Used by the
    backend's in-UI installer. Returns 0 on success, 1 on failure."""
    print(BANNER)
    ok = _ensure_omnivoice_env()
    return 0 if ok else 1
```

Register the subparser (next to `install-chatterbox`, ~line 481) and dispatch it (~line 488). Add the subparser line:

```python
    sub.add_parser("install-chatterbox", help="build the isolated Chatterbox env (non-interactive)")
    sub.add_parser("install-omnivoice", help="build the isolated OmniVoice env (non-interactive)")
```

And the dispatch branch (after the `install-chatterbox` branch in `main`):

```python
    if args.command == "install-chatterbox":
        return cmd_install_chatterbox(args)
    if args.command == "install-omnivoice":
        return cmd_install_omnivoice(args)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd backend && ./venv/Scripts/python.exe -m pytest tests/test_setup_helpers.py -k omnivoice -v`
Expected: PASS (4 passed)

- [ ] **Step 5: Commit**

```bash
git add studio.py backend/requirements-omnivoice.txt backend/tests/test_setup_helpers.py
git commit -m "feat: studio.py install-omnivoice (isolated venv + cu128 torch)"
```

---

## Task 3: `omnivoice_worker.py` — isolated stdio worker

**Files:**
- Create: `backend/omnivoice_worker.py`

This worker runs inside `venv-omnivoice` and is exercised end-to-end by the proxy tests (Task 4) via a stub worker, exactly as `chatterbox_worker.py` is. It has no standalone unit test (it imports the real `omnivoice` only inside `load`).

- [ ] **Step 1: Create the file**

Create `backend/omnivoice_worker.py`:

```python
#!/usr/bin/env python3
"""OmniVoice worker — runs INSIDE backend/venv-omnivoice.

Speaks newline-delimited JSON on stdin/stdout. The parent process
(backend/core/engines/omnivoice_engine.py) drives it. All human-readable
logging goes to STDERR so it never corrupts the stdout protocol.

Protocol (one JSON object per line):
  stdin  {"op":"load","device":"cuda","model_id":"k2-fsa/OmniVoice"}
         {"op":"synth","mode":"clone|design|auto","text":..,"out_wav":<path>,
          "ref_audio":<path?>,"ref_text":<str?>,"instruct":<str?>,
          "speed":<float?>,"num_step":<int?>}
         {"op":"shutdown"}
  stdout {"ok":true}                                            (load)
         {"ok":true,"sample_rate":24000,"duration_sec":..,"inference_ms":..}  (synth)
         {"ok":false,"error":".."}                             (any failure)

The generated audio is written to out_wav (16-bit PCM mono WAV at 24 kHz);
only metadata travels over the pipe.
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
    return d  # cpu, mps, xpu, cuda:N


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
        device = _norm_device(req.get("device"))
        model_id = req.get("model_id") or "k2-fsa/OmniVoice"
        try:
            from omnivoice import OmniVoice
        except Exception as exc:  # noqa: BLE001
            return {"ok": False, "error": f"import omnivoice failed: {exc}"}
        try:
            self._model = OmniVoice.from_pretrained(model_id, device_map=device)
        except Exception as exc:  # noqa: BLE001
            return {"ok": False, "error": f"load failed: {exc}"}
        _log(f"[omnivoice-worker] model loaded on {device}")
        return {"ok": True}

    def _synth(self, req: dict) -> dict:
        if self._model is None:
            return {"ok": False, "error": "model not loaded"}
        text = (req.get("text") or "").strip()
        out_wav = req.get("out_wav")
        mode = req.get("mode") or "auto"
        if not text:
            return {"ok": False, "error": "text must be non-empty"}
        if not out_wav:
            return {"ok": False, "error": "out_wav required"}
        ctl: dict = {}
        if req.get("num_step") is not None:
            ctl["num_step"] = int(req["num_step"])
        if req.get("speed") is not None:
            ctl["speed"] = float(req["speed"])
        t0 = time.perf_counter()
        try:
            if mode == "clone":
                ref = req.get("ref_audio")
                if not ref:
                    return {"ok": False, "error": "clone mode requires ref_audio"}
                gkwargs = {"ref_audio": ref}
                if req.get("ref_text"):
                    gkwargs["ref_text"] = req["ref_text"]
                audio = self._model.generate(text, **gkwargs, **ctl)
            elif mode == "design":
                audio = self._model.generate(text, instruct=req.get("instruct") or "", **ctl)
            else:  # auto
                audio = self._model.generate(text, **ctl)
        except Exception as exc:  # noqa: BLE001
            return {"ok": False, "error": f"generate failed: {exc}"}
        inference_ms = int((time.perf_counter() - t0) * 1000)

        import numpy as np

        # OmniVoice returns a list of np.ndarray (one per utterance); take the
        # first. Tolerate a bare array too.
        arr = audio[0] if isinstance(audio, (list, tuple)) else audio
        if hasattr(arr, "detach"):
            arr = arr.detach().cpu().float().numpy()
        arr = np.asarray(arr, dtype=np.float32).reshape(-1)
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
    global _OUT
    # Reserve the real stdout for protocol replies, then point fd 1 — Python
    # AND C-level/library writes — at stderr so model-load noise can't corrupt
    # the JSON stream the parent reads.
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

- [ ] **Step 2: Sanity-check it imports (stdlib-only at module load)**

Run: `cd backend && ./venv/Scripts/python.exe -c "import ast; ast.parse(open('omnivoice_worker.py').read()); print('ok')"`
Expected: `ok` (parses; `omnivoice`/`numpy` are imported lazily, so this never needs the isolated venv).

- [ ] **Step 3: Commit**

```bash
git add backend/omnivoice_worker.py
git commit -m "feat: OmniVoice isolated stdio worker (clone/design/auto)"
```

---

## Task 4: `OmniVoiceEngine` proxy

**Files:**
- Create: `backend/core/engines/omnivoice_engine.py`
- Test: `backend/tests/test_omnivoice_proxy.py`

The proxy reuses the Chatterbox proxy's subprocess mechanics verbatim (spawn/`_exchange`/stderr-drain/`_kill`/ready-marker). Build it by copying `backend/core/engines/chatterbox_engine.py` and applying the changes below.

- [ ] **Step 1: Write the failing tests**

Create `backend/tests/test_omnivoice_proxy.py`:

```python
"""Tests for the OmniVoice proxy engine using a STUB worker + message builder.

No real omnivoice is required: we point the proxy at a tiny stub worker run by
the MAIN venv's Python, speaking the same JSON protocol.
"""

import sys
import textwrap
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT))

import pytest  # noqa: E402

from backend.core.engines import EngineSynthRequest  # noqa: E402
from backend.core.engines.omnivoice_engine import OmniVoiceEngine  # noqa: E402

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


def _make_stub_engine(tmp_path: Path) -> OmniVoiceEngine:
    stub = tmp_path / "stub_worker.py"
    stub.write_text(_STUB_WORKER, encoding="utf-8")
    return OmniVoiceEngine(worker_python=Path(sys.executable), worker_script=stub)


def test_capabilities():
    eng = OmniVoiceEngine(worker_python=Path("x"), worker_script=Path("y"))
    assert eng.name == "omnivoice"
    assert eng.sample_rate() == 24000
    assert eng.max_speakers() == 1
    assert eng.supports_voice_cloning() is True
    assert eng.supports_streaming() is False
    assert eng.default_cfg_scale() is None
    assert eng.available_voices() == []


def test_build_synth_msg_clone():
    eng = OmniVoiceEngine(worker_python=Path("x"), worker_script=Path("y"), num_step=24)
    req = EngineSynthRequest(text="hi", voice_id="v", reference_audio="/ref.wav", speed=1.2)
    msg = eng._build_synth_msg(req, "/out.wav")
    assert msg["op"] == "synth"
    assert msg["mode"] == "clone"
    assert msg["text"] == "hi"
    assert msg["ref_audio"] == "/ref.wav"
    assert msg["out_wav"] == "/out.wav"
    assert msg["speed"] == 1.2
    assert msg["num_step"] == 24


def test_build_synth_msg_requires_reference_audio():
    eng = OmniVoiceEngine(worker_python=Path("x"), worker_script=Path("y"))
    req = EngineSynthRequest(text="hi", voice_id="v")  # no reference_audio
    with pytest.raises(ValueError):
        eng._build_synth_msg(req, "/out.wav")


def test_load_then_synthesize_with_stub(tmp_path):
    eng = _make_stub_engine(tmp_path)
    assert eng.is_loaded() is False
    eng.load()
    assert eng.is_loaded() is True
    ref = tmp_path / "ref.wav"
    ref.write_bytes(b"RIFF")
    req = EngineSynthRequest(text="hello", voice_id="v", reference_audio=str(ref))
    result = eng.synthesize(req)
    assert result.sample_rate == 24000
    assert result.wav_bytes[:4] == b"RIFF"
    assert result.wav_bytes[8:12] == b"WAVE"
    eng.unload()
    assert eng.is_loaded() is False


def test_load_raises_when_venv_missing(tmp_path):
    eng = OmniVoiceEngine(
        worker_python=tmp_path / "no" / "such" / "python.exe",
        worker_script=tmp_path / "missing_worker.py",
    )
    with pytest.raises(RuntimeError) as exc:
        eng.load()
    assert "studio.py" in str(exc.value)


def test_installed_flag_requires_ready_marker(tmp_path):
    venv = tmp_path / "venv-omnivoice"
    (venv / "Scripts").mkdir(parents=True)
    py = venv / "Scripts" / "python.exe"
    py.write_text("", encoding="utf-8")
    eng = OmniVoiceEngine(worker_python=py, worker_script=tmp_path / "w.py")
    assert eng.installed() is False
    assert eng.info()["installed"] is False
    (venv / ".omnivoice-ready").write_text("ok", encoding="utf-8")
    assert eng.installed() is True
    assert eng.info()["installed"] is True
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd backend && ./venv/Scripts/python.exe -m pytest tests/test_omnivoice_proxy.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'backend.core.engines.omnivoice_engine'`

- [ ] **Step 3: Implement the proxy**

Copy `backend/core/engines/chatterbox_engine.py` to `backend/core/engines/omnivoice_engine.py`, then make exactly these changes (everything else — `_exchange`, `_start_stderr_drain`, `_recent_stderr`, `_kill`, the stderr-drain fields — stays identical):

(a) Replace the module docstring's first line and the `_BACKEND_ROOT`/default-path helpers' names. Replace the top of the file (docstring through `_default_worker_script`) with:

```python
"""OmniVoice engine — ISOLATED-ENV PROXY.

OmniVoice pins transformers>=5.3.0 and torch 2.8, incompatible with the main
venv (VibeVoice transformers==4.51.3) and the Chatterbox venv
(transformers==5.2.0). So the model never runs in this process: this class is
a thin proxy that drives `backend/omnivoice_worker.py` inside a separate venv
(`backend/venv-omnivoice`). It keeps the exact same Engine surface, so
EngineManager and SynthService are unchanged.

Communication is newline-delimited JSON over the worker's stdin/stdout; the
generated audio is written by the worker to a temp WAV this process reads.

Spec A drives voice cloning only (a selected reference voice). The worker also
implements design/auto modes; those are wired up in Spec B.
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
    venv = _BACKEND_ROOT / "venv-omnivoice"
    if os.name == "nt":
        return venv / "Scripts" / "python.exe"
    return venv / "bin" / "python"


def _default_worker_script() -> Path:
    return _BACKEND_ROOT / "omnivoice_worker.py"
```

(Delete the Chatterbox-only `SUPPORTED_LANGUAGE_IDS` set and `_normalize_language_id` helper — OmniVoice doesn't use them.)

(b) Replace the class header + `__init__` with:

```python
class OmniVoiceEngine(Engine):
    """Proxy to an OmniVoice worker running in backend/venv-omnivoice."""

    name = "omnivoice"
    display_name = "OmniVoice"
    description = (
        "k2-fsa's 0.6B zero-shot multilingual TTS (600+ languages). Voice "
        "cloning from a short reference clip. Runs in its own isolated "
        "environment. ~0.6B weights download on first use."
    )

    def __init__(
        self,
        model_id: str = "k2-fsa/OmniVoice",
        device_request: str = "cuda",
        num_step: int | None = 32,
        worker_python: Path | None = None,
        worker_script: Path | None = None,
    ) -> None:
        self._model_id = model_id
        self._device_request = device_request
        self._num_step = num_step
        self._worker_python = Path(worker_python) if worker_python else _default_worker_python()
        self._worker_script = Path(worker_script) if worker_script else _default_worker_script()
        self._proc: subprocess.Popen | None = None
        self._lock = threading.Lock()
        self._stderr_tail: collections.deque[str] = collections.deque(maxlen=200)
        self._stderr_thread: threading.Thread | None = None
```

(c) In `load()`, keep the structure but change the friendly error, the marker-based env vars, and the load op. Replace the body of `load()` with:

```python
    def load(self) -> None:
        if self.is_loaded():
            return
        if not self._worker_python.is_file():
            raise RuntimeError(
                "OmniVoice isn't installed in its isolated environment. "
                "Run `python studio.py install-omnivoice` (or click Install in the UI)."
            )
        device = self._device_request
        if device == "auto":
            device = "cuda"
        env = dict(os.environ)
        models_dir = _BACKEND_ROOT / "models"
        env["HF_HOME"] = str(models_dir)
        env["HUGGINGFACE_HUB_CACHE"] = str(models_dir / "hub")
        log.info("Spawning OmniVoice worker: %s %s", self._worker_python, self._worker_script)
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
            raise RuntimeError(f"OmniVoice worker failed to load: {err}")
```

(d) Replace `installed()` + `_ready_marker()`:

```python
    def installed(self) -> bool:
        return self._ready_marker().is_file()

    def _ready_marker(self) -> Path:
        # backend/venv-omnivoice/.omnivoice-ready
        return self._worker_python.parent.parent / ".omnivoice-ready"
```

(e) Replace `engine_info()`:

```python
    def engine_info(self) -> dict[str, Any]:
        device = self._device_request
        if device == "auto":
            device = "cuda"
        dtype = "float32"
        return {
            "model_id": self._model_id,
            "device": device,
            "dtype": dtype,
            "attn_implementation": "sdpa",
        }
```

(f) Replace the capabilities block (`sample_rate`/`max_speakers`/`supports_voice_cloning`/`supports_streaming`/`default_cfg_scale`/`available_voices`) with:

```python
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
        return None  # OmniVoice has no CFG knob

    def available_voices(self) -> list:
        return []
```

(g) Replace the entire `synthesize()` method with a message-builder + exchange (the worker handles cloning):

```python
    # -- synthesis
    def _build_synth_msg(self, req: EngineSynthRequest, out_wav: str) -> dict:
        """Build the worker 'synth' message. Spec A: clone mode only."""
        text = (req.text or "").strip()
        if not text:
            raise ValueError("text must be non-empty")
        if not req.reference_audio:
            raise ValueError(
                "OmniVoice (Spec A) requires a reference voice for cloning; "
                "auto/design modes arrive in Spec B."
            )
        msg: dict[str, Any] = {
            "op": "synth",
            "mode": "clone",
            "text": text,
            "ref_audio": req.reference_audio,
            "out_wav": out_wav,
        }
        if req.speed is not None:
            msg["speed"] = float(req.speed)
        if self._num_step is not None:
            msg["num_step"] = int(self._num_step)
        return msg

    def synthesize(self, req: EngineSynthRequest) -> EngineResult:
        if not self.is_loaded():
            raise RuntimeError("OmniVoice worker is not loaded")
        fd, out_wav = tempfile.mkstemp(suffix=".wav", prefix="omnivoice-")
        os.close(fd)
        try:
            msg = self._build_synth_msg(req, out_wav)
            resp = self._exchange(msg)
            if not resp.get("ok"):
                raise RuntimeError(f"OmniVoice synth failed: {resp.get('error', 'unknown error')}")
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
```

Keep `unload()`, `is_loaded()`, `_exchange()`, `_start_stderr_drain()`, `_recent_stderr()`, `_kill()` exactly as copied from the Chatterbox proxy.

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd backend && ./venv/Scripts/python.exe -m pytest tests/test_omnivoice_proxy.py -v`
Expected: PASS (7 passed)

- [ ] **Step 5: Commit**

```bash
git add backend/core/engines/omnivoice_engine.py backend/tests/test_omnivoice_proxy.py
git commit -m "feat: OmniVoiceEngine proxy (clone) with stub-worker tests"
```

---

## Task 5: Register OmniVoice in the engine manager + config

**Files:**
- Modify: `backend/config.py`
- Modify: `backend/core/engine_manager.py`
- Modify: `backend/app.py`
- Modify: `backend/cli.py` (only if it lists engine choices — see Step 3)
- Test: `backend/tests/test_omnivoice_proxy.py`

- [ ] **Step 1: Write the failing test**

Append to `backend/tests/test_omnivoice_proxy.py`:

```python
def test_engine_manager_registers_omnivoice(tmp_path):
    from backend.core.engine_manager import EngineManager

    em = EngineManager(
        default_engine="vibevoice",
        voices_dir=tmp_path / "voices",
        uploads_dir=tmp_path / "uploads",
        model_id="vibevoice/VibeVoice-1.5B",
        device_request="cpu",
        state_dir=tmp_path,
    )
    names = [e.name for e in em.list_engines()]
    assert "omnivoice" in names
    eng = em.get_engine("omnivoice")
    assert eng.display_name == "OmniVoice"
    # Not installed in a bare test env (no marker) → installed flag is False.
    assert eng.info()["installed"] is False
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd backend && ./venv/Scripts/python.exe -m pytest tests/test_omnivoice_proxy.py::test_engine_manager_registers_omnivoice -v`
Expected: FAIL with `EngineNotFound: omnivoice` (or KeyError).

- [ ] **Step 3: Implement**

In `backend/config.py`:
- Update the `default_engine` field (line 27) to include omnivoice:
```python
    default_engine: Literal["vibevoice", "kokoro", "chatterbox", "omnivoice"] = "vibevoice"
```
- Add OmniVoice defaults after the `chatterbox_watermark` field (~line 54):
```python
    omnivoice_model_id: str = "k2-fsa/OmniVoice"
    omnivoice_num_step: int = 32
```

In `backend/core/engine_manager.py`:
- Add the import next to the other engine imports (~line 19):
```python
from .engines.omnivoice_engine import OmniVoiceEngine
```
- Add constructor params after `chatterbox_watermark` (~line 64):
```python
        chatterbox_watermark: bool = True,
        omnivoice_model_id: str = "k2-fsa/OmniVoice",
        omnivoice_num_step: int = 32,
        state_dir: Path | None = None,
```
- Add the engine to the `self._engines` dict after the `chatterbox` entry (~line 89, the order places it last in the selector):
```python
            "omnivoice": OmniVoiceEngine(
                model_id=omnivoice_model_id,
                device_request=device_request,
                num_step=omnivoice_num_step,
            ),
```

In `backend/app.py`, pass the new settings through the `EngineManager(...)` construction (after `chatterbox_watermark=settings.chatterbox_watermark,`, ~line 137):
```python
        chatterbox_watermark=settings.chatterbox_watermark,
        omnivoice_model_id=settings.omnivoice_model_id,
        omnivoice_num_step=settings.omnivoice_num_step,
```

In `backend/cli.py`: search for an `--engine` argument with a `choices=[...]` list. If present, add `"omnivoice"` to that list. Run first:

Run: `cd backend && ./venv/Scripts/python.exe -c "import re,io; s=open('cli.py').read(); print('CHOICES' if 'choices' in s and 'engine' in s else 'no engine choices list')"`

If it prints `CHOICES`, open `backend/cli.py`, find the engine argument's `choices=[...]`, and add `"omnivoice"`. If it prints `no engine choices list`, no cli change is needed.

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd backend && ./venv/Scripts/python.exe -m pytest tests/test_omnivoice_proxy.py -v`
Expected: PASS (8 passed)

- [ ] **Step 5: Run the full backend suite (no regressions)**

Run: `cd backend && ./venv/Scripts/python.exe -m pytest tests/ -q`
Expected: PASS (previous count + the new OmniVoice tests; 0 failures).

- [ ] **Step 6: Commit**

```bash
git add backend/config.py backend/core/engine_manager.py backend/app.py backend/cli.py
git commit -m "feat: register OmniVoice engine + config defaults"
```

---

## Task 6: Generalize the install service + endpoints

**Files:**
- Modify: `backend/services/chatterbox_install.py`
- Modify: `backend/app.py`
- Modify: `backend/api/deps.py`
- Modify: `backend/api/engines.py`
- Modify: `backend/tests/test_chatterbox_install.py`

- [ ] **Step 1: Write the failing test**

Append to `backend/tests/test_chatterbox_install.py`:

```python
def test_engine_env_installer_runs_given_subcommand():
    seen = {}
    def runner():
        seen["ran"] = True
        yield "line", None
        yield None, 0
    inst = EngineEnvInstaller("install-omnivoice", runner=runner)
    inst.start()
    _wait(inst)
    assert seen.get("ran") is True
    assert inst.status()["state"] == "installed"


def test_install_endpoint_supports_omnivoice():
    omni = EngineEnvInstaller("install-omnivoice", runner=_fake_runner(["hi"], 0))
    cb = ChatterboxInstaller(runner=_fake_runner([], 0))
    from fastapi import FastAPI
    from fastapi.testclient import TestClient
    from backend.api.engines import router
    app = FastAPI()
    app.include_router(router)
    app.state.engine_installers = {"chatterbox": cb, "omnivoice": omni}
    client = TestClient(app)
    assert client.get("/api/engines/omnivoice/install").json()["state"] == "not_installed"
    assert client.post("/api/engines/omnivoice/install").status_code == 200
    _wait(omni)
    assert "hi" in client.get("/api/engines/omnivoice/install").json()["log"]
    # Unknown / non-installable engine still 400s.
    assert client.get("/api/engines/kokoro/install").status_code == 400
```

Update the existing `_make_client` helper in this file to register the installer **registry** instead of the single attribute. Replace its body:

```python
def _make_client(installer):
    from fastapi import FastAPI
    from fastapi.testclient import TestClient
    from backend.api.engines import router
    app = FastAPI()
    app.include_router(router)
    app.state.engine_installers = {"chatterbox": installer}
    return TestClient(app)
```

And update the import at the top of the test file to pull in `EngineEnvInstaller`:

```python
from backend.services.chatterbox_install import (  # noqa: E402
    ChatterboxInstaller,
    EngineEnvInstaller,
    _format_progress,
)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd backend && ./venv/Scripts/python.exe -m pytest tests/test_chatterbox_install.py -k "engine_env or omnivoice" -v`
Expected: FAIL with `ImportError: cannot import name 'EngineEnvInstaller'`

- [ ] **Step 3: Implement**

In `backend/services/chatterbox_install.py`:
- Change `_default_runner` to take the subcommand:
```python
def _default_runner(repo_root: Path, subcommand: str) -> Iterator[RunnerItem]:
    """Spawn `python studio.py <subcommand>` and stream its output."""
    proc = subprocess.Popen(
        [sys.executable, "studio.py", subcommand],
        cwd=str(repo_root),
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,  # merge so a single stream is drained to EOF
        text=True,
        bufsize=1,
    )
    assert proc.stdout is not None
    for line in proc.stdout:
        yield line.rstrip("\n"), None
    proc.wait()
    yield None, proc.returncode
```
- Rename the class `ChatterboxInstaller` to `EngineEnvInstaller`, give it a `subcommand` first arg, and bind the default runner to it. Replace the class definition's `__init__` and keep the rest of the class body unchanged:
```python
class EngineEnvInstaller:
    """Thread-safe install state machine for an isolated engine env.

    Drives `python studio.py <subcommand>` in a daemon thread, streaming its
    merged stdout/stderr into a capped log buffer. State machine:
        not_installed -> installing -> installed | error
    """

    def __init__(
        self,
        subcommand: str,
        *,
        runner: Runner | None = None,
        repo_root: Path | None = None,
    ) -> None:
        self._repo_root = repo_root or _REPO_ROOT
        self._subcommand = subcommand
        self._runner: Runner = runner or (lambda: _default_runner(self._repo_root, self._subcommand))
        self._lock = threading.Lock()
        self._state = "not_installed"
        self._log: list[str] = []
        self._returncode: int | None = None
        self._thread: threading.Thread | None = None
```
- At the end of the file, add a thin backward-compatible alias so existing imports/usages keep working:
```python
class ChatterboxInstaller(EngineEnvInstaller):
    """Backward-compatible alias: the isolated Chatterbox env installer."""

    def __init__(self, *, runner: Runner | None = None, repo_root: Path | None = None) -> None:
        super().__init__("install-chatterbox", runner=runner, repo_root=repo_root)
```

In `backend/app.py`:
- Add the import next to `ChatterboxInstaller` (~line 40):
```python
from .services.chatterbox_install import ChatterboxInstaller, EngineEnvInstaller
```
- Replace the `app.state.chatterbox_installer = ChatterboxInstaller()` line (~line 174) with a registry:
```python
    app.state.engine_installers = {
        "chatterbox": ChatterboxInstaller(),
        "omnivoice": EngineEnvInstaller("install-omnivoice"),
    }
```

In `backend/api/deps.py`:
- Replace `get_chatterbox_installer` with a registry accessor:
```python
def get_engine_installers(request: Request) -> dict:
    return request.app.state.engine_installers  # type: ignore[no-any-return]
```

In `backend/api/engines.py`:
- Update the deps import (line 12) from `get_chatterbox_installer` to `get_engine_installers`:
```python
from .deps import get_engine_installers, get_engine_manager, get_model_downloader
```
- Replace the two install endpoints (the `install_status` and `start_install` functions) with registry-driven versions:
```python
@router.get("/{name}/install", response_model=InstallStatusModel)
def install_status(name: str, installers=Depends(get_engine_installers)) -> InstallStatusModel:
    """Current install state for an installable engine (Chatterbox / OmniVoice)."""
    inst = installers.get(name)
    if inst is None:
        raise HTTPException(status_code=400, detail=f"{name} is not installable")
    return InstallStatusModel(**inst.status())


@router.post("/{name}/install", response_model=InstallStatusModel)
def start_install(name: str, installers=Depends(get_engine_installers)) -> InstallStatusModel:
    """Start (or coalesce onto a running) install of an isolated engine env."""
    inst = installers.get(name)
    if inst is None:
        raise HTTPException(status_code=400, detail=f"{name} is not installable")
    return InstallStatusModel(**inst.start())
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd backend && ./venv/Scripts/python.exe -m pytest tests/test_chatterbox_install.py -v`
Expected: PASS (existing Chatterbox tests + the two new ones).

- [ ] **Step 5: Run the full backend suite**

Run: `cd backend && ./venv/Scripts/python.exe -m pytest tests/ -q`
Expected: PASS, 0 failures.

- [ ] **Step 6: Commit**

```bash
git add backend/services/chatterbox_install.py backend/app.py backend/api/deps.py backend/api/engines.py backend/tests/test_chatterbox_install.py
git commit -m "refactor: generalize installer + install endpoints for OmniVoice"
```

---

## Task 7: Frontend — generalize install dialog + wire OmniVoice

**Files:**
- Rename/replace: `frontend/src/components/InstallChatterboxDialog.tsx` → `frontend/src/components/InstallEngineDialog.tsx`
- Modify: `frontend/src/lib/api.ts`
- Modify: `frontend/src/App.tsx`
- Modify: `frontend/src/lib/engineHints.ts`

- [ ] **Step 1: Generalize the API client**

In `frontend/src/lib/api.ts`, replace `startChatterboxInstall` and `getChatterboxInstallStatus` (the two functions) with engine-parametrized versions:

```typescript
export async function startEngineInstall(name: string): Promise<InstallStatus> {
  return jsonOrThrow<InstallStatus>(
    await fetch(`${API_BASE}/engines/${encodeURIComponent(name)}/install`, { method: "POST" }),
  );
}

export async function getEngineInstallStatus(name: string): Promise<InstallStatus> {
  return jsonOrThrow<InstallStatus>(
    await fetch(`${API_BASE}/engines/${encodeURIComponent(name)}/install`),
  );
}
```

- [ ] **Step 2: Create the generalized dialog**

Create `frontend/src/components/InstallEngineDialog.tsx` with this content (it is the Chatterbox dialog parametrized by engine; copy text is engine-generic):

```tsx
import { useEffect, useRef, useState } from "react";
import { Loader2, X } from "lucide-react";
import { getEngineInstallStatus, startEngineInstall } from "@/lib/api";
import type { InstallStatus } from "@/types/models";

interface Props {
  isDark: boolean;
  engineName: string;
  displayName: string;
  onClose: () => void;
  onInstalled: () => void;
}

export function InstallEngineDialog({
  isDark,
  engineName,
  displayName,
  onClose,
  onInstalled,
}: Props) {
  const [status, setStatus] = useState<InstallStatus>({
    state: "installing",
    log: [],
    returncode: null,
  });
  const logRef = useRef<HTMLPreElement>(null);
  const timerRef = useRef<number | null>(null);

  const poll = async () => {
    try {
      const s = await getEngineInstallStatus(engineName);
      setStatus(s);
      if (s.state === "installing") {
        timerRef.current = window.setTimeout(() => void poll(), 1000);
      } else if (s.state === "installed") {
        onInstalled();
      }
    } catch (err) {
      setStatus((prev) => ({
        ...prev,
        state: "error",
        log: [...prev.log, err instanceof Error ? err.message : String(err)],
      }));
    }
  };

  const begin = async () => {
    setStatus({ state: "installing", log: [], returncode: null });
    try {
      await startEngineInstall(engineName);
    } catch (err) {
      setStatus({
        state: "error",
        log: [err instanceof Error ? err.message : String(err)],
        returncode: -1,
      });
      return;
    }
    void poll();
  };

  useEffect(() => {
    void begin();
    return () => {
      if (timerRef.current) window.clearTimeout(timerRef.current);
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  useEffect(() => {
    if (logRef.current) logRef.current.scrollTop = logRef.current.scrollHeight;
  }, [status.log]);

  const installing = status.state === "installing";
  const done = status.state === "installed";
  const failed = status.state === "error";

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/60 p-4">
      <div
        className={`w-full max-w-2xl rounded-xl border shadow-xl ${
          isDark ? "bg-zinc-900 border-zinc-800" : "bg-white border-gray-200"
        }`}
      >
        <div
          className={`flex items-center justify-between px-5 py-3 border-b ${
            isDark ? "border-zinc-800" : "border-gray-200"
          }`}
        >
          <div className="flex items-center gap-2">
            {installing && <Loader2 className="w-4 h-4 animate-spin text-teal-400" />}
            <span className={`font-semibold ${isDark ? "text-white" : "text-gray-900"}`}>
              {installing
                ? `Installing ${displayName}…`
                : done
                  ? `${displayName} installed`
                  : `${displayName} install failed`}
            </span>
          </div>
          <button
            type="button"
            onClick={onClose}
            disabled={installing}
            className={`p-1 rounded ${
              installing
                ? "opacity-40 cursor-not-allowed"
                : isDark
                  ? "hover:bg-zinc-800 text-zinc-400"
                  : "hover:bg-gray-100 text-gray-500"
            }`}
          >
            <X className="w-5 h-5" />
          </button>
        </div>

        <div className="p-5 space-y-3">
          <p className={`text-sm ${isDark ? "text-zinc-400" : "text-gray-600"}`}>
            {installing
              ? `Building the isolated ${displayName} environment (venv + PyTorch + model package). This takes a few minutes.`
              : done
                ? `Done. Close this dialog, then switch to ${displayName} in the engine menu.`
                : "The install failed. Review the log below and retry."}
          </p>
          <pre
            ref={logRef}
            className={`h-72 overflow-auto rounded-lg p-3 text-[11px] leading-relaxed font-mono whitespace-pre-wrap ${
              isDark ? "bg-black/40 text-zinc-300" : "bg-gray-50 text-gray-700"
            }`}
          >
            {status.log.length ? status.log.join("\n") : "Starting…"}
          </pre>
          <div className="flex justify-end gap-2">
            {failed && (
              <button
                type="button"
                onClick={() => void begin()}
                className="px-4 py-2 rounded-lg text-sm font-medium bg-teal-600 hover:bg-teal-500 text-white"
              >
                Retry
              </button>
            )}
            <button
              type="button"
              onClick={onClose}
              disabled={installing}
              className={`px-4 py-2 rounded-lg text-sm font-medium ${
                installing
                  ? "opacity-40 cursor-not-allowed bg-zinc-700 text-zinc-300"
                  : isDark
                    ? "bg-zinc-800 hover:bg-zinc-700 text-zinc-200"
                    : "bg-gray-100 hover:bg-gray-200 text-gray-700"
              }`}
            >
              {done ? "Done" : "Close"}
            </button>
          </div>
        </div>
      </div>
    </div>
  );
}
```

Then delete the old file:

```bash
git rm frontend/src/components/InstallChatterboxDialog.tsx
```

- [ ] **Step 3: Wire it in `App.tsx`**

In `frontend/src/App.tsx`:
- Replace the import `import { InstallChatterboxDialog } from "@/components/InstallChatterboxDialog";` with:
```typescript
import { InstallEngineDialog } from "@/components/InstallEngineDialog";
```
- Replace the state `const [installEngineOpen, setInstallEngineOpen] = useState(false);` with:
```typescript
  const [installEngine, setInstallEngine] = useState<string | null>(null);
```
- Replace the ActionBar prop `onInstallEngine={() => setInstallEngineOpen(true)}` with:
```tsx
          onInstallEngine={(name) => setInstallEngine(name)}
```
- Replace the dialog render block (currently `{installEngineOpen && ( <InstallChatterboxDialog ... /> )}`) with:
```tsx
        {installEngine && (
          <InstallEngineDialog
            isDark={isDark}
            engineName={installEngine}
            displayName={
              engines.find((e) => e.name === installEngine)?.display_name ?? installEngine
            }
            onClose={() => setInstallEngine(null)}
            onInstalled={() => {
              void refreshEngines();
            }}
          />
        )}
```

- [ ] **Step 4: Add OmniVoice CFG hints (hide the slider knob meaning)**

In `frontend/src/lib/engineHints.ts`, add an OmniVoice entry mirroring the Kokoro "no-op" treatment (OmniVoice has no CFG). After `CHATTERBOX_HINTS` (~line 93) add:

```typescript
// OmniVoice has no CFG knob — the engine ignores the field entirely. Show the
// familiar slider as a visual cue; the value never affects output.
const OMNIVOICE_HINTS: EngineCfgHints = {
  ...VIBEVOICE_HINTS,
  name: "omnivoice",
  hint:
    "OmniVoice does not use CFG — this slider is a no-op while OmniVoice is active. Voice fidelity comes from the reference clip.",
};
```

And add it to `HINTS_BY_ENGINE` (~line 95):

```typescript
const HINTS_BY_ENGINE: Record<string, EngineCfgHints> = {
  vibevoice: VIBEVOICE_HINTS,
  kokoro: KOKORO_HINTS,
  chatterbox: CHATTERBOX_HINTS,
  omnivoice: OMNIVOICE_HINTS,
};
```

- [ ] **Step 5: Typecheck + build**

Run: `cd frontend && npm run typecheck`
Expected: PASS. If an identifier like `engines`/`refreshEngines` is reported undefined in `App.tsx`, confirm the exact in-scope names (they are the same ones used by the existing engine handlers) and match them.

Run: `cd frontend && npm run build`
Expected: PASS (tsc + vite build succeed).

- [ ] **Step 6: Commit**

```bash
git add frontend/src/components/InstallEngineDialog.tsx frontend/src/lib/api.ts frontend/src/App.tsx frontend/src/lib/engineHints.ts
git commit -m "feat: generalize install dialog + wire OmniVoice into the UI"
```

---

## Final verification

- [ ] **Backend suite green:** `cd backend && ./venv/Scripts/python.exe -m pytest tests/ -q` → all pass.
- [ ] **Frontend green:** `cd frontend && npm run typecheck && npm run build` → both pass.
- [ ] **Manual smoke (optional; requires building the venv):** `python studio.py install-omnivoice` builds `backend/venv-omnivoice`; then `python studio.py start --dev`, open the engine menu — OmniVoice shows **Install OmniVoice** before install and **Switch to OmniVoice** after; switching + generating with a selected reference voice produces 24 kHz cloned audio. Chatterbox's Install flow still works unchanged.
- [ ] **Update `CLAUDE.md`** (per the maintain-CLAUDE.md memory): note OmniVoice as the fourth engine (isolated `venv-omnivoice` worker, `transformers>=5.3`/torch-2.8 conflict, `install-omnivoice`, clone-only in Spec A), and that the installer/endpoint/dialog are now generic over installable engines.

---

## Self-Review (completed by plan author)

**Spec coverage:**
- Isolated worker + proxy (clone/design/auto in worker; clone in proxy) → Tasks 3, 4. ✓
- On-demand install (`install-omnivoice`, `.omnivoice-ready`, cu128 torch) → Tasks 1, 2. ✓
- Installer/API/dialog generalization → Tasks 6, 7. ✓
- Engine registration + config → Task 5. ✓
- CFG slider hidden / no-op for OmniVoice → Task 7. ✓
- Tests: proxy (stub worker + `_build_synth_msg` + installed-marker), envdetect mapping, studio helpers/dispatch, installer generalization, engine-manager registration; frontend typecheck/build → Tasks 1–7. ✓
- Chatterbox untouched behaviorally (alias preserves `ChatterboxInstaller()`; its tests updated only for the registry shape) → Task 6. ✓
- Spec B deferral (no `instruct`/auto/toggle UI; worker ready for them) → respected throughout. ✓

**Placeholder scan:** none — every code step carries full code; the one conditional (`cli.py`) ships with an exact detection command and concrete instruction, not a vague "handle it".

**Type/name consistency:** worker message keys (`op/mode/text/ref_audio/ref_text/instruct/out_wav/speed/num_step`) are identical across `omnivoice_worker.py` (Task 3) and `OmniVoiceEngine._build_synth_msg` (Task 4). `EngineEnvInstaller(subcommand, *, runner, repo_root)` + `ChatterboxInstaller` alias are consistent across the service, `app.py`, and tests (Task 6). `engine_installers` registry key shape is consistent across `app.py`, `deps.py`, `engines.py`, and both backend tests. `.omnivoice-ready` marker name matches between `studio.py` (Task 2) and the proxy's `_ready_marker` (Task 4). `startEngineInstall`/`getEngineInstallStatus` + `InstallEngineDialog(engineName, displayName)` are consistent across `api.ts`, the dialog, and `App.tsx` (Task 7).
