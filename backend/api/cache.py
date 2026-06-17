"""GET/DELETE /api/cache — manage the on-disk synthesis cache."""

from __future__ import annotations

import logging

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from ..services.synth_cache import SynthCache
from .deps import get_synth_cache

log = logging.getLogger(__name__)

router = APIRouter(prefix="/api/cache", tags=["cache"])


class CacheEntryInfo(BaseModel):
    hash: str
    sample_rate: int
    duration_sec: float
    inference_ms: int
    size_bytes: int
    created_at: float


class CacheListResponse(BaseModel):
    enabled: bool
    directory: str
    entry_count: int
    max_entries: int
    entries: list[CacheEntryInfo]


@router.get("", response_model=CacheListResponse)
def list_cache(cache: SynthCache = Depends(get_synth_cache)) -> CacheListResponse:
    entries = []
    for e in cache.list():
        try:
            size = e.wav_path.stat().st_size
        except OSError:
            size = 0
        entries.append(
            CacheEntryInfo(
                hash=e.hash,
                sample_rate=e.sample_rate,
                duration_sec=e.duration_sec,
                inference_ms=e.inference_ms,
                size_bytes=size,
                created_at=e.created_at,
            )
        )
    return CacheListResponse(
        enabled=cache.enabled,
        directory=str(cache.dir),
        entry_count=len(cache),
        max_entries=cache._max_entries,  # noqa: SLF001 (intentional read)
        entries=entries,
    )


@router.delete("", status_code=200)
def clear_cache(cache: SynthCache = Depends(get_synth_cache)) -> dict:
    """Wipe the entire cache."""
    if not cache.enabled:
        raise HTTPException(status_code=400, detail="cache is disabled")
    removed = cache.clear()
    log.info("Cache cleared: %d entries removed", removed)
    return {"removed": removed}


@router.delete("/{content_hash}", status_code=200)
def delete_cache_entry(
    content_hash: str,
    cache: SynthCache = Depends(get_synth_cache),
) -> dict:
    """Delete a single cache entry by its content hash."""
    if not cache.enabled:
        raise HTTPException(status_code=400, detail="cache is disabled")
    if not cache.delete(content_hash):
        raise HTTPException(status_code=404, detail=f"cache entry not found: {content_hash}")
    return {"deleted": content_hash}
