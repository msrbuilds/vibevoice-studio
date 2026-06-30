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
    license = "Apache-2.0"
    model_url = "https://huggingface.co/openbmb/VoxCPM2"
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
        # The device the worker actually resolved "auto" to (cuda/cpu), reported
        # back on load. None until the first successful load.
        self._resolved_device: str | None = None

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
            # Pass the raw request (incl. "auto") through — the worker holds the
            # torch that runs the model and resolves auto→cuda/cpu honestly.
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
            resp = self._exchange(
                {"op": "load", "device": self._device_request, "model_id": self._model_id}
            )
            if not resp.get("ok"):
                err = resp.get("error", "unknown error")
                self._kill()
                raise RuntimeError(f"VoxCPM worker failed to load: {err}")
            self._resolved_device = resp.get("device") or self._device_request

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
        # Report the device the worker actually resolved to once loaded; before
        # load, echo the request (may be "auto") rather than guessing "cuda".
        device = self._resolved_device or self._device_request
        dtype = "bfloat16" if str(device).startswith("cuda") else "float32"
        return {
            "model_id": self._model_id,
            "device": device,
            "dtype": dtype,
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
