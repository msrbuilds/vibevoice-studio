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
    d = (device or "auto").lower()
    if d == "auto":
        # The worker holds the torch that actually runs the model, so it is the
        # authority on CUDA availability. Fall back to CPU on GPU-less hosts
        # instead of forcing cuda. (VoxCPM auto-selects its own device, so this
        # is mainly for honest reporting.)
        try:
            import torch
            d = "cuda" if torch.cuda.is_available() else "cpu"
        except Exception:  # noqa: BLE001
            d = "cpu"
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
            # NOTE: VoxCPM.from_pretrained auto-selects the device; `device` here is
            # advisory only. If a future voxcpm version accepts an explicit device arg,
            # pass it here (confirmed when the isolated venv is built).
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
        _log(f"[voxcpm-worker] model loaded (requested device={device!r}; VoxCPM selects its own device), sr={self._sample_rate}")
        return {"ok": True, "device": device}

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
