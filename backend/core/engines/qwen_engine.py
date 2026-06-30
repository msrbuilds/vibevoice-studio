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
