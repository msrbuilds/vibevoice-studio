"""Kokoro-82M engine — lightweight Apache-licensed TTS from hexgrad.

See https://huggingface.co/hexgrad/Kokoro-82M and
https://github.com/hexgrad/kokoro.

Kokoro is a 82M-parameter StyleTTS2 model with 54 built-in voices across
American English (af_*), British English (bf_*), Japanese (jf_* — requires
`misaki[ja]`), and Mandarin Chinese (zf_* — requires `misaki[zh]`). It
does NOT support voice cloning — voices are picked from the built-in set.

The `kokoro` PyPI package import is lazy so the backend still boots when
only VibeVoice is installed.
"""

from __future__ import annotations

import logging
import time
from dataclasses import dataclass
from typing import Any

from . import Engine, EngineResult, EngineSynthRequest, wrap_pcm_as_wav

log = logging.getLogger(__name__)


# Static catalog of Kokoro's 54 voices. Each id follows the convention
# `{lang}{gender}_{name}` and the language code on the pipeline must match.
# Source: https://huggingface.co/hexgrad/Kokoro-82M/tree/main/voices
@dataclass(frozen=True)
class _KokoroVoiceSpec:
    id: str
    name: str
    gender: str  # "man" | "woman" | "nonbinary"
    language: str  # "en-us" | "en-gb" | "ja" | "zh"
    lang_code: str  # KPipeline lang_code: "a" | "b" | "j" | "z"


_KOKORO_VOICES: tuple[_KokoroVoiceSpec, ...] = (
    # American English (lang_code "a")
    _KokoroVoiceSpec("af_heart",    "Heart",   "woman", "en-us", "a"),
    _KokoroVoiceSpec("af_alloy",    "Alloy",   "woman", "en-us", "a"),
    _KokoroVoiceSpec("af_aoede",    "Aoede",   "woman", "en-us", "a"),
    _KokoroVoiceSpec("af_bella",    "Bella",   "woman", "en-us", "a"),
    _KokoroVoiceSpec("af_jessica",  "Jessica", "woman", "en-us", "a"),
    _KokoroVoiceSpec("af_kore",     "Kore",    "woman", "en-us", "a"),
    _KokoroVoiceSpec("af_nicole",   "Nicole",  "woman", "en-us", "a"),
    _KokoroVoiceSpec("af_nova",     "Nova",    "woman", "en-us", "a"),
    _KokoroVoiceSpec("af_river",    "River",   "woman", "en-us", "a"),
    _KokoroVoiceSpec("af_sarah",    "Sarah",   "woman", "en-us", "a"),
    _KokoroVoiceSpec("af_sky",      "Sky",     "woman", "en-us", "a"),
    _KokoroVoiceSpec("am_adam",     "Adam",    "man",   "en-us", "a"),
    _KokoroVoiceSpec("am_echo",     "Echo",    "man",   "en-us", "a"),
    _KokoroVoiceSpec("am_eric",     "Eric",    "man",   "en-us", "a"),
    _KokoroVoiceSpec("am_fenrir",   "Fenrir",  "man",   "en-us", "a"),
    _KokoroVoiceSpec("am_liam",     "Liam",    "man",   "en-us", "a"),
    _KokoroVoiceSpec("am_michael",  "Michael", "man",   "en-us", "a"),
    _KokoroVoiceSpec("am_onyx",     "Onyx",    "man",   "en-us", "a"),
    _KokoroVoiceSpec("am_puck",     "Puck",    "man",   "en-us", "a"),
    _KokoroVoiceSpec("am_santa",    "Santa",   "man",   "en-us", "a"),
    # British English (lang_code "b")
    _KokoroVoiceSpec("bf_alice",    "Alice",   "woman", "en-gb", "b"),
    _KokoroVoiceSpec("bf_emma",     "Emma",    "woman", "en-gb", "b"),
    _KokoroVoiceSpec("bf_isabella", "Isabella","woman", "en-gb", "b"),
    _KokoroVoiceSpec("bf_lily",     "Lily",    "woman", "en-gb", "b"),
    _KokoroVoiceSpec("bm_daniel",   "Daniel",  "man",   "en-gb", "b"),
    _KokoroVoiceSpec("bm_fable",    "Fable",   "man",   "en-gb", "b"),
    _KokoroVoiceSpec("bm_george",   "George",  "man",   "en-gb", "b"),
    _KokoroVoiceSpec("bm_lewis",    "Lewis",   "man",   "en-gb", "b"),
    # Japanese (lang_code "j") — requires misaki[ja]
    _KokoroVoiceSpec("jf_alpha",    "Alpha",   "woman", "ja",    "j"),
    _KokoroVoiceSpec("jf_gongitsune","Gongitsune","woman","ja",  "j"),
    _KokoroVoiceSpec("jf_nezumi",   "Nezumi",  "woman", "ja",    "j"),
    _KokoroVoiceSpec("jf_tebukuro", "Tebukuro","woman", "ja",    "j"),
    _KokoroVoiceSpec("jm_kumo",     "Kumo",    "man",   "ja",    "j"),
    # Mandarin Chinese (lang_code "z") — requires misaki[zh]
    _KokoroVoiceSpec("zf_xiaobei",  "Xiaobei", "woman", "zh",    "z"),
    _KokoroVoiceSpec("zf_xiaoni",   "Xiaoni",  "woman", "zh",    "z"),
    _KokoroVoiceSpec("zf_xiaoxiao", "Xiaoxiao","woman", "zh",    "z"),
    _KokoroVoiceSpec("zf_xiaoyi",   "Xiaoyi",  "woman", "zh",    "z"),
    _KokoroVoiceSpec("zm_yunjian",  "Yunjian", "man",   "zh",    "z"),
    _KokoroVoiceSpec("zm_yunxi",    "Yunxi",   "man",   "zh",    "z"),
    _KokoroVoiceSpec("zm_yunxia",   "Yunxia",  "man",   "zh",    "z"),
    _KokoroVoiceSpec("zm_yunyang",  "Yunyang", "man",   "zh",    "z"),
)


_KOKORO_LANG_LABELS: dict[str, str] = {
    "en-us": "English (US)", "en-gb": "English (UK)",
    "ja": "Japanese", "zh": "Chinese",
}


# KPipeline lang_code → list of voice ids that voice can handle
def _voices_for_lang_code(lang_code: str) -> list[str]:
    return [v.id for v in _KOKORO_VOICES if v.lang_code == lang_code]


def _voice_spec(voice_id: str) -> _KokoroVoiceSpec | None:
    for v in _KOKORO_VOICES:
        if v.id == voice_id:
            return v
    return None


class KokoroEngine(Engine):
    """Kokoro-82M via the `kokoro` PyPI package.

    Notes:
    - One `KPipeline` per language code is created lazily on first use and
      cached, since Kokoro's pipeline is per-language.
    - The model weights are downloaded once on first load and cached under
      `~/.cache/huggingface/`.
    - Requires `espeak-ng` installed on the system (Windows: MSI; Linux:
      `apt install espeak-ng`; macOS: `brew install espeak-ng`).
    """

    name = "kokoro"
    display_name = "Kokoro-82M"
    license = "Apache-2.0"
    model_url = "https://huggingface.co/hexgrad/Kokoro-82M"
    description = "Hexgrad's 82M-param StyleTTS2. ~350 MB. EN/JA/ZH built-in voices."

    def __init__(self, default_lang_code: str = "a", default_speed: float = 1.0) -> None:
        self._default_lang_code = default_lang_code
        self._default_speed = default_speed
        self._model_id = "hexgrad/Kokoro-82M"
        # KPipeline instances keyed by lang_code, created lazily.
        self._pipelines: dict[str, Any] = {}
        self._available: bool | None = None  # cache import check

    # -- lifecycle
    def load(self) -> None:
        # Importing the kokoro package triggers weights download on first
        # pipeline() call. We just verify the import here so failures show
        # up early with a clean error.
        self._ensure_kokoro()
        # Pre-create a pipeline for the default language so the first
        # request is fast.
        self._get_pipeline(self._default_lang_code)

    def unload(self) -> None:
        self._pipelines.clear()
        try:
            import torch

            if torch.cuda.is_available():
                torch.cuda.empty_cache()
        except ImportError:
            pass

    def is_loaded(self) -> bool:
        if self._available is False:
            return False
        return bool(self._pipelines)

    def downloaded(self) -> bool:
        from ..model_cache import model_downloaded

        return model_downloaded(self._model_id)

    def engine_info(self) -> dict[str, Any]:
        """Surface Kokoro's pipeline info to /api/config.

        Kokoro uses KPipeline under the hood; the device is whatever
        torch sees as available (cuda when a GPU is present, else cpu).
        Kokoro-82M is float32 by default — no mixed-precision knobs.
        """
        import torch
        device = "cuda" if torch.cuda.is_available() else "cpu"
        return {
            "model_id": self._model_id,
            "device": device,
            "dtype": "float32",
            "attn_implementation": "n/a",
        }

    # -- capabilities
    def sample_rate(self) -> int:
        return 24000

    def max_speakers(self) -> int:
        # Kokoro's KPipeline generates one voice at a time. Multi-speaker
        # scripts would need per-segment calls (the SynthService handles
        # that). Per-call we treat it as a single-speaker engine.
        return 1

    def supports_voice_cloning(self) -> bool:
        return False

    def supports_streaming(self) -> bool:
        # KPipeline.__call__() is a generator that yields one audio
        # chunk per decoder step. We can forward each chunk as it
        # arrives so the WebSocket client hears audio start within
        # ~100ms instead of waiting for the full narration.
        return True

    def default_cfg_scale(self) -> float | None:
        # Kokoro has no CFG knob; use `speed` instead.
        return None

    def available_voices(self) -> list:
        # The registry delegates to this method for `engine == "kokoro"`
        # voice listings. We return VoiceInfo objects that are tagged
        # with engine="kokoro" so the frontend can group them.
        from ...services.voices import VoiceInfo

        out: list[VoiceInfo] = []
        for v in _KOKORO_VOICES:
            out.append(
                VoiceInfo(
                    id=v.id,
                    name=v.name,
                    gender=v.gender,
                    language=v.language,
                    source="builtin",
                    size_bytes=None,
                    duration_sec=None,
                    sample_rate=24000,
                )
            )
        return out

    def languages(self) -> list[dict[str, str]]:
        seen: list[str] = []
        for v in _KOKORO_VOICES:
            if v.language not in seen:
                seen.append(v.language)
        return [{"code": c, "label": _KOKORO_LANG_LABELS.get(c, c)} for c in seen]

    # -- synthesis
    def synthesize(self, req: EngineSynthRequest) -> EngineResult:
        import numpy as np  # always available; kokoro's dep

        if not req.voice_id:
            raise ValueError("voice_id is required for Kokoro")
        spec = _voice_spec(req.voice_id)
        if spec is None:
            raise ValueError(f"unknown Kokoro voice: {req.voice_id}")

        text = (req.text or "").strip()
        if not text:
            raise ValueError("text must be non-empty")

        pipeline = self._get_pipeline(spec.lang_code)

        # Collect audio from the generator. Kokoro yields one chunk per
        # paragraph (split by \n+); concatenate everything.
        audio_chunks: list[np.ndarray] = []
        t0 = time.perf_counter()
        for _gs, _ps, audio in pipeline(
            text,
            voice=spec.id,
            speed=req.speed or self._default_speed,
            split_pattern=r"\n+",
        ):
            if audio is not None and len(audio) > 0:
                audio_chunks.append(audio)
        inference_ms = int((time.perf_counter() - t0) * 1000)

        if not audio_chunks:
            raise RuntimeError("Kokoro produced no audio")

        import numpy as np

        full = np.concatenate(audio_chunks)
        duration = float(full.size) / float(self.sample_rate())
        wav_bytes = wrap_pcm_as_wav(full, self.sample_rate())
        return EngineResult(
            wav_bytes=wav_bytes,
            sample_rate=self.sample_rate(),
            duration_sec=duration,
            inference_ms=inference_ms,
        )

    def stream_synthesize(
        self, req: EngineSynthRequest
    ):
        """Yield one EngineResult per KPipeline chunk.

        KPipeline.__call__() already returns a generator that yields
        `(gs, ps, audio)` tuples. Each `audio` is a numpy int16 array
        of one decoded segment. We wrap each one as an EngineResult
        containing just-PCM-as-WAV so the WebSocket client can forward
        raw bytes without re-encoding.

        Note: inference time is reported on the *final* chunk only;
        intermediate chunks report `inference_ms=0` because we don't
        know the total until the generator is exhausted.
        """
        if not req.voice_id:
            raise ValueError("voice_id is required for Kokoro")
        spec = _voice_spec(req.voice_id)
        if spec is None:
            raise ValueError(f"unknown Kokoro voice: {req.voice_id}")

        text = (req.text or "").strip()
        if not text:
            raise ValueError("text must be non-empty")

        pipeline = self._get_pipeline(spec.lang_code)
        sr = self.sample_rate()

        t0 = time.perf_counter()
        any_chunk = False
        total_samples = 0
        # Track how many samples we've yielded so each chunk's
        # duration_sec reflects the partial result, useful for UI
        # progress indicators.
        for _gs, _ps, audio in pipeline(
            text,
            voice=spec.id,
            speed=req.speed or self._default_speed,
            split_pattern=r"\n+",
        ):
            if audio is None or len(audio) == 0:
                continue
            any_chunk = True
            samples = int(audio.size)
            total_samples += samples
            # Wrap each chunk as a standalone WAV. The client
            # concatenates the PCM bytes (skipping headers) — easier
            # than feeding each chunk through a shared wav writer.
            wav_bytes = wrap_pcm_as_wav(audio, sr)
            yield EngineResult(
                wav_bytes=wav_bytes,
                sample_rate=sr,
                duration_sec=total_samples / float(sr),
                # Intermediate chunks report 0 ms; the route will
                # compute the final inference_ms and inject it into
                # the closing frame.
                inference_ms=0,
            )

        if not any_chunk:
            raise RuntimeError("Kokoro produced no audio")

        # Yield one final empty-PCM result purely so the caller knows
        # the total inference_ms. The WebSocket route consumes this
        # and forwards inference_ms in the "end" frame instead of
        # treating it as a chunk.
        inference_ms = int((time.perf_counter() - t0) * 1000)
        yield EngineResult(
            wav_bytes=b"",
            sample_rate=sr,
            duration_sec=total_samples / float(sr),
            inference_ms=inference_ms,
            is_final=True,
        )
    def _ensure_kokoro(self) -> None:
        if self._available is False:
            raise RuntimeError(
                "The 'kokoro' package is not installed. "
                "Run `pip install -r backend/requirements.txt` and "
                "make sure espeak-ng is on your system PATH."
            )
        if self._available is None:
            try:
                import kokoro  # noqa: F401
                self._available = True
            except ImportError as exc:
                self._available = False
                raise RuntimeError(
                    "The 'kokoro' package is not installed. "
                    "Run `pip install -r backend/requirements.txt` and "
                    "make sure espeak-ng is on your system PATH. "
                    f"(import error: {exc})"
                ) from exc

    def _get_pipeline(self, lang_code: str) -> Any:
        self._ensure_kokoro()
        if lang_code in self._pipelines:
            return self._pipelines[lang_code]
        from kokoro import KPipeline

        log.info("Initializing Kokoro KPipeline for lang_code=%s", lang_code)
        try:
            pipeline = KPipeline(lang_code=lang_code)
        except Exception as exc:
            # Some lang codes require extra misaki extras (ja, zh). Map the
            # error to a helpful message.
            if lang_code in ("j", "z"):
                raise RuntimeError(
                    f"Kokoro failed to init for lang_code='{lang_code}'. "
                    f"Install the matching misaki extra: "
                    f"`pip install 'misaki[{'ja' if lang_code == 'j' else 'zh'}]'` "
                    f"(underyling error: {exc})"
                ) from exc
            raise
        self._pipelines[lang_code] = pipeline
        return pipeline
