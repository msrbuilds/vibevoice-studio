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
    d = (device or "auto").lower()
    if d == "auto":
        # The worker holds the torch that actually runs the model, so it is the
        # authority on CUDA availability. Fall back to CPU on GPU-less hosts
        # instead of forcing cuda and crashing.
        try:
            import torch
            d = "cuda" if torch.cuda.is_available() else "cpu"
        except Exception:  # noqa: BLE001
            d = "cpu"
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
        return {"ok": True, "device": device}

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
