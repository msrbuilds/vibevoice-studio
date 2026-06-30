"""GET/DELETE /api/cache — manage the on-disk synthesis cache."""

from __future__ import annotations

import logging
import os
import subprocess
import sys
from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import FileResponse, Response
from pydantic import BaseModel

from ..services.synth_cache import SynthCache
from .deps import get_synth_cache

log = logging.getLogger(__name__)


def _open_in_file_manager(path: Path) -> None:
    """Open a directory in the host OS file manager.

    This is a local-desktop-app convenience: the backend runs in the user's
    own session, so revealing its own cache directory is safe (the path is the
    server's, never user-supplied).
    """
    if sys.platform.startswith("win"):
        os.startfile(str(path))  # type: ignore[attr-defined]  # noqa: S606 (Windows-only)
    elif sys.platform == "darwin":
        subprocess.run(["open", str(path)], check=False)
    else:
        subprocess.run(["xdg-open", str(path)], check=False)

router = APIRouter(prefix="/api/cache", tags=["cache"])


def _derive_name(text: str | None, hash: str) -> str:
    """Derive a human-readable name from synthesis text.

    Takes the first 6 whitespace-split words, joins them, trims to <=48 chars.
    Falls back to "Generation <hash8>" when text is absent or empty.
    """
    if text and text.strip():
        words = text.split()[:6]
        name = " ".join(words)[:48].strip()
        if name:
            return name
    return f"Generation {hash[:8]}"


class CacheEntryInfo(BaseModel):
    hash: str
    sample_rate: int
    duration_sec: float
    inference_ms: int
    size_bytes: int
    created_at: float
    text: str | None = None
    voice: str | None = None
    name: str


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
        # Exclude join- export bundles — they have no single text/voice
        if e.hash.startswith("join-"):
            continue
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
                text=e.text,
                voice=e.voice,
                name=_derive_name(e.text, e.hash),
            )
        )
    return CacheListResponse(
        enabled=cache.enabled,
        directory=str(cache.dir),
        entry_count=len(cache),
        max_entries=cache._max_entries,  # noqa: SLF001 (intentional read)
        entries=entries,
    )


@router.get("/{content_hash}/audio")
def get_cache_audio(
    content_hash: str,
    cache: SynthCache = Depends(get_synth_cache),
) -> Response:
    """Serve a cached WAV file for playback or download.

    Uses FileResponse so Starlette advertises `Accept-Ranges: bytes` and
    honors `Range` requests (206 partial content) — without this the browser
    can't seek the <audio> element (currentTime snaps back to 0).
    """
    entry = cache.get(content_hash)
    if entry is None or not entry.wav_path.is_file():
        raise HTTPException(status_code=404, detail=f"cache entry not found: {content_hash}")
    return FileResponse(entry.wav_path, media_type="audio/wav")


@router.post("/folder", status_code=200)
def open_cache_folder(cache: SynthCache = Depends(get_synth_cache)) -> dict:
    """Open the synthesis-cache directory in the OS file manager."""
    path = cache.dir
    if not path.is_dir():
        raise HTTPException(status_code=404, detail="cache directory not found")
    try:
        _open_in_file_manager(path)
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(status_code=500, detail=f"could not open folder: {exc}") from exc
    return {"opened": str(path)}


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
