"""VibeVoice 1.5B engine — wraps the existing ModelManager + synthesis flow."""

from __future__ import annotations

import logging
import re
import tempfile
import time
from pathlib import Path
from typing import Any

import numpy as np
import soundfile as sf

from ..model import ModelManager
from . import Engine, EngineResult, EngineSynthRequest, wrap_pcm_as_wav

log = logging.getLogger(__name__)


# Match "Speaker N:" at the start of a line (case-insensitive). Used to
# decide whether the input is a multi-speaker script.
_SPEAKER_TAG_RE = re.compile(r"^\s*Speaker\s*\d+\s*:", re.IGNORECASE | re.MULTILINE)


def _has_speaker_tags(text: str) -> bool:
    return bool(_SPEAKER_TAG_RE.search(text))


def _normalize_speaker_tags(text: str) -> str:
    """Same logic as the previous SynthService._normalize_speaker_tags."""
    name_to_idx: dict[str, int] = {}
    lines = text.splitlines()
    out: list[str] = []
    current_idx: int | None = None
    prefix_re = re.compile(r"^([Ss]peaker\s*\d+|[A-Z][\w.\- ]*?)\s*:\s*(.*)$")

    def _assign(name: str) -> int:
        if name not in name_to_idx:
            name_to_idx[name] = len(name_to_idx) + 1
        return name_to_idx[name]

    for line in lines:
        m = prefix_re.match(line.strip())
        if m:
            original_name = m.group(1).strip()
            rest = m.group(2).strip()
            idx = _assign(original_name)
            current_idx = idx
            out.append(f"Speaker {idx}: {rest}")
        else:
            if current_idx is not None and line.strip():
                out.append(f"Speaker {current_idx}: {line.strip()}")
            elif line.strip():
                idx = _assign("Anonymous")
                current_idx = idx
                out.append(f"Speaker {idx}: {line.strip()}")
    return "\n".join(out)


def _build_script(text: str) -> str:
    """Build the canonical `Speaker N: <text>` script for the model."""
    if not _has_speaker_tags(text):
        non_empty = [ln.strip() for ln in text.splitlines() if ln.strip()]
        if not non_empty:
            non_empty = [text.strip()]
        return "\n".join(f"Speaker 1: {ln}" for ln in non_empty)
    return _normalize_speaker_tags(text)


class VibeVoiceEngine(Engine):
    """The VibeVoice 1.5B community fork.

    Backed by the `vibevoice` PyPI package (loaded from
    `vibevoice-community/VibeVoice`). Multi-speaker, supports voice
    cloning from short reference clips, deterministic inference.
    """

    name = "vibevoice"
    display_name = "VibeVoice 1.5B"
    license = "MIT"
    model_url = "https://huggingface.co/microsoft/VibeVoice-1.5B"
    description = "Microsoft's 1.5B multilingual voice-cloning model. ~5.4 GB."

    def __init__(
        self,
        model_id: str,
        device_request: str,
        max_text_chars: int = 5000,
        default_cfg_scale: float = 1.3,
    ) -> None:
        self._model_manager = ModelManager(
            model_id=model_id,
            device_request=device_request,
        )
        # Cache on the engine too so engine_info() can report the
        # intended device before the model is loaded (otherwise the
        # UI sees "unknown" until first inference).
        self._device_request = device_request
        self._max_text_chars = max_text_chars
        self._default_cfg_scale = default_cfg_scale

    # -- lifecycle
    def load(self) -> None:
        self._model_manager.load()

    def unload(self) -> None:
        self._model_manager.unload()

    def is_loaded(self) -> bool:
        return self._model_manager.is_loaded

    def downloaded(self) -> bool:
        from ..model_cache import model_downloaded

        return model_downloaded(self._model_manager.model_id)

    def engine_info(self) -> dict[str, Any]:
        """Surface VibeVoice's ModelManager fields to /api/config."""
        mm = self._model_manager
        if not mm.is_loaded:
            # ModelManager hasn't loaded yet — show the requested device
            # rather than "unknown" so the UI can still hint at the
            # intended runtime.
            return {
                "model_id": mm.model_id,
                "device": self._device_request,
                "dtype": "unknown",
                "attn_implementation": "unknown",
            }
        return {
            "model_id": mm.model_id,
            "device": mm.device_name,
            "dtype": mm.dtype_name,
            "attn_implementation": mm.attn_impl,
        }

    # -- capabilities
    def sample_rate(self) -> int:
        return self._model_manager.sampling_rate

    def max_speakers(self) -> int:
        return 4

    def supports_voice_cloning(self) -> bool:
        return True

    def supports_streaming(self) -> bool:
        # The vibevoice package exposes model.generate() as a single
        # call returning the full speech tensor. Step-level streaming
        # would require hooking into T3's diffusion loop, which the
        # upstream library doesn't expose in this version. Fall back
        # to /api/synthesize for the full result.
        return False

    def default_cfg_scale(self) -> float | None:
        return self._default_cfg_scale

    def available_voices(self) -> list:
        # VibeVoice has no built-in voice catalog; voices come from the
        # filesystem (VoiceRegistry). Returning [] here tells the engine
        # manager to look in the registry for this engine's voices.
        return []

    # -- synthesis
    def synthesize(self, req: EngineSynthRequest) -> EngineResult:
        if not self._model_manager.is_loaded:
            raise RuntimeError("VibeVoice model is not loaded")

        text = (req.text or "").strip()
        if not text:
            raise ValueError("text must be non-empty")
        if len(text) > self._max_text_chars:
            raise ValueError(
                f"text exceeds {self._max_text_chars} chars (got {len(text)})"
            )
        if not req.voice_id:
            raise ValueError("voice_id is required for VibeVoice")

        script = _build_script(text)
        cfg = req.cfg_scale if req.cfg_scale is not None else self._default_cfg_scale
        if req.inference_steps and req.inference_steps > 0:
            self._model_manager.set_ddpm_steps(req.inference_steps)

        voice_path = Path(req.reference_audio) if req.reference_audio else None
        voice_paths = [voice_path] if voice_path else None
        # If no reference audio is provided we use the requested voice_id
        # to look one up via the registry; here we assume the engine is
        # always called with reference_audio already resolved by the caller.
        if voice_paths is None:
            raise ValueError("VibeVoice requires a reference audio path")

        processor = self._model_manager.processor
        model = self._model_manager.model
        sr = self._model_manager.sampling_rate

        inputs = processor(
            text=[script],
            voice_samples=[[str(p) for p in voice_paths]],
            padding=True,
            return_tensors="pt",
            return_attention_mask=True,
        )
        device = self._model_manager.device
        moved: dict[str, Any] = {}
        for k, v in inputs.items():
            if hasattr(v, "to"):
                moved[k] = v.to(device)
            else:
                moved[k] = v

        import torch

        t0 = time.perf_counter()
        with torch.inference_mode():
            output = model.generate(
                **moved,
                tokenizer=processor.tokenizer,
                cfg_scale=cfg,
                max_new_tokens=None,
                is_prefill=not req.disable_prefill,
            )
        inference_ms = int((time.perf_counter() - t0) * 1000)

        speech = getattr(output, "speech_outputs", None)
        if speech is None or len(speech) == 0 or speech[0] is None:
            raise RuntimeError("VibeVoice produced no audio")
        wav_tensor = speech[0]

        wav_bytes, duration_sec = _tensor_to_wav_bytes(wav_tensor, sr)
        return EngineResult(
            wav_bytes=wav_bytes,
            sample_rate=sr,
            duration_sec=duration_sec,
            inference_ms=inference_ms,
        )


def _tensor_to_wav_bytes(tensor, sample_rate: int) -> tuple[bytes, float]:
    """Save a torch tensor to a temp file via soundfile, read as bytes."""
    import numpy as np
    import torch

    if hasattr(tensor, "detach"):
        arr = tensor.detach().cpu()
        if hasattr(arr, "to") and arr.is_floating_point():
            arr = arr.to(torch.float32)
        arr = arr.numpy()
    else:
        arr = np.asarray(tensor, dtype=np.float32)
    if arr.ndim > 1:
        arr = arr.reshape(-1)
    np.clip(arr, -1.0, 1.0, out=arr)
    duration = float(arr.size) / float(sample_rate)

    with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as tmp:
        tmp_path = Path(tmp.name)
    try:
        sf.write(str(tmp_path), arr, samplerate=sample_rate, subtype="PCM_16")
        wav_bytes = tmp_path.read_bytes()
    finally:
        try:
            tmp_path.unlink()
        except OSError:
            pass
    return wav_bytes, duration
