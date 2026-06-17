"""SynthService: orchestrates processor.prepare → model.generate → WAV bytes.

The VibeVoice 1.5B model takes a *script* with `Speaker N: <text>` lines and a
list of reference audio paths (one per unique speaker). It supports up to 4
speakers. The UI also lets the user write plain text without speaker tags; in
that case we wrap the text in a single-speaker script.
"""

from __future__ import annotations

import concurrent.futures
import logging
import struct
import tempfile
import threading
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import numpy as np
import torch

from ..core.exceptions import (
    OutOfMemory,
    SynthesisTimeout,
    TextInvalid,
    VoiceNotFound,
)
from ..core.model import ModelManager
from .synth_cache import SynthCache, compute_hash
from .voices import VoiceRegistry

log = logging.getLogger(__name__)


@dataclass
class Speaker:
    """One speaker in a script."""
    name: str
    voice_id: str  # VoiceRegistry id (i.e. filename stem)


@dataclass
class SynthRequest:
    text: str
    speakers: list[Speaker]  # ordered list of speakers used in the script
    cfg_scale: float | None = None
    inference_steps: int | None = None
    disable_prefill: bool = False  # True → generate without voice cloning
    force_regenerate: bool = False  # True → bypass per-segment cache read


@dataclass
class SynthResult:
    wav_bytes: bytes
    sample_rate: int
    duration_sec: float
    inference_ms: int
    cache_hash: str | None = None
    cache_hit: bool = False


class SynthService:
    """Serialize synthesize requests and run the heavy model call in a worker thread.

    The API route is a sync `def`, so FastAPI runs it in a threadpool worker.
    We use a regular `threading.Lock` (not `asyncio.Lock`) so that two
    concurrent threadpool workers serialize correctly. Inside the lock we
    dispatch the actual generate() call to a single-shot ThreadPoolExecutor so
    we can apply a wall-clock timeout via `future.result(timeout=...)`.
    """

    def __init__(
        self,
        model_manager: ModelManager,
        voice_registry: VoiceRegistry,
        max_text_chars: int,
        synth_timeout_s: int,
        default_cfg_scale: float,
        cache: SynthCache | None = None,
    ) -> None:
        self._mm = model_manager
        self._voices = voice_registry
        self._max_text_chars = max_text_chars
        self._timeout_s = synth_timeout_s
        self._default_cfg_scale = default_cfg_scale
        self._cache = cache
        self._thread_lock = threading.Lock()
        self._executor = concurrent.futures.ThreadPoolExecutor(
            max_workers=1, thread_name_prefix="vibevoice-gen"
        )

    @property
    def default_cfg_scale(self) -> float:
        return self._default_cfg_scale

    def synthesize(self, req: SynthRequest) -> SynthResult:
        """Blocking synthesize. May take tens of seconds; runs in the caller's thread."""
        # --- validate inputs
        text = (req.text or "").strip()
        if not text:
            raise TextInvalid("text must be non-empty")
        if len(text) > self._max_text_chars:
            raise TextInvalid(
                f"text exceeds {self._max_text_chars} chars (got {len(text)})"
            )
        if not req.speakers:
            raise TextInvalid("at least one speaker is required")
        if len(req.speakers) > 4:
            raise TextInvalid("VibeVoice-1.5B supports up to 4 speakers")
        if not self._mm.is_loaded:
            raise TextInvalid("model is not loaded; check /api/health")

        # Resolve all voice paths up front
        voice_paths: list[Path] = []
        for sp in req.speakers:
            try:
                voice_paths.append(self._voices.get(sp.voice_id))
            except VoiceNotFound:
                raise

        cfg = req.cfg_scale if req.cfg_scale is not None else self._default_cfg_scale
        steps_override = req.inference_steps

        # --- cache lookup (no lock needed; cache has its own thread-safety)
        content_hash: str | None = None
        if self._cache is not None and self._cache.enabled:
            content_hash = compute_hash(
                text=text,
                voice=voice_paths[0].name,
                cfg_scale=cfg,
                voice_samples=[str(p) for p in voice_paths],
            )
            hit = self._cache.get(content_hash)
            if hit is not None and not req.force_regenerate:
                log.info("Cache hit for %s (%.1fs audio)", content_hash, hit.duration_sec)
                return SynthResult(
                    wav_bytes=hit.wav_path.read_bytes(),
                    sample_rate=hit.sample_rate,
                    duration_sec=hit.duration_sec,
                    inference_ms=hit.inference_ms,
                    cache_hash=content_hash,
                    cache_hit=True,
                )

        # --- serialize across worker threads
        with self._thread_lock:
            if steps_override is not None and steps_override > 0:
                self._mm.set_ddpm_steps(steps_override)

            future = self._executor.submit(
                self._synthesize_sync,
                text,
                voice_paths,
                [sp.name for sp in req.speakers],
                cfg,
                req.disable_prefill,
            )
            try:
                result = future.result(timeout=self._timeout_s)
            except concurrent.futures.TimeoutError as exc:
                raise SynthesisTimeout(
                    f"synthesis exceeded {self._timeout_s}s timeout"
                ) from exc

        # --- cache write (best-effort)
        if self._cache is not None and self._cache.enabled and content_hash is not None:
            try:
                self._cache.put(
                    content_hash=content_hash,
                    wav_bytes=result.wav_bytes,
                    sample_rate=result.sample_rate,
                    duration_sec=result.duration_sec,
                    inference_ms=result.inference_ms,
                )
            except Exception as exc:  # noqa: BLE001
                log.debug("Failed to write cache entry %s: %s", content_hash, exc)
            result.cache_hash = content_hash

        return result

    # --------------------------------------------------------------- internals --

    def _synthesize_sync(
        self,
        text: str,
        voice_paths: list[Path],
        speaker_names: list[str],
        cfg_scale: float,
        disable_prefill: bool,
    ) -> SynthResult:
        processor = self._mm.processor
        model = self._mm.model
        sr = self._mm.sampling_rate

        # 1. Build the script. The processor requires the literal prefix
        #    "Speaker N:" (case-insensitive) — it does NOT accept arbitrary
        #    speaker names like "Host:" or "Alice:". Speaker IDs are 1-based
        #    in the script, and the processor maps them to voice_samples[i]
        #    by first appearance.
        if not _has_speaker_tags(text):
            # Plain text with no speaker tags. If the text spans multiple
            # lines, prefix EVERY non-empty line with "Speaker 1:" so the
            # model generates voice for all lines instead of stopping after
            # the first. Joining with a single space flattens multi-line
            # text into a single utterance.
            non_empty = [ln.strip() for ln in text.splitlines() if ln.strip()]
            if not non_empty:
                non_empty = [text.strip()]
            script = "\n".join(f"Speaker 1: {ln}" for ln in non_empty)
        else:
            script = _normalize_speaker_tags(text)

        # 2. Prepare inputs.
        try:
            inputs = processor(
                text=[script],
                # The processor wraps each path with float() internally; passing
                # Path objects fails with "float() argument must be a string or
                # a real number, not 'WindowsPath'". Convert to str.
                voice_samples=[[str(p) for p in voice_paths]],
                padding=True,
                return_tensors="pt",
                return_attention_mask=True,
            )
        except Exception as exc:  # noqa: BLE001
            log.exception("processor() failed")
            raise TextInvalid(f"processor failed: {exc}") from exc

        # 3. Move tensors to the model's device; leave non-tensor entries alone.
        device = self._mm.device
        moved: dict[str, Any] = {}
        for k, v in inputs.items():
            if isinstance(v, torch.Tensor):
                moved[k] = v.to(device)
            else:
                moved[k] = v

        # 4. Generate
        t0 = time.perf_counter()
        try:
            with torch.inference_mode():
                output = model.generate(
                    **moved,
                    tokenizer=processor.tokenizer,
                    cfg_scale=cfg_scale,
                    max_new_tokens=None,
                    is_prefill=not disable_prefill,
                )
        except torch.cuda.OutOfMemoryError as exc:
            if torch.cuda.is_available():
                torch.cuda.empty_cache()
            log.exception("CUDA OOM during synthesis")
            raise OutOfMemory(
                "GPU out of memory; try --device cpu or shorten the text"
            ) from exc
        except RuntimeError as exc:
            if "out of memory" in str(exc).lower():
                if torch.cuda.is_available():
                    torch.cuda.empty_cache()
                raise OutOfMemory("out of memory during synthesis") from exc
            log.exception("Model generate failed")
            raise
        inference_ms = int((time.perf_counter() - t0) * 1000)

        # 5. Extract the speech tensor
        speech = getattr(output, "speech_outputs", None)
        if speech is None or len(speech) == 0 or speech[0] is None:
            raise TextInvalid("model produced no audio")
        wav_tensor = speech[0]

        # 6. Save to a temp file via processor.save_audio, then read back as bytes.
        wav_bytes, duration_sec = _tensor_to_wav_bytes(wav_tensor, sr, processor)

        return SynthResult(
            wav_bytes=wav_bytes,
            sample_rate=sr,
            duration_sec=duration_sec,
            inference_ms=inference_ms,
        )


# ----------------------------------------------------------------- helpers ---

_SPEAKER_TAG = __import__("re").compile(r"^\s*Speaker\s*\d+\s*:", __import__("re").MULTILINE | __import__("re").IGNORECASE)


def _has_speaker_tags(text: str) -> bool:
    """Heuristic: does the text already contain canonical 'Speaker N:' lines?"""
    return bool(_SPEAKER_TAG.search(text))


def _normalize_speaker_tags(text: str) -> str:
    """Remap any speaker prefix in `text` to the canonical 'Speaker N: <text>' form.

    The first unique speaker in the script becomes Speaker 1, the second Speaker 2, etc.
    We accept both canonical `Speaker N:` prefixes and named prefixes like `Alice:`
    (case-sensitive, must start with a capital letter). Continuation lines (no
    prefix) inherit the most recent speaker. Hard cap of 4 speakers.
    """
    import re

    name_to_idx: dict[str, int] = {}
    lines = text.splitlines()
    out: list[str] = []
    current_idx: int | None = None

    prefix_re = re.compile(r"^([Ss]peaker\s*\d+|[A-Z][\w.\- ]*?)\s*:\s*(.*)$")

    def _assign(name: str) -> int:
        if name not in name_to_idx:
            if len(name_to_idx) >= 4:
                raise TextInvalid("script uses more than 4 speakers")
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


def _tensor_to_wav_bytes(
    tensor: torch.Tensor,
    sample_rate: int,
    processor: Any,
) -> tuple[bytes, float]:
    """Save a tensor to a temp file via processor.save_audio, then read back as bytes."""
    import soundfile as sf

    if torch.is_tensor(tensor):
        arr = tensor.detach().cpu().to(torch.float32).numpy()
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


def make_wav_header(data_size: int, sample_rate: int, channels: int = 1, bits: int = 16) -> bytes:
    """Build a canonical PCM WAV header (RIFF/fmt/data). Used by tests."""
    byte_rate = sample_rate * channels * bits // 8
    block_align = channels * bits // 8
    return struct.pack(
        "<4sI4s4sIHHIIHH4sI",
        b"RIFF",
        36 + data_size,
        b"WAVE",
        b"fmt ",
        16,
        1,
        channels,
        sample_rate,
        byte_rate,
        block_align,
        bits,
        b"data",
        data_size,
    )
