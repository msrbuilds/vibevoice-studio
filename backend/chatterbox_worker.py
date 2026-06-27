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
import os
import sys
import time
import wave

# Protocol output. main() replaces this with the REAL stdout and then points
# fd 1 (Python AND C-level) at stderr, so anything the model load prints
# (banners, HF/tqdm progress) goes to stderr and can never corrupt the
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
    global _OUT
    # Reserve the real stdout for protocol replies, then point fd 1 — for both
    # Python prints and C-level/library writes — at stderr so model-load noise
    # can't corrupt the JSON stream the parent reads.
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
