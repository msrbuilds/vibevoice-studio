"""SynthService: orchestrates the active TTS engine + cache + threading.

This module keeps the public API of the previous SynthService (so the
existing routes, schemas, and tests don't change) but delegates the
actual model call to the active `Engine` from `EngineManager`.

Engines do the heavy lifting (model.generate / KPipeline). SynthService
does everything engine-agnostic:
  - input validation
  - multi-line text → canonical `Speaker N:` script
  - per-segment disk cache lookup/write
  - thread serialization (model.generate holds the GIL, so we run
    blocking calls in a single-worker ThreadPoolExecutor under a lock)
  - WAV byte packaging
"""

from __future__ import annotations

import concurrent.futures
import logging
import re
import tempfile
import threading
import time
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING

import numpy as np
import soundfile as sf

from ..core.engines import EngineSynthRequest, wrap_pcm_as_wav
from ..core.exceptions import (
    OutOfMemory,
    SynthesisTimeout,
    TextInvalid,
    VoiceNotFound,
)
from .synth_cache import SynthCache, compute_hash
from .voices import VoiceRegistry

if TYPE_CHECKING:
    from ..core.engine_manager import EngineManager

log = logging.getLogger(__name__)


@dataclass
class Speaker:
    """One speaker in a script."""
    name: str
    voice_id: str  # VoiceRegistry id (i.e. filename stem)
    voice_mode: str | None = None  # OmniVoice: clone|design|auto
    instruct: str | None = None    # OmniVoice design-mode prompt


@dataclass
class SynthRequest:
    text: str
    speakers: list[Speaker]  # ordered list of speakers used in the script
    cfg_scale: float | None = None
    inference_steps: int | None = None
    disable_prefill: bool = False  # True → generate without voice cloning
    force_regenerate: bool = False  # True → bypass per-segment cache read
    speed: float = 1.0  # Kokoro uses this; VibeVoice ignores
    engine: str | None = None  # explicit engine override; default = active
    # --- Chatterbox Multilingual V3 only (other engines ignore) ---
    cfg_weight: float | None = None  # classifier-free guidance weight
    exaggeration: float | None = None  # voice expressiveness
    # BCP-47-ish short language code. When set, overrides the language
    # derived from the voice's metadata. Used by the multilingual engine.
    language_id: str | None = None


@dataclass
class SynthResult:
    wav_bytes: bytes
    sample_rate: int
    duration_sec: float
    inference_ms: int
    cache_hash: str | None = None
    cache_hit: bool = False
    engine: str | None = None


_SPEAKER_TAG = re.compile(
    r"^\s*Speaker\s*\d+\s*:", re.IGNORECASE | re.MULTILINE
)


def _has_speaker_tags(text: str) -> bool:
    return bool(_SPEAKER_TAG.search(text))


def _normalize_speaker_tags(text: str) -> str:
    """Remap any speaker prefix to canonical `Speaker N: <text>` form."""
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


class SynthService:
    """Routes synthesis to the active engine. Engine-agnostic."""

    def __init__(
        self,
        engine_manager: "EngineManager",
        voice_registry: VoiceRegistry,
        max_text_chars: int,
        synth_timeout_s: int,
        default_cfg_scale: float,
        cache: SynthCache | None = None,
    ) -> None:
        self._engines = engine_manager
        self._voices = voice_registry
        self._max_text_chars = max_text_chars
        self._timeout_s = synth_timeout_s
        self._default_cfg_scale = default_cfg_scale
        self._cache = cache
        self._thread_lock = threading.Lock()
        self._executor = concurrent.futures.ThreadPoolExecutor(
            max_workers=1, thread_name_prefix="tts-gen"
        )

    # -- internal helpers
    def _resolve_request_context(self, req: SynthRequest):
        """Common request validation + engine routing used by both
        `synthesize()` and `stream_synthesize()`. Returns a tuple of
        `(target_engine, target_name, reference_audio, voice_language,
        cfg, steps_override)` ready to feed into an EngineSynthRequest.
        """
        text = (req.text or "").strip()
        if not text:
            raise TextInvalid("text must be non-empty")
        if len(text) > self._max_text_chars:
            raise TextInvalid(
                f"text exceeds {self._max_text_chars} chars (got {len(text)})"
            )
        if not req.speakers:
            raise TextInvalid("at least one speaker is required")

        # Determine which engine will run this request. Either the caller
        # pinned one (req.engine), or we use the active engine.
        target_engine = self._engines.active_engine
        target_name = self._engines.active_name
        if req.engine and req.engine != target_name:
            try:
                target_engine = self._engines.get_engine(req.engine)
                target_name = req.engine
            except KeyError:
                raise TextInvalid(f"unknown engine: {req.engine}")
        # Eagerly load if needed. Catches the ImportError for Kokoro etc.
        try:
            if not target_engine.is_loaded():
                target_engine.load()
        except Exception as exc:  # noqa: BLE001
            raise TextInvalid(f"engine {target_name!r} not available: {exc}")

        # Enforce engine-level constraints.
        if len(req.speakers) > target_engine.max_speakers():
            raise TextInvalid(
                f"{target_engine.display_name} supports up to "
                f"{target_engine.max_speakers()} speaker(s) per request "
                f"(got {len(req.speakers)})"
            )
        # Resolve reference audio (voice cloning engines) + voice language.
        reference_audio: str | None = None
        voice_language: str | None = None
        for sp in req.speakers:
            try:
                if target_engine.supports_voice_cloning():
                    reference_audio = str(self._voices.get(sp.voice_id))
                voice_language = voice_language or self._voices.get_language(sp.voice_id)
            except VoiceNotFound:
                raise

        cfg = req.cfg_scale if req.cfg_scale is not None else self.default_cfg_scale
        steps_override = req.inference_steps
        if steps_override is not None and steps_override > 0:
            try:
                if hasattr(target_engine, "set_ddpm_steps"):
                    target_engine.set_ddpm_steps(steps_override)
            except Exception:  # noqa: BLE001
                pass

        return target_engine, target_name, reference_audio, voice_language, cfg, steps_override, text

    # -- public properties
    @property
    def default_cfg_scale(self) -> float:
        # Engine-specific default if the engine has one, else the global.
        eng = self._engines.active_engine
        if eng.is_loaded():
            v = eng.default_cfg_scale()
            if v is not None:
                return v
        return self._default_cfg_scale

    @property
    def active_engine_name(self) -> str:
        return self._engines.active_name

    # -- public API
    def synthesize(self, req: SynthRequest) -> SynthResult:
        target_engine, target_name, reference_audio, voice_language, cfg, steps_override, text = \
            self._resolve_request_context(req)
        effective_language_id = req.language_id or voice_language
        effective_cfg_weight = req.cfg_weight
        effective_exaggeration = req.exaggeration

        # Cache key includes the engine name + extra knobs so VibeVoice-
        # cached audio never gets returned for a Kokoro request (or vice
        # versa), and so changing cfg_weight/exaggeration/language
        # invalidates the cache entry.
        content_hash: str | None = None
        if self._cache is not None and self._cache.enabled:
            cache_voice_key = (
                Path(reference_audio).name if reference_audio else req.speakers[0].voice_id
            )
            # Fold the optional knobs into the voice field with a stable
            # delimiter so different knob combos don't share a cache slot.
            extra = ""
            if effective_cfg_weight is not None:
                extra += f"|cw={effective_cfg_weight:.3f}"
            if effective_exaggeration is not None:
                extra += f"|ex={effective_exaggeration:.3f}"
            if effective_language_id:
                extra += f"|lang={effective_language_id}"
            content_hash = compute_hash(
                text=req.text,
                voice=cache_voice_key + extra,
                cfg_scale=cfg,
                voice_samples=[reference_audio or req.speakers[0].voice_id],
            )
            hit = self._cache.get(content_hash)
            if hit is not None and not req.force_regenerate:
                log.info(
                    "Cache hit for %s (%.1fs audio, engine=%s)",
                    content_hash, hit.duration_sec, target_name,
                )
                return SynthResult(
                    wav_bytes=hit.wav_path.read_bytes(),
                    sample_rate=hit.sample_rate,
                    duration_sec=hit.duration_sec,
                    inference_ms=hit.inference_ms,
                    cache_hash=content_hash,
                    cache_hit=True,
                    engine=target_name,
                )

        # Build the engine-level request. For now, single-speaker scripts
        # only — multi-speaker scripts would need to be split and the
        # per-segment WAVs concatenated. SynthService does the split when
        # len(speakers) > 1 OR the script has multiple `Speaker N:` lines.
        script = _build_script(text)
        speaker_chunks = _split_script_by_speaker(script)

        # Single-speaker fast path.
        if len(speaker_chunks) <= 1 and len(req.speakers) <= 1:
            voice_id = req.speakers[0].voice_id
            engine_req = EngineSynthRequest(
                text=speaker_chunks[0] if speaker_chunks else text,
                voice_id=voice_id,
                speed=req.speed,
                cfg_scale=cfg,
                reference_audio=reference_audio,
                inference_steps=steps_override,
                disable_prefill=req.disable_prefill,
            )
            return self._synth_one(
                engine=target_engine,
                engine_name=target_name,
                engine_req=engine_req,
                cache_hash_for_write=content_hash,
            )

        # Multi-speaker: synthesize each chunk separately, then concatenate
        # the resulting PCM. For now, all chunks use speakers[0]'s voice
        # (the simplest path). Multi-voice per-segment routing would need
        # to look at the speaker tag in each chunk and pick the right voice.
        # Keep it simple: warn if more than one speaker is in use.
        if len(req.speakers) > 1:
            log.warning(
                "Multi-speaker synthesis with %d speakers is simplified: "
                "all chunks will use the first speaker's voice.",
                len(req.speakers),
            )

        voice_id = req.speakers[0].voice_id
        pcm_chunks: list[bytes] = []
        sample_rates: list[int] = []
        total_duration = 0.0
        total_inference_ms = 0
        for chunk in speaker_chunks:
            engine_req = EngineSynthRequest(
                text=chunk,
                voice_id=voice_id,
                speed=req.speed,
                cfg_scale=cfg,
                reference_audio=reference_audio,
                inference_steps=steps_override,
                disable_prefill=req.disable_prefill,
                cfg_weight=effective_cfg_weight,
                exaggeration=effective_exaggeration,
                language_id=effective_language_id,
            )
            sub = self._synth_one(
                engine=target_engine,
                engine_name=target_name,
                engine_req=engine_req,
                cache_hash_for_write=None,  # don't cache multi-speaker joins
            )
            sub_pcm, sub_sr, _ = _pcm16_from_wav(sub.wav_bytes)
            pcm_chunks.append(sub_pcm)
            sample_rates.append(sub_sr)
            total_duration += sub.duration_sec
            total_inference_ms += sub.inference_ms

        target_sr = sample_rates[0]
        joined_pcm = _concat_pcm(pcm_chunks, 150, target_sr)
        total_duration += 0.150 * (len(pcm_chunks) - 1)
        joined_wav = _pcm16_to_wav(joined_pcm, target_sr)
        return SynthResult(
            wav_bytes=joined_wav,
            sample_rate=target_sr,
            duration_sec=total_duration,
            inference_ms=total_inference_ms,
            cache_hash=None,
            cache_hit=False,
            engine=target_name,
        )

    # -- streaming
    def stream_synthesize(self, req: SynthRequest):
        """Yield EngineResult chunks for the active engine.

        Validates the request the same way `synthesize()` does, then
        delegates to `target_engine.stream_synthesize(req)`. The WebSocket
        route consumes the iterator and forwards each chunk as a binary
        frame, except for the terminator chunk (wav_bytes=b"") which
        signals "end of stream" and carries the final inference_ms.

        Raises `EngineStreamingNotSupported` (caught by the route as a
        1008 close) if the resolved engine doesn't support streaming.
        """
        target_engine, _name, _ref_audio, voice_language, cfg, _steps, text = \
            self._resolve_request_context(req)

        if not target_engine.supports_streaming():
            # Imports kept lazy to avoid a circular dep at module load.
            from ..exceptions import EngineStreamingNotSupported

            raise EngineStreamingNotSupported(
                f"{target_engine.display_name} does not support streaming synthesis"
            )

        effective_language_id = req.language_id or voice_language

        # Build the EngineSynthRequest with the streaming sentinel set so
        # engines can branch internally if they ever need to.
        engine_req = EngineSynthRequest(
            text=text,
            voice_id=req.speakers[0].voice_id,
            speed=req.speed,
            cfg_scale=cfg,
            cfg_weight=req.cfg_weight,
            exaggeration=req.exaggeration,
            language_id=effective_language_id,
        )

        # Acquire the same lock the non-streaming path uses, so a
        # stream_synthesize call can't run concurrently with a regular
        # synthesize call on the same engine.
        with self._thread_lock:
            # The engine's stream_synthesize is a generator. We just
            # forward each yielded chunk to the caller.
            yield from target_engine.stream_synthesize(engine_req)

    # -- internals
    def _synth_one(
        self,
        engine,
        engine_name: str,
        engine_req: EngineSynthRequest,
        cache_hash_for_write: str | None,
    ) -> SynthResult:
        with self._thread_lock:
            try:
                future = self._executor.submit(engine.synthesize, engine_req)
                result = future.result(timeout=self._timeout_s)
            except concurrent.futures.TimeoutError as exc:
                raise SynthesisTimeout(
                    f"synthesis exceeded {self._timeout_s}s timeout"
                ) from exc

        if cache_hash_for_write and self._cache is not None and self._cache.enabled:
            try:
                self._cache.put(
                    content_hash=cache_hash_for_write,
                    wav_bytes=result.wav_bytes,
                    sample_rate=result.sample_rate,
                    duration_sec=result.duration_sec,
                    inference_ms=result.inference_ms,
                )
            except Exception as exc:  # noqa: BLE001
                log.debug("Failed to write cache entry %s: %s", cache_hash_for_write, exc)

        return SynthResult(
            wav_bytes=result.wav_bytes,
            sample_rate=result.sample_rate,
            duration_sec=result.duration_sec,
            inference_ms=result.inference_ms,
            cache_hash=cache_hash_for_write,
            cache_hit=False,
            engine=engine_name,
        )


# ----------------------------------------------------------------- helpers --

def _build_script(text: str) -> str:
    if not _has_speaker_tags(text):
        non_empty = [ln.strip() for ln in text.splitlines() if ln.strip()]
        if not non_empty:
            non_empty = [text.strip()]
        return "\n".join(f"Speaker 1: {ln}" for ln in non_empty)
    return _normalize_speaker_tags(text)


def _split_script_by_speaker(script: str) -> list[str]:
    """Split a `Speaker N: <text>` script into one chunk per speaker line.

    Used to break multi-speaker scripts into per-voice inference calls.
    Blank lines and lines without a speaker prefix are skipped.
    """
    chunks: list[str] = []
    for line in script.splitlines():
        line = line.strip()
        if not line:
            continue
        m = re.match(r"^Speaker\s*\d+\s*:\s*(.*)$", line, re.IGNORECASE)
        if m and m.group(1).strip():
            chunks.append(m.group(1).strip())
    return chunks


def _pcm16_from_wav(wav_bytes: bytes) -> tuple[bytes, int, int]:
    if wav_bytes[:4] != b"RIFF" or wav_bytes[8:12] != b"WAVE":
        raise ValueError("not a RIFF/WAVE file")
    pos = 12
    sample_rate = 24000
    pcm = b""
    while pos + 8 <= len(wav_bytes):
        cid = wav_bytes[pos:pos + 4]
        sz = int.from_bytes(wav_bytes[pos + 4:pos + 8], "little")
        if cid == b"fmt ":
            if pos + 16 <= len(wav_bytes):
                sample_rate = int.from_bytes(wav_bytes[pos + 12:pos + 16], "little")
        elif cid == b"data":
            pcm = wav_bytes[pos + 8:pos + 8 + sz]
            break
        pos += 8 + sz
        if sz % 2 == 1:
            pos += 1
    if not pcm:
        raise ValueError("WAV has no data chunk")
    return pcm, sample_rate, len(pcm) // 2


def _pcm16_to_wav(pcm: bytes, sample_rate: int, channels: int = 1, bits: int = 16) -> bytes:
    import struct
    data_size = len(pcm)
    byte_rate = sample_rate * channels * bits // 8
    block_align = channels * bits // 8
    header = struct.pack(
        "<4sI4s4sIHHIIHH4sI",
        b"RIFF", 36 + data_size, b"WAVE",
        b"fmt ", 16, 1, channels,
        sample_rate, byte_rate, block_align, bits,
        b"data", data_size,
    )
    return header + pcm


def _concat_pcm(segments: list[bytes], gap_ms: int, sample_rate: int) -> bytes:
    out = bytearray()
    for pcm in segments:
        out.extend(pcm)
        if gap_ms > 0 and pcm is not segments[-1]:
            silence_samples = (gap_ms * sample_rate) // 1000
            out.extend(np.zeros(silence_samples, dtype=np.int16).tobytes())
    return bytes(out)
