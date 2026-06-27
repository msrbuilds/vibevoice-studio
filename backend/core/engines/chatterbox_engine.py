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
        # stderr is drained on a background thread so a chatty worker
        # (CUDA init, warnings, tqdm) can never fill its stderr pipe buffer
        # and deadlock against our blocking stdout reads. We keep the last
        # N lines for diagnostics when the worker dies.
        self._stderr_tail: collections.deque[str] = collections.deque(maxlen=200)
        self._stderr_thread: threading.Thread | None = None

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
        self._start_stderr_drain()
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
                self._exchange({"op": "shutdown"}, expect_reply=False)
        except Exception:  # noqa: BLE001
            pass
        self._kill()

    def is_loaded(self) -> bool:
        return self._proc is not None and self._proc.poll() is None

    def installed(self) -> bool:
        # The venv's Python exists right after `python -m venv`, before any
        # package is installed, so checking for it would report a half-built
        # (interrupted) install as complete. Gate on the ready marker that
        # studio.py writes only after the full install succeeds.
        return self._ready_marker().is_file()

    def _ready_marker(self) -> Path:
        # backend/venv-chatterbox/.chatterbox-ready (worker_python is
        # venv-chatterbox/{Scripts|bin}/python[.exe]).
        return self._worker_python.parent.parent / ".chatterbox-ready"

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
                        "Chatterbox worker closed unexpectedly"
                        + (f": {stderr}" if stderr else "")
                    )
                stripped = line.strip()
                if not stripped:
                    continue
                try:
                    return json.loads(stripped)
                except json.JSONDecodeError:
                    log.debug("chatterbox worker non-protocol stdout: %s", stripped[:200])
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
