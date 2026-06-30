"""TTS engine abstraction.

Each engine is a self-contained model + processor pair that can synthesize
speech from a `SynthRequest` and return a `SynthResult`. Engines are
pluggable: the active engine is selected at runtime via
`EngineManager.activate(name)`.

The `Engine` ABC is intentionally narrow — just enough to swap one TTS
backend for another. Higher-level concerns (caching, threading, script
formatting) live in `SynthService` and are engine-agnostic.
"""

from __future__ import annotations

import abc
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

import numpy as np

if TYPE_CHECKING:
    from ..model import ModelManager
    from ...services.voices import VoiceInfo


@dataclass
class EngineResult:
    """Engine-agnostic synthesis result.

    Mirrors the public fields of `SynthService.SynthResult` so the
    SynthService can return either without special-casing.

    `is_final` is True on the last chunk of a streaming response,
    used by the WebSocket route to inject inference_ms into the
    closing "end" frame instead of forwarding as audio. False (or
    unset) for normal single-shot results and intermediate streaming
    chunks.
    """

    wav_bytes: bytes
    sample_rate: int
    duration_sec: float
    inference_ms: int
    is_final: bool = False


@dataclass
class EngineSynthRequest:
    """Engine-agnostic synthesis request.

    Engines may ignore fields they don't understand (e.g. Kokoro doesn't
    support voice cloning, so `reference_audio` is optional; only
    Chatterbox uses `cfg_weight`/`exaggeration`/`language_id`).
    """

    text: str
    voice_id: str
    speed: float = 1.0
    cfg_scale: float | None = None  # engines that don't use CFG ignore it
    # Optional reference audio for engines that support voice cloning.
    # Pass a file path; engines that don't need it (Kokoro) ignore.
    reference_audio: str | None = None
    # Optional inference overrides
    inference_steps: int | None = None
    disable_prefill: bool = False
    # --- Chatterbox Multilingual V3 only ---
    # Classifier-free guidance weight (0.0–1.0). Lower = more natural,
    # higher = stricter voice adherence. Default 0.5.
    cfg_weight: float | None = None
    # Voice expressiveness / exaggeration (0.0–1.0+). Higher = more
    # dramatic. Default 0.5.
    exaggeration: float | None = None
    # BCP-47-ish short language code (e.g. "en", "fr", "ur", "zh"). Used
    # by Chatterbox Multilingual to pick the right text tokenizer. Falls
    # back to the engine's default when None.
    language_id: str | None = None
    # --- OmniVoice only (other engines ignore) ---
    # Voice generation mode: "clone" (ref_audio), "design" (instruct), "auto".
    voice_mode: str | None = None
    # Free-text speaker-attribute prompt used when voice_mode == "design".
    instruct: str | None = None
    # --- VoxCPM only (other engines ignore) ---
    # Transcript of the reference clip, enabling VoxCPM "ultimate cloning"
    # (prompt_wav + prompt_text). Resolved per-voice by SynthService.
    reference_text: str | None = None
    # --- Qwen3-TTS CustomVoice only (other engines ignore) ---
    # HF generation sampling params forwarded to generate_custom_voice.
    temperature: float | None = None
    top_p: float | None = None
    top_k: int | None = None
    repetition_penalty: float | None = None
    seed: int | None = None


class Engine(abc.ABC):
    """Abstract base class for a TTS engine.

    Lifecycle: an engine is constructed at app start, NOT loaded. The
    active engine is loaded lazily on first use (or eagerly via
    `load()` if you want a startup warmup). Other engines stay unloaded
    to keep memory usage low.
    """

    #: Stable string id used in API calls and config (e.g. "vibevoice", "kokoro").
    name: str = "base"
    #: Human-readable display name shown in the UI.
    display_name: str = "Base Engine"
    #: Short blurb shown next to the name in the engine selector.
    description: str = ""

    @abc.abstractmethod
    def load(self) -> None:
        """Load model weights + processor. Idempotent. Raises on failure."""

    @abc.abstractmethod
    def unload(self) -> None:
        """Free GPU/RAM. Idempotent."""

    @abc.abstractmethod
    def is_loaded(self) -> bool:
        """True if the model + processor are in memory and ready to serve."""

    @abc.abstractmethod
    def synthesize(self, req: EngineSynthRequest) -> EngineResult:
        """Run inference. Blocking. Engine must be loaded."""

    def supports_streaming(self) -> bool:
        """True if the engine can deliver audio in chunks via
        `stream_synthesize()`. Default False — engines that produce
        a single tensor at the end of inference (VibeVoice, Chatterbox)
        should leave this as False. The WebSocket route uses this to
        decide whether to call `stream_synthesize()` or return a
        "not supported" error.
        """
        return False

    def installed(self) -> bool:
        """True if the engine's runtime is present and usable. Engines that
        live in the main venv are always installed; engines that need a
        separate environment (Chatterbox) override this."""
        return True

    def downloaded(self) -> bool:
        """True if the engine's model weights are present in the local cache.

        Engines that fetch large weights lazily (VibeVoice, Kokoro) override
        this so the UI can offer a download-with-progress flow before the
        first load. Default True: engines without a separate weight download
        (or that manage it elsewhere, like Chatterbox) never trigger that UI.
        """
        return True

    def supports_voice_modes(self) -> bool:
        """True if the engine offers per-speaker Clone/Design/Auto modes
        (an empty voice means "design" or "auto", not an error). OmniVoice
        and VoxCPM override this; every other engine is always voice-based."""
        return False

    def supports_style_clone(self) -> bool:
        """True if the engine accepts an inline style prompt WHILE cloning a
        reference voice (VoxCPM "controllable cloning"). OmniVoice's design
        prompt only applies without a reference, so it leaves this False."""
        return False

    def supports_style_prompt(self) -> bool:
        """True if the engine accepts an always-available free-text style
        prompt alongside a built-in voice (Qwen CustomVoice), independent of
        any Clone/Design/Auto toggle. The value rides the `instruct` field."""
        return False

    def languages(self) -> list[dict[str, str]]:
        """UI language options as [{"code","label"}].

        Default empty = the engine shows no language selector (reference-
        driven like VibeVoice, or auto-detected like OmniVoice). Cloning
        engines that accept a language param (Chatterbox) and built-in-voice
        engines whose voices are language-grouped (Kokoro) override this.
        """
        return []

    def stream_synthesize(
        self, req: EngineSynthRequest
    ) -> Iterator[EngineResult]:
        """Optional streaming inference. Yield one EngineResult per
        audio chunk (typically one per model decoder step). The WebSocket
        route forwards each yielded chunk as a binary frame.

        The default implementation raises EngineStreamingNotSupported
        so engines that don't override this method give a clean error
        instead of failing silently. Override + return True from
        `supports_streaming()` to enable.
        """
        # Imported lazily to avoid a circular dependency at module load
        # (exceptions.py is imported by engines/__init__.py via app).
        from ..exceptions import EngineStreamingNotSupported

        raise EngineStreamingNotSupported(
            f"{self.display_name} does not support streaming synthesis"
        )

    @abc.abstractmethod
    def sample_rate(self) -> int:
        """Output sample rate in Hz."""

    @abc.abstractmethod
    def max_speakers(self) -> int:
        """Maximum number of distinct speakers in a single generation."""

    @abc.abstractmethod
    def supports_voice_cloning(self) -> bool:
        """True if the engine can clone an arbitrary reference voice."""

    @abc.abstractmethod
    def default_cfg_scale(self) -> float | None:
        """Engine's preferred default CFG scale. None if N/A."""

    @abc.abstractmethod
    def available_voices(self) -> list["VoiceInfo"]:
        """List the engine's built-in voice set. Empty if none.

        For engines with no built-in voices (custom-only), this is [].
        """

    def info(self) -> dict[str, Any]:
        """Public info dict for the /api/engines endpoint."""
        return {
            "name": self.name,
            "display_name": self.display_name,
            "description": self.description,
            "loaded": self.is_loaded(),
            "installed": self.installed(),
            "downloaded": self.downloaded(),
            "supports_voice_cloning": self.supports_voice_cloning(),
            "supports_streaming": self.supports_streaming(),
            "sample_rate": self.sample_rate() if self.is_loaded() else None,
            "max_speakers": self.max_speakers(),
            "default_cfg_scale": self.default_cfg_scale(),
            "languages": self.languages(),
            "supports_voice_modes": self.supports_voice_modes(),
            "supports_style_clone": self.supports_style_clone(),
            "supports_style_prompt": self.supports_style_prompt(),
        }

    def engine_info(self) -> dict[str, Any]:
        """Per-engine runtime details for the /api/config endpoint.

        Returns a dict with: model_id, device, dtype, attn_implementation.
        The base implementation returns `"unknown"` for fields the
        engine doesn't track. Subclasses override to surface their own
        torch device / dtype when loaded.
        """
        return {
            "model_id": getattr(self, "_model_id", None) or "unknown",
            "device": getattr(self, "_device_request", None) or "unknown",
            "dtype": "unknown",
            "attn_implementation": "unknown",
        }


# Re-export for convenience
__all__ = [
    "Engine",
    "EngineResult",
    "EngineSynthRequest",
    "wrap_pcm_as_wav",
]


def wrap_pcm_as_wav(pcm: np.ndarray, sample_rate: int) -> bytes:
    """Convert a float32/int16 mono PCM numpy array to a 16-bit PCM WAV.

    Engines that produce raw tensors (Kokoro returns float32 numpy) need
    this to produce the same WAV bytes the rest of the pipeline expects.
    """
    import io
    import struct

    if pcm.dtype != np.int16:
        # Clip to int16 range to avoid wraparound on clipping
        pcm = np.clip(pcm, -1.0, 1.0)
        pcm_i16 = (pcm * 32767.0).astype(np.int16)
    else:
        pcm_i16 = pcm

    pcm_bytes = pcm_i16.tobytes()
    data_size = len(pcm_bytes)
    byte_rate = sample_rate * 1 * 16 // 8
    block_align = 1 * 16 // 8
    header = struct.pack(
        "<4sI4s4sIHHIIHH4sI",
        b"RIFF",
        36 + data_size,
        b"WAVE",
        b"fmt ",
        16,
        1,
        1,
        sample_rate,
        byte_rate,
        block_align,
        16,
        b"data",
        data_size,
    )
    return header + pcm_bytes
