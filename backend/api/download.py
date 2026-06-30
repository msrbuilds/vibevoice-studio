"""POST /api/download — concatenate per-segment WAVs into a single full-podcast WAV.

Request body:
    {
      "segments": [
        {"text": "...", "voice": "en_Amelia", "cfg_scale": 1.3},
        ...
      ],
      "silence_gap_ms": 150
    }

The per-segment WAVs are looked up in the segment cache (SynthCache).
If all segments are cached, the resulting full WAV is fetched from
the join cache; otherwise the missing segments are synthesized, then
the joined WAV is written into the join cache.

Returns: audio/wav with the joined audio.
"""

from __future__ import annotations

import asyncio
import io
import logging
import time
import uuid
import wave
import json
from typing import Annotated, Literal

import numpy as np
from fastapi import APIRouter, Body, Depends, HTTPException, Response
from pydantic import BaseModel, Field

from ..core.exceptions import BackendError, TextInvalid
from ..services.join_cache import JoinCache
from ..services.synth_cache import compute_hash
from ..services.synthesize import SynthService
from .deps import get_join_cache, get_synth_service

log = logging.getLogger(__name__)

router = APIRouter(tags=["download"])


class DownloadSegment(BaseModel):
    text: str = Field(..., min_length=1)
    voice: str = Field("", max_length=256)  # may be empty for OmniVoice design/auto
    voice_mode: Literal["clone", "design", "auto"] | None = None
    instruct: str | None = None
    # VoxCPM diffusion quality (inference timesteps). voxcpm-only; other engines
    # ignore it. Threaded through so an exported segment matches its preview slot.
    inference_steps: int | None = None
    cfg_scale: float | None = None
    # Per-segment cache hash. If provided, the join hash includes this so that
    # regenerating a segment invalidates the join cache. Optional for backward
    # compatibility.
    cache_hash: str | None = None
    # --- Chatterbox Multilingual V3 only ---
    cfg_weight: float | None = Field(default=None, ge=0.0, le=2.0)
    exaggeration: float | None = Field(default=None, ge=0.0, le=2.0)
    language_id: str | None = None


class DownloadRequest(BaseModel):
    segments: list[DownloadSegment] = Field(..., min_length=1, max_length=200)
    silence_gap_ms: int = Field(default=150, ge=0, le=2000)


def _join_canonical(segments: list["DownloadSegment"], silence_gap_ms: int, default_cfg: float) -> str:
    """Stable JSON canonical of a download request, used for the join-cache hash.
    Folds voice_mode/instruct so OmniVoice design/auto and distinct prompts
    never share a joined-WAV cache slot."""
    return json.dumps(
        [
            {
                "text": s.text,
                "voice": s.voice,
                "cfg_scale": round(float(s.cfg_scale if s.cfg_scale is not None else default_cfg), 4),
                "vm": s.voice_mode,
                "in": s.instruct,
                "steps": s.inference_steps,
            }
            for s in segments
        ]
        + [{"gap_ms": silence_gap_ms}],
        ensure_ascii=False,
        separators=(",", ":"),
    )


def _pcm16_from_wav(wav_bytes: bytes) -> tuple[bytes, int, int]:
    """Strip the 44-byte WAV header and return (pcm16_bytes, sample_rate, sample_count)."""
    if wav_bytes[:4] != b"RIFF" or wav_bytes[8:12] != b"WAVE":
        raise ValueError("not a RIFF/WAVE file")
    # Walk chunks to find the audio data — handles non-standard headers.
    pos = 12
    sample_rate = 24000
    pcm = b""
    while pos + 8 <= len(wav_bytes):
        chunk_id = wav_bytes[pos:pos + 4]
        chunk_size = int.from_bytes(wav_bytes[pos + 4:pos + 8], "little")
        if chunk_id == b"fmt ":
            # fmt chunk layout (after 8-byte chunk header):
            #   +0/+2: audio_format (2)        — pos+8
            #   +2/+4: num_channels (2)        — pos+10
            #   +4/+8: sample_rate (4)         — pos+12
            #   +8/+12: byte_rate (4)
            #   +12/+14: block_align (2)
            #   +14/+16: bits_per_sample (2)
            if pos + 16 <= len(wav_bytes):
                sample_rate = int.from_bytes(wav_bytes[pos + 12:pos + 16], "little")
        elif chunk_id == b"data":
            pcm = wav_bytes[pos + 8:pos + 8 + chunk_size]
            break
        pos += 8 + chunk_size
        # Chunks are word-aligned
        if chunk_size % 2 == 1:
            pos += 1
    if not pcm:
        raise ValueError("WAV has no data chunk")
    return pcm, sample_rate, len(pcm) // 2


def _pcm16_to_wav(pcm: bytes, sample_rate: int, channels: int = 1, bits: int = 16) -> bytes:
    data_size = len(pcm)
    byte_rate = sample_rate * channels * bits // 8
    block_align = channels * bits // 8
    header = struct_pack(
        b"RIFF", 36 + data_size, b"WAVE", b"fmt ", 16, 1, channels,
        sample_rate, byte_rate, block_align, bits, b"data", data_size,
    )
    return header + pcm


def struct_pack(*args):  # tiny local shim so this file is self-contained
    import struct
    return struct.pack(
        "<4sI4s4sIHHIIHH4sI", *args
    )


def _concat_pcm(segments: list[bytes], gap_ms: int, sample_rate: int) -> bytes:
    """Concatenate raw int16 PCM chunks, inserting `gap_ms` of silence between."""
    out = io.BytesIO()
    for pcm in segments:
        out.write(pcm)
        if gap_ms > 0 and pcm is not segments[-1]:
            silence_samples = (gap_ms * sample_rate) // 1000
            out.write(np.zeros(silence_samples, dtype=np.int16).tobytes())
    return out.getvalue()


@router.post("/api/download", responses={
    200: {"content": {"audio/wav": {}}},
    400: {"description": "Empty segments list"},
    404: {"description": "Voice not found"},
    503: {"description": "Model not loaded yet"},
    504: {"description": "Synthesis timed out"},
    507: {"description": "GPU out of memory"},
})
def download(
    body: Annotated[DownloadRequest, Body(...)],
    svc: SynthService = Depends(get_synth_service),
    join_cache: JoinCache = Depends(get_join_cache),
) -> Response:
    """Concatenate all segment WAVs into one WAV. Caches the joined result."""
    if not body.segments:
        raise HTTPException(status_code=400, detail="segments list is empty")

    # Compute the join hash BEFORE synthesis so missing-segments are also fast.
    # We use the request text + voice (not the audio hash) so the join key
    # is stable even before the audio exists.
    import hashlib

    canonical = _join_canonical(body.segments, body.silence_gap_ms, svc.default_cfg_scale)
    join_hash = "join-" + hashlib.sha256(canonical.encode("utf-8")).hexdigest()[:24]

    # Cache hit fast path
    if join_cache.enabled:
        hit = join_cache.get(join_hash)
        if hit is not None:
            log.info("Join cache hit for %s", join_hash)
            wav = hit.wav_path.read_bytes()
            return Response(
                content=wav,
                media_type="audio/wav",
                headers={
                    "X-Sample-Rate": str(hit.sample_rate),
                    "X-Audio-Duration-Sec": f"{hit.duration_sec:.3f}",
                    "X-Cache": "hit",
                    "X-Cache-Hash": join_hash,
                    "Content-Disposition": f'attachment; filename="vibevoice-podcast-{uuid.uuid4().hex[:8]}.wav"',
                },
            )

    # Synthesize each segment (uses per-segment cache internally)
    from ..services.synthesize import SynthRequest, Speaker

    pcm_chunks: list[bytes] = []
    sample_rates: list[int] = []
    total_duration = 0.0
    t0 = time.perf_counter()
    for i, seg in enumerate(body.segments):
        try:
            result = svc.synthesize(
                SynthRequest(
                    text=seg.text,
                    speakers=[Speaker(
                        name=seg.voice or "speaker",
                        voice_id=seg.voice,
                        voice_mode=seg.voice_mode,
                        instruct=seg.instruct,
                    )],
                    inference_steps=seg.inference_steps,
                    cfg_scale=seg.cfg_scale,
                    cfg_weight=seg.cfg_weight,
                    exaggeration=seg.exaggeration,
                    language_id=seg.language_id,
                )
            )
        except BackendError:
            raise

        pcm, sr, _ = _pcm16_from_wav(result.wav_bytes)
        pcm_chunks.append(pcm)
        sample_rates.append(sr)
        total_duration += result.duration_sec

    if not pcm_chunks:
        raise HTTPException(status_code=500, detail="no audio produced")
    if len(set(sample_rates)) > 1:
        log.warning("Join: segments have mixed sample rates; using first (%d Hz)", sample_rates[0])
    target_sr = sample_rates[0]

    # Concatenate
    joined_pcm = _concat_pcm(pcm_chunks, body.silence_gap_ms, target_sr)
    total_duration += (body.silence_gap_ms / 1000.0) * (len(pcm_chunks) - 1)
    joined_wav = _pcm16_to_wav(joined_pcm, target_sr)
    inference_ms = int((time.perf_counter() - t0) * 1000)

    # Cache the joined result
    if join_cache.enabled:
        try:
            join_cache.put(
                join_hash=join_hash,
                wav_bytes=joined_wav,
                sample_rate=target_sr,
                duration_sec=total_duration,
                inference_ms=inference_ms,
            )
        except Exception as exc:  # noqa: BLE001
            log.warning("Failed to write join cache entry %s: %s", join_hash, exc)

    return Response(
        content=joined_wav,
        media_type="audio/wav",
        headers={
            "X-Sample-Rate": str(target_sr),
            "X-Audio-Duration-Sec": f"{total_duration:.3f}",
            "X-Cache": "miss",
            "X-Cache-Hash": join_hash,
            "X-Segment-Count": str(len(body.segments)),
            "Content-Disposition": f'attachment; filename="vibevoice-podcast-{uuid.uuid4().hex[:8]}.wav"',
        },
    )
