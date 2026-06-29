"""Tests for the 'recent generations' cache additions.

Covers:
  - text/voice round-trip through CacheEntry + _load_index
  - _derive_name helper
  - GET /api/cache includes text/voice/name, excludes join- entries
  - GET /api/cache/{hash}/audio returns WAV bytes or 404

Endpoint tests build a minimal FastAPI app that mounts only the cache
router (no engine, no ML imports) so they run fast without a GPU or
the 5.4 GB vibevoice weights.
"""

from __future__ import annotations

import struct
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT))

import pytest  # noqa: E402

from backend.services.synth_cache import SynthCache  # noqa: E402
from backend.api.cache import _derive_name  # noqa: E402


# ---------------------------------------------------------------------------
# Minimal valid WAV helper
# ---------------------------------------------------------------------------

def _make_wav(num_samples: int = 100, sample_rate: int = 24000) -> bytes:
    """Return a minimal 16-bit mono PCM WAV with `num_samples` silent samples."""
    num_channels = 1
    bits_per_sample = 16
    byte_rate = sample_rate * num_channels * bits_per_sample // 8
    block_align = num_channels * bits_per_sample // 8
    pcm_data = b"\x00\x00" * num_samples
    data_size = len(pcm_data)
    riff_size = 36 + data_size
    header = struct.pack(
        "<4sI4s4sIHHIIHH4sI",
        b"RIFF",
        riff_size,
        b"WAVE",
        b"fmt ",
        16,                 # fmt chunk size
        1,                  # PCM format
        num_channels,
        sample_rate,
        byte_rate,
        block_align,
        bits_per_sample,
        b"data",
        data_size,
    )
    return header + pcm_data


# ---------------------------------------------------------------------------
# Unit tests: SynthCache text/voice round-trip
# ---------------------------------------------------------------------------

def test_put_stores_text_and_voice(tmp_path):
    """put() with text+voice stores them in the sidecar and CacheEntry."""
    cache = SynthCache(tmp_path)
    wav = _make_wav()
    entry, _ = cache.put(
        content_hash="abc123",
        wav_bytes=wav,
        sample_rate=24000,
        duration_sec=0.004,
        inference_ms=10,
        text="Hello world this is a test of naming",
        voice="Mike",
    )
    assert entry.text == "Hello world this is a test of naming"
    assert entry.voice == "Mike"


def test_load_index_restores_text_and_voice(tmp_path):
    """_load_index re-reads text/voice from the sidecar JSON."""
    cache1 = SynthCache(tmp_path)
    wav = _make_wav()
    cache1.put(
        content_hash="abc123",
        wav_bytes=wav,
        sample_rate=24000,
        duration_sec=0.004,
        inference_ms=10,
        text="Hello world this is a test of naming",
        voice="Mike",
    )

    # Force a fresh index reload by creating a new SynthCache over the same dir
    cache2 = SynthCache(tmp_path)
    entry = cache2.get("abc123")
    assert entry is not None
    assert entry.text == "Hello world this is a test of naming"
    assert entry.voice == "Mike"


def test_put_without_text_voice_legacy_defaults(tmp_path):
    """put() without text/voice stores None values (legacy entries)."""
    cache = SynthCache(tmp_path)
    wav = _make_wav()
    entry, _ = cache.put(
        content_hash="legacy001",
        wav_bytes=wav,
        sample_rate=24000,
        duration_sec=0.004,
        inference_ms=10,
    )
    assert entry.text is None
    assert entry.voice is None

    # Reload
    cache2 = SynthCache(tmp_path)
    e2 = cache2.get("legacy001")
    assert e2 is not None
    assert e2.text is None
    assert e2.voice is None


# ---------------------------------------------------------------------------
# Unit tests: _derive_name
# ---------------------------------------------------------------------------

def test_derive_name_from_long_text():
    """First 6 words, joined, trimmed to <=48 chars."""
    result = _derive_name(
        "Subscribe to the channel and follow my profile on social media",
        "abcd1234ef",
    )
    # Should start with the first words
    assert result.startswith("Subscribe to the channel")
    assert len(result) <= 48


def test_derive_name_none_falls_back():
    """None text → 'Generation <hash8>'."""
    assert _derive_name(None, "abcd1234ef") == "Generation abcd1234"


def test_derive_name_empty_string_falls_back():
    """Empty text → 'Generation <hash8>'."""
    assert _derive_name("", "abcd1234ef") == "Generation abcd1234"


def test_derive_name_whitespace_only_falls_back():
    """Whitespace-only text → 'Generation <hash8>'."""
    assert _derive_name("   ", "abcd1234ef") == "Generation abcd1234"


def test_derive_name_short_text():
    """Short text (fewer than 6 words) is returned as-is."""
    result = _derive_name("Hello world", "abcd1234ef")
    assert result == "Hello world"


def test_derive_name_exactly_six_words():
    """Exactly 6 words — all included."""
    result = _derive_name("one two three four five six", "abcd1234ef")
    assert result == "one two three four five six"


def test_derive_name_truncated_to_48_chars():
    """Very long first 6 words still trim to <=48 chars."""
    long_text = "averylongword " * 6
    result = _derive_name(long_text, "abcd1234ef")
    assert len(result) <= 48


# ---------------------------------------------------------------------------
# Helpers for endpoint tests
# ---------------------------------------------------------------------------

def _make_cache_app(cache_dir: Path):
    """Build a minimal FastAPI app with only the cache router mounted.

    Does NOT import EngineManager, vibevoice, or any ML library.
    The SynthCache is injected directly into app.state so the deps work.
    """
    from fastapi import FastAPI
    from fastapi.testclient import TestClient
    from backend.api.cache import router as cache_router

    app = FastAPI()
    app.include_router(cache_router)

    cache = SynthCache(cache_dir)
    app.state.synth_cache = cache

    return app, cache


# ---------------------------------------------------------------------------
# Endpoint tests: GET /api/cache and GET /api/cache/{hash}/audio
# ---------------------------------------------------------------------------

def test_list_cache_includes_text_voice_name(tmp_path):
    """GET /api/cache returns entries with text, voice, name fields."""
    from fastapi.testclient import TestClient

    app, cache = _make_cache_app(tmp_path / "cache")
    wav = _make_wav()
    cache.put(
        content_hash="deadbeef0001",
        wav_bytes=wav,
        sample_rate=24000,
        duration_sec=0.004,
        inference_ms=10,
        text="Hello world from the test",
        voice="Alice",
    )

    with TestClient(app) as client:
        resp = client.get("/api/cache")
        assert resp.status_code == 200
        body = resp.json()
        entries = body["entries"]
        hashes = [e["hash"] for e in entries]
        assert "deadbeef0001" in hashes

        entry = next(e for e in entries if e["hash"] == "deadbeef0001")
        assert entry["text"] == "Hello world from the test"
        assert entry["voice"] == "Alice"
        # "Hello world from the test" = 5 words (fewer than 6), all included
        assert entry["name"] == "Hello world from the test"
        assert len(entry["name"]) <= 48


def test_list_cache_excludes_join_entries(tmp_path):
    """GET /api/cache does NOT include join- hash entries."""
    from fastapi.testclient import TestClient

    app, cache = _make_cache_app(tmp_path / "cache")
    wav = _make_wav()

    # Normal entry
    cache.put(
        content_hash="normal0001",
        wav_bytes=wav,
        sample_rate=24000,
        duration_sec=0.004,
        inference_ms=10,
        text="Normal clip text",
        voice="Bob",
    )
    # Join entry (export bundle) — should be excluded from listing
    cache.put(
        content_hash="join-deadbeef0001",
        wav_bytes=wav,
        sample_rate=24000,
        duration_sec=0.008,
        inference_ms=5,
    )

    with TestClient(app) as client:
        resp = client.get("/api/cache")
        assert resp.status_code == 200
        entries = resp.json()["entries"]
        hashes = [e["hash"] for e in entries]

        assert "normal0001" in hashes
        assert "join-deadbeef0001" not in hashes


def test_audio_endpoint_returns_wav(tmp_path):
    """GET /api/cache/{hash}/audio returns 200 with audio/wav content-type."""
    from fastapi.testclient import TestClient

    app, cache = _make_cache_app(tmp_path / "cache")
    wav = _make_wav()
    cache.put(
        content_hash="audio0001",
        wav_bytes=wav,
        sample_rate=24000,
        duration_sec=0.004,
        inference_ms=10,
        text="Some text",
        voice="Carol",
    )

    with TestClient(app) as client:
        resp = client.get("/api/cache/audio0001/audio")
        assert resp.status_code == 200
        assert resp.headers["content-type"].startswith("audio/")
        # Verify the response body is the WAV we stored
        assert resp.content == wav


def test_audio_endpoint_404_for_missing(tmp_path):
    """GET /api/cache/{hash}/audio returns 404 for an unknown hash."""
    from fastapi.testclient import TestClient

    app, cache = _make_cache_app(tmp_path / "cache")

    with TestClient(app) as client:
        resp = client.get("/api/cache/doesnotexist/audio")
        assert resp.status_code == 404


def test_open_folder_invokes_file_manager(tmp_path, monkeypatch):
    """POST /api/cache/folder opens the cache dir via the OS file manager."""
    from fastapi.testclient import TestClient
    import backend.api.cache as cache_api

    app, cache = _make_cache_app(tmp_path / "cache")
    opened: list = []
    monkeypatch.setattr(cache_api, "_open_in_file_manager", lambda p: opened.append(p))

    with TestClient(app) as client:
        resp = client.post("/api/cache/folder")
        assert resp.status_code == 200
        assert resp.json()["opened"] == str(cache.dir)
    # The opener was called exactly once with the cache directory.
    assert len(opened) == 1 and str(opened[0]) == str(cache.dir)
