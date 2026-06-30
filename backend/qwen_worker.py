#!/usr/bin/env python3
"""Qwen3-TTS CustomVoice worker — runs INSIDE backend/venv-qwen.

Speaks newline-delimited JSON on stdin/stdout. The parent process
(backend/core/engines/qwen_engine.py) drives it. All human-readable logging
goes to STDERR so it never corrupts the stdout protocol.

Protocol (one JSON object per line):
  stdin  {"op":"load","device":"cuda","model_id":"Qwen/Qwen3-TTS-12Hz-1.7B-CustomVoice"}
         {"op":"synth","mode":"custom|clone|design","text":..,"out_wav":<path>,
          "speaker":<str?>,"language":<str>,"instruct":<str?>,
          "ref_audio":<path?>,"ref_text":<str?>,
          "temperature":<float?>,"top_p":<float?>,"top_k":<int?>,
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


# generate_custom_voice accepts a fixed lowercase vocabulary. Map the UI's
# display names ("English") and the voice's 2-letter language codes ("en", which
# SynthService falls back to when no language is explicitly selected) onto it.
# Anything unrecognized → "auto" (let the model detect).
_QWEN_LANG_ALIASES = {
    "auto": "auto",
    "zh": "chinese", "chinese": "chinese",
    "en": "english", "english": "english",
    "ja": "japanese", "japanese": "japanese",
    "ko": "korean", "korean": "korean",
    "de": "german", "german": "german",
    "fr": "french", "french": "french",
    "ru": "russian", "russian": "russian",
    "pt": "portuguese", "portuguese": "portuguese",
    "es": "spanish", "spanish": "spanish",
    "it": "italian", "italian": "italian",
}


def _normalize_language(language) -> str:
    """Map a UI language code/name ('English', 'en', 'Auto') to the lowercase
    vocabulary generate_custom_voice accepts. Unknown / empty → 'auto'."""
    return _QWEN_LANG_ALIASES.get((language or "auto").strip().lower(), "auto")


def _common_kwargs(req: dict) -> dict:
    """Quality kwargs + max_new_tokens shared by every mode."""
    text = (req.get("text") or "").strip()
    if not text:
        raise ValueError("text must be non-empty")
    kw: dict = {"text": text, "language": _normalize_language(req.get("language"))}
    for key in ("temperature", "top_p", "top_k", "repetition_penalty"):
        if req.get(key) is not None:
            kw[key] = req[key]
    kw["max_new_tokens"] = _auto_max_new_tokens(text)
    return kw


def _build_call(req: dict) -> tuple[str, dict]:
    """Return (op, kwargs) for the requested mode. op is the method suffix:
    'custom' -> generate_custom_voice, 'clone' -> generate_voice_clone,
    'design' -> generate_voice_design. Defaults to custom (built-in voice)."""
    mode = (req.get("mode") or "custom").strip().lower()
    kw = _common_kwargs(req)
    if mode == "clone":
        ref_audio = req.get("ref_audio")
        if not ref_audio:
            raise ValueError("clone mode requires ref_audio")
        kw["ref_audio"] = ref_audio
        ref_text = (req.get("ref_text") or "").strip()
        if ref_text:
            kw["ref_text"] = ref_text
            kw["x_vector_only_mode"] = False
        else:
            kw["x_vector_only_mode"] = True
        return "clone", kw
    if mode == "design":
        instruct = (req.get("instruct") or "").strip()
        if not instruct:
            raise ValueError("design mode requires a non-empty instruct/style")
        kw["instruct"] = instruct
        return "design", kw
    speaker = req.get("speaker")
    if not speaker:
        raise ValueError("custom mode requires a speaker (one of the 9 Qwen voices)")
    kw["speaker"] = str(speaker).strip().lower()
    instruct = (req.get("instruct") or "").strip()
    if instruct:
        kw["instruct"] = instruct
    return "custom", kw


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
            op, kwargs = _build_call(req)
        except ValueError as exc:
            return {"ok": False, "error": str(exc)}
        if req.get("seed") is not None:
            try:
                import torch
                torch.manual_seed(int(req["seed"]))
            except Exception:  # noqa: BLE001
                pass
        method = {
            "custom": "generate_custom_voice",
            "clone": "generate_voice_clone",
            "design": "generate_voice_design",
        }[op]
        t0 = time.perf_counter()
        try:
            wavs, sr = getattr(self._model, method)(**kwargs)
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
