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


class OmniVoiceEngine(Engine):
    """Proxy to an OmniVoice worker running in backend/venv-omnivoice."""

    name = "omnivoice"
    display_name = "OmniVoice"
    license = "Apache-2.0"
    model_url = "https://huggingface.co/k2-fsa/OmniVoice"
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
        # backend/venv-omnivoice/.omnivoice-ready
        return self._worker_python.parent.parent / ".omnivoice-ready"

    def downloaded(self) -> bool:
        # OmniVoice weights live in the shared HF cache (backend/models/), which
        # both the main process and the isolated worker read. Probe it so the UI
        # can offer a Download (with progress) before the first worker load.
        from ..model_cache import model_downloaded

        return model_downloaded(self._model_id)

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

    # -- capabilities
    def sample_rate(self) -> int:
        return 24000

    def max_speakers(self) -> int:
        return 1

    def supports_voice_cloning(self) -> bool:
        return True

    def supports_streaming(self) -> bool:
        return False

    def supports_voice_modes(self) -> bool:
        return True

    def default_cfg_scale(self) -> float | None:
        return None  # OmniVoice has no CFG knob

    def available_voices(self) -> list:
        return []

    # -- synthesis
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

    # -- internals
    def _exchange(self, msg: dict, expect_reply: bool = True) -> dict:
        """Send one JSON line; read one JSON reply line. Thread-safe."""
        with self._lock:
            if self._proc is None or self._proc.stdin is None or self._proc.stdout is None:
                raise RuntimeError("OmniVoice worker is not running")
            try:
                self._proc.stdin.write(json.dumps(msg) + "\n")
                self._proc.stdin.flush()
            except (BrokenPipeError, OSError) as exc:
                self._kill()
                raise RuntimeError(f"OmniVoice worker pipe broke: {exc}") from exc
            if not expect_reply:
                return {"ok": True}
            # Read until a JSON reply. Tolerate non-protocol noise on stdout
            # (library banners / model-download progress) by skipping any line
            # that isn't valid JSON, rather than crashing on it.
            while True:
                line = self._proc.stdout.readline()
                if not line:
                    # Worker closed stdout (crashed/exited). Let the stderr
                    # drain thread catch up so we can include the reason.
                    if self._stderr_thread is not None:
                        self._stderr_thread.join(timeout=1.0)
                    stderr = self._recent_stderr()
                    self._kill()
                    raise RuntimeError(
                        "OmniVoice worker closed unexpectedly"
                        + (f": {stderr}" if stderr else "")
                    )
                stripped = line.strip()
                if not stripped:
                    continue
                try:
                    return json.loads(stripped)
                except json.JSONDecodeError:
                    log.debug("omnivoice worker non-protocol stdout: %s", stripped[:200])
                    continue

    def _start_stderr_drain(self) -> None:
        """Continuously drain the worker's stderr on a daemon thread so its
        pipe buffer never fills and deadlocks our blocking stdout reads."""
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
