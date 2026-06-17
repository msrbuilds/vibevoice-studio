"""ModelManager: process-level singleton wrapping the VibeVoice model + processor."""

from __future__ import annotations

import logging
from threading import Lock
from typing import Any

import torch

# These imports come from the `vibevoice` package, installed from
# https://github.com/vibevoice-community/VibeVoice (the community fork of
# Microsoft's now-removed VibeVoice repo).
from vibevoice.modular.modeling_vibevoice_inference import (
    VibeVoiceForConditionalGenerationInference,
)
from vibevoice.processor.vibevoice_processor import VibeVoiceProcessor

from .device import resolve_device

log = logging.getLogger(__name__)


class ModelManager:
    """Loads the VibeVoice 1.5B model once and exposes processor/model/sampling_rate.

    Uses a thread lock so concurrent load() calls are idempotent.
    """

    def __init__(self, model_id: str, device_request: str) -> None:
        self._model_id = model_id
        self._device_request = device_request
        self._lock = Lock()

        self._device: torch.device | None = None
        self._dtype: torch.dtype | None = None
        self._attn_impl: str | None = None
        self._processor: VibeVoiceProcessor | None = None
        self._model: VibeVoiceForConditionalGenerationInference | None = None
        self._sampling_rate: int | None = None
        self._ddpm_steps: int = 10  # default; configurable via set_ddpm_inference_steps

    @property
    def is_loaded(self) -> bool:
        return self._model is not None and self._processor is not None

    @property
    def model_id(self) -> str:
        return self._model_id

    @property
    def device(self) -> torch.device:
        if self._device is None:
            raise RuntimeError("Model not loaded")
        return self._device

    @property
    def device_name(self) -> str:
        if self._device is None:
            return "unloaded"
        return self._device.type

    @property
    def dtype_name(self) -> str:
        if self._dtype is None:
            return "unknown"
        return {
            torch.float32: "float32",
            torch.float16: "float16",
            torch.bfloat16: "bfloat16",
        }.get(self._dtype, str(self._dtype).removeprefix("torch."))

    @property
    def attn_impl(self) -> str:
        return self._attn_impl or "unknown"

    @property
    def sampling_rate(self) -> int:
        if self._sampling_rate is None:
            raise RuntimeError("Model not loaded")
        return self._sampling_rate

    @property
    def processor(self) -> VibeVoiceProcessor:
        if self._processor is None:
            raise RuntimeError("Model not loaded")
        return self._processor

    @property
    def model(self) -> VibeVoiceForConditionalGenerationInference:
        if self._model is None:
            raise RuntimeError("Model not loaded")
        return self._model

    def load(self) -> None:
        """Load the model and processor. Idempotent — safe to call multiple times."""
        with self._lock:
            if self.is_loaded:
                log.info("Model already loaded; skipping.")
                return

            log.info("Loading processor from %s …", self._model_id)
            self._processor = VibeVoiceProcessor.from_pretrained(self._model_id)

            device, dtype, attn_impl = resolve_device(self._device_request)
            self._device = device
            self._dtype = dtype
            self._attn_impl = attn_impl

            log.info(
                "Loading model weights (device=%s, dtype=%s, attn=%s) …",
                device,
                self.dtype_name,
                attn_impl,
            )

            try:
                if device.type == "mps":
                    # MPS: load to CPU first, then move (device_map=None on mps is safer)
                    self._model = VibeVoiceForConditionalGenerationInference.from_pretrained(
                        self._model_id,
                        torch_dtype=dtype,
                        attn_implementation=attn_impl,
                        device_map=None,
                    )
                    self._model.to("mps")
                else:
                    self._model = VibeVoiceForConditionalGenerationInference.from_pretrained(
                        self._model_id,
                        torch_dtype=dtype,
                        device_map=device,
                        attn_implementation=attn_impl,
                    )
            except Exception as exc:
                if attn_impl != "sdpa":
                    log.warning("Failed with %s; retrying with sdpa. Error: %s", attn_impl, exc)
                    self._attn_impl = "sdpa"
                    if device.type == "mps":
                        self._model = VibeVoiceForConditionalGenerationInference.from_pretrained(
                            self._model_id,
                            torch_dtype=dtype,
                            attn_implementation="sdpa",
                            device_map=None,
                        )
                        self._model.to("mps")
                    else:
                        self._model = VibeVoiceForConditionalGenerationInference.from_pretrained(
                            self._model_id,
                            torch_dtype=dtype,
                            device_map=device,
                            attn_implementation="sdpa",
                        )
                else:
                    raise

            self._model.eval()

            # Set a reasonable default for DDPM inference steps. The community
            # example uses 10; lower (5-7) is faster but slightly lower quality.
            self._model.set_ddpm_inference_steps(num_steps=self._ddpm_steps)

            # Sampling rate lives on the processor's audio processor; read it back
            # rather than hardcoding 24000.
            self._sampling_rate = self._detect_sampling_rate(self._processor)

            log.info(
                "Model ready. sampling_rate=%d Hz, ddpm_steps=%d, attn=%s",
                self._sampling_rate,
                self._ddpm_steps,
                self._attn_impl,
            )

    def unload(self) -> None:
        """Free GPU memory. Idempotent."""
        with self._lock:
            self._model = None
            self._processor = None
            if torch.cuda.is_available():
                torch.cuda.empty_cache()

    def set_ddpm_steps(self, steps: int) -> None:
        """Update the DDPM inference step count for subsequent generations."""
        if steps < 1:
            return
        with self._lock:
            self._ddpm_steps = int(steps)
            if self._model is not None:
                self._model.set_ddpm_inference_steps(num_steps=self._ddpm_steps)

    @staticmethod
    def _detect_sampling_rate(processor: Any) -> int:
        """Pull sampling rate from wherever the processor hides it."""
        for attr in ("audio_processor", "feature_extractor"):
            ap = getattr(processor, attr, None)
            if ap is None:
                continue
            sr = getattr(ap, "sampling_rate", None)
            if isinstance(sr, int) and sr > 0:
                return sr
        sr = getattr(processor, "sampling_rate", None)
        if isinstance(sr, int) and sr > 0:
            return sr
        raise RuntimeError("Could not detect sampling_rate on VibeVoiceProcessor")
