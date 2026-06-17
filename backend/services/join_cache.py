"""On-disk cache for concatenated (joined) audio downloads.

A thin wrapper around SynthCache that lives in `<cache_dir>/downloads/`
and reuses the same WAV+JSON on-disk format. Keyed by `compute_join_hash`
which hashes the ordered list of segment hashes plus the silence gap.

To handle the case where one of the constituent segments is regenerated
after a download, we maintain a manifest (`manifest.json`) that records
which segment hashes went into each join_hash. When a per-segment entry
is overwritten, the caller invokes `invalidate_for_segment(old_hash)`
which removes any join entries that referenced that segment hash.
"""

from __future__ import annotations

import json
import logging
import time
from dataclasses import replace
from pathlib import Path
from typing import Any

from .synth_cache import CacheEntry, SynthCache

log = logging.getLogger(__name__)


class JoinCache:
    """Cache for concatenated full-podcast downloads."""

    MANIFEST_FILENAME = "manifest.json"

    def __init__(self, parent: SynthCache) -> None:
        self._inner = parent
        self._manifest: dict[str, list[str]] = {}  # join_hash -> [segment_hash, ...]
        self._load_manifest()

    @property
    def enabled(self) -> bool:
        return self._inner.enabled

    @property
    def dir(self) -> Path:
        return self._inner.dir / "downloads"

    def _resolve_path(self, content_hash: str) -> Path:
        return self.dir / f"{content_hash}.wav"

    def _manifest_path(self) -> Path:
        return self.dir / self.MANIFEST_FILENAME

    def _load_manifest(self) -> None:
        if not self.dir.exists():
            return
        path = self._manifest_path()
        if not path.is_file():
            return
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
            if isinstance(data, dict):
                self._manifest = {
                    str(k): list(v) for k, v in data.items() if isinstance(v, list)
                }
                log.info("Join manifest: %d entries loaded", len(self._manifest))
        except Exception as exc:  # noqa: BLE001
            log.warning("Failed to load join manifest: %s", exc)

    def _save_manifest(self) -> None:
        try:
            self.dir.mkdir(parents=True, exist_ok=True)
            self._manifest_path().write_text(
                json.dumps(self._manifest, indent=2), encoding="utf-8"
            )
        except Exception as exc:  # noqa: BLE001
            log.warning("Failed to save join manifest: %s", exc)

    def get(self, join_hash: str) -> CacheEntry | None:
        entry = self._inner.get(join_hash)
        if entry is None:
            return None
        return replace(entry, wav_path=self._resolve_path(join_hash))

    def put(
        self,
        join_hash: str,
        wav_bytes: bytes,
        sample_rate: int,
        duration_sec: float,
        inference_ms: int,
        segment_hashes: list[str] | None = None,
    ) -> None:
        """Store the joined WAV and record which segments went into it."""
        self.dir.mkdir(parents=True, exist_ok=True)
        wav_path = self._resolve_path(join_hash)
        wav_path.write_bytes(wav_bytes)
        meta_path = wav_path.with_suffix(".json")
        meta_path.write_text(
            json.dumps(
                {
                    "hash": join_hash,
                    "sample_rate": sample_rate,
                    "duration_sec": duration_sec,
                    "inference_ms": inference_ms,
                    "created_at": time.time(),
                }
            ),
            encoding="utf-8",
        )
        self._inner._index[join_hash] = CacheEntry(
            hash=join_hash,
            wav_path=wav_path,
            sample_rate=sample_rate,
            duration_sec=duration_sec,
            inference_ms=inference_ms,
            created_at=time.time(),
        )
        if segment_hashes is not None:
            self._manifest[join_hash] = list(segment_hashes)
            self._save_manifest()
        self._inner._maybe_evict()
        log.info(
            "Join cache: wrote %s (%.1fs, %d bytes, %d segments)",
            join_hash, duration_sec, len(wav_bytes), len(segment_hashes or []),
        )

    def delete(self, join_hash: str) -> bool:
        entry = self._inner._index.pop(join_hash, None)
        if entry is None:
            return False
        for p in (entry.wav_path, entry.wav_path.with_suffix(".json")):
            try:
                p.unlink(missing_ok=True)
            except OSError:
                pass
        self._manifest.pop(join_hash, None)
        self._save_manifest()
        return True

    def clear(self) -> int:
        """Remove only entries that live under downloads/."""
        to_remove = [
            h for h, e in self._inner._index.items()
            if str(e.wav_path).startswith(str(self.dir))
        ]
        for h in to_remove:
            self.delete(h)
        return len(to_remove)

    def invalidate_for_segment(self, old_segment_hash: str) -> list[str]:
        """Remove any join entries that reference the given segment hash.

        Called when a per-segment audio is regenerated, so the next download
        with the same content re-concatenates from the new audio.
        """
        if not self._manifest:
            return []
        to_remove = [
            join_hash
            for join_hash, segment_hashes in self._manifest.items()
            if old_segment_hash in segment_hashes
        ]
        for join_hash in to_remove:
            self.delete(join_hash)
        if to_remove:
            log.info(
                "Join cache: invalidated %d entries (segment %s was regenerated)",
                len(to_remove), old_segment_hash[:12],
            )
        return to_remove

