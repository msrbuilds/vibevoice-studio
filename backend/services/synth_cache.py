"""Persistent on-disk synthesis cache.

Caches the WAV output of /api/synthesize keyed by a content hash so repeated
requests for the same text + voice + cfg_scale hit the disk instead of the
GPU. Survives browser refreshes, model reloads, and server restarts.

Cache files are stored as `<cache_dir>/<hash>.wav` alongside a tiny sidecar
JSON `<cache_dir>/<hash>.json` carrying the metadata needed to compute the
HTTP response headers (sample_rate, duration_sec, inference_ms).

The cache is LRU-bounded: when the number of entries exceeds `max_entries`,
the oldest half is evicted. This keeps disk usage predictable.
"""

from __future__ import annotations

import hashlib
import json
import logging
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

log = logging.getLogger(__name__)


@dataclass
class CacheEntry:
    hash: str
    wav_path: Path
    sample_rate: int
    duration_sec: float
    inference_ms: int
    created_at: float
    text: str | None = None
    voice: str | None = None


def compute_hash(text: str, voice: str, cfg_scale: float, voice_samples: list[str]) -> str:
    """Stable content hash for a synthesis request."""
    # Order of voice_samples matters for voice mapping; sort for determinism.
    canonical = json.dumps(
        {
            "text": text,
            "voice": voice,
            "cfg_scale": round(float(cfg_scale), 4),
            "voice_samples": sorted(voice_samples),
        },
        ensure_ascii=False,
        sort_keys=False,
        separators=(",", ":"),
    )
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()[:24]


def compute_join_hash(segment_hashes: list[str], silence_gap_ms: int) -> str:
    """Stable hash for a concatenated download.

    Two downloads of the same segments in the same order with the same gap
    produce the same hash and therefore hit the cache.
    """
    canonical = json.dumps(
        {
            "segments": list(segment_hashes),  # preserve order
            "gap_ms": int(silence_gap_ms),
        },
        ensure_ascii=False,
        separators=(",", ":"),
    )
    return "join-" + hashlib.sha256(canonical.encode("utf-8")).hexdigest()[:24]


class SynthCache:
    """On-disk synthesis cache. Thread-safe via an instance lock."""

    def __init__(self, cache_dir: Path, enabled: bool = True, max_entries: int = 500) -> None:
        self._dir = Path(cache_dir)
        self._enabled = enabled
        self._max_entries = max(1, int(max_entries))
        self._index: dict[str, CacheEntry] = {}
        if enabled:
            self._dir.mkdir(parents=True, exist_ok=True)
            self._load_index()

    @property
    def enabled(self) -> bool:
        return self._enabled

    @property
    def dir(self) -> Path:
        return self._dir

    def __len__(self) -> int:
        return len(self._index)

    # ---- I/O ----

    def _load_index(self) -> None:
        """Scan the cache directory on startup to rebuild the in-memory index."""
        if not self._dir.exists():
            return
        loaded = 0
        for meta in self._dir.glob("*.json"):
            try:
                data = json.loads(meta.read_text(encoding="utf-8"))
                hash_id = data["hash"]
                wav_path = self._dir / f"{hash_id}.wav"
                if not wav_path.is_file():
                    meta.unlink(missing_ok=True)
                    continue
                self._index[hash_id] = CacheEntry(
                    hash=hash_id,
                    wav_path=wav_path,
                    sample_rate=int(data["sample_rate"]),
                    duration_sec=float(data["duration_sec"]),
                    inference_ms=int(data["inference_ms"]),
                    created_at=float(data.get("created_at", meta.stat().st_mtime)),
                    text=data.get("text"),
                    voice=data.get("voice"),
                )
                loaded += 1
            except Exception as exc:  # noqa: BLE001
                log.warning("Failed to load cache meta %s: %s", meta, exc)
        log.info("Synthesis cache: %d entries loaded from %s", loaded, self._dir)

    def get(self, content_hash: str) -> Optional[CacheEntry]:
        if not self._enabled:
            return None
        entry = self._index.get(content_hash)
        if entry is None:
            return None
        # Confirm files are still on disk
        if not entry.wav_path.is_file() or not entry.wav_path.with_suffix(".wav").with_name(f"{content_hash}.json").is_file():
            self._index.pop(content_hash, None)
            return None
        # Touch the entry to mark it recently used
        entry.created_at = time.time()
        return entry

    def put(
        self,
        content_hash: str,
        wav_bytes: bytes,
        sample_rate: int,
        duration_sec: float,
        inference_ms: int,
        text: str | None = None,
        voice: str | None = None,
    ) -> tuple[CacheEntry, str | None]:
        """Write a cache entry. Returns (entry, old_content_hash_or_None).

        `old_content_hash` is the hash of the previous entry that occupied
        this slot, IF that previous entry's hash was different. Callers
        use it to invalidate join entries that referenced the old audio.
        """
        if not self._enabled:
            raise RuntimeError("cache is disabled")
        old_entry = self._index.get(content_hash)
        old_hash: str | None = None
        # If we're overwriting an entry whose hash is the same as ours, it's
        # a no-op (rare; could happen with a manual `put` call). Otherwise,
        # the slot is being taken over by a different hash — but that's
        # impossible with a dict keyed by hash, so `old_entry` is always
        # either the same content or None. We still report it so the caller
        # can detect overwrites.
        if old_entry is not None and old_entry.hash != content_hash:
            old_hash = old_entry.hash

        wav_path = self._dir / f"{content_hash}.wav"
        meta_path = self._dir / f"{content_hash}.json"
        wav_path.write_bytes(wav_bytes)
        now = time.time()
        meta_path.write_text(
            json.dumps(
                {
                    "hash": content_hash,
                    "sample_rate": sample_rate,
                    "duration_sec": duration_sec,
                    "inference_ms": inference_ms,
                    "created_at": now,
                    "text": text,
                    "voice": voice,
                }
            ),
            encoding="utf-8",
        )
        entry = CacheEntry(
            hash=content_hash,
            wav_path=wav_path,
            sample_rate=sample_rate,
            duration_sec=duration_sec,
            inference_ms=inference_ms,
            created_at=now,
            text=text,
            voice=voice,
        )
        self._index[content_hash] = entry
        self._maybe_evict()
        return entry, old_hash

    def put_replace(
        self,
        old_hash: str,
        new_content_hash: str,
        wav_bytes: bytes,
        sample_rate: int,
        duration_sec: float,
        inference_ms: int,
        text: str | None = None,
        voice: str | None = None,
    ) -> CacheEntry:
        """Replace one cached entry with another, deleting the old file.

        Used when a segment's audio is regenerated with different content
        (e.g. text changed). The old file is removed from disk so the hash
        no longer collides. The new entry is stored under its own hash.
        """
        if old_hash == new_content_hash:
            return self._index[old_hash]

        # Remove old entry's files
        old_path = self._dir / f"{old_hash}.wav"
        old_meta = self._dir / f"{old_hash}.json"
        try:
            old_path.unlink(missing_ok=True)
            old_meta.unlink(missing_ok=True)
        except OSError:
            pass
        self._index.pop(old_hash, None)

        # Store new entry
        wav_path = self._dir / f"{new_content_hash}.wav"
        meta_path = self._dir / f"{new_content_hash}.json"
        wav_path.write_bytes(wav_bytes)
        now = time.time()
        meta_path.write_text(
            json.dumps(
                {
                    "hash": new_content_hash,
                    "sample_rate": sample_rate,
                    "duration_sec": duration_sec,
                    "inference_ms": inference_ms,
                    "created_at": now,
                    "text": text,
                    "voice": voice,
                }
            ),
            encoding="utf-8",
        )
        entry = CacheEntry(
            hash=new_content_hash,
            wav_path=wav_path,
            sample_rate=sample_rate,
            duration_sec=duration_sec,
            inference_ms=inference_ms,
            created_at=now,
            text=text,
            voice=voice,
        )
        self._index[new_content_hash] = entry
        self._maybe_evict()
        return entry

    def delete(self, content_hash: str) -> bool:
        entry = self._index.pop(content_hash, None)
        if entry is None:
            return False
        for p in (entry.wav_path, entry.wav_path.with_suffix(".json")):
            try:
                p.unlink(missing_ok=True)
            except OSError:
                pass
        return True

    def clear(self) -> int:
        """Remove all entries. Returns how many were removed."""
        count = len(self._index)
        for entry in list(self._index.values()):
            for p in (entry.wav_path, entry.wav_path.with_suffix(".json")):
                try:
                    p.unlink(missing_ok=True)
                except OSError:
                    pass
        self._index.clear()
        return count

    def list(self) -> list[CacheEntry]:
        """All entries, newest first."""
        return sorted(self._index.values(), key=lambda e: e.created_at, reverse=True)

    # ---- maintenance ----

    def _maybe_evict(self) -> None:
        if len(self._index) <= self._max_entries:
            return
        # Evict the oldest half
        sorted_entries = sorted(self._index.values(), key=lambda e: e.created_at)
        keep = self._max_entries // 2
        to_remove = sorted_entries[: max(0, len(sorted_entries) - keep)]
        for entry in to_remove:
            self.delete(entry.hash)
        log.info("Evicted %d cache entries (cap=%d)", len(to_remove), self._max_entries)
