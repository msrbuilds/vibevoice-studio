"""Lightweight smoke tests that don't require the heavy model to actually load.

We DO require `vibevoice` and `transformers` to be importable, but we never
load the model weights. The ModelManager.load() path is exercised by patching
`from_pretrained` on the model/processor classes.

Run with: `python backend/tests/test_smoke.py`
"""

import sys
from pathlib import Path

BACKEND = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BACKEND.parent))

from fastapi.testclient import TestClient  # noqa: E402

# Patch the from_pretrained methods so load() doesn't actually fetch the
# 5.4 GB model. We do this *before* importing the app, so the lifespan
# hook doesn't try to download weights.
from vibevoice.modular.modeling_vibevoice_inference import (  # noqa: E402
    VibeVoiceForConditionalGenerationInference,
)
from vibevoice.processor.vibevoice_processor import VibeVoiceProcessor  # noqa: E402


class _StubProcessor:
    audio_processor = type("AP", (), {"sampling_rate": 24000})()
    tokenizer = object()

    def __call__(self, *a, **kw):
        # Return a minimal dict that synthesize_sync can iterate
        return {"input_ids": object(), "attention_mask": object()}


class _StubModel:
    def eval(self):
        return self

    def set_ddpm_inference_steps(self, num_steps):
        pass

    def generate(self, *a, **kw):
        import torch
        out = type(
            "Out",
            (),
            {"speech_outputs": [torch.zeros(24000, dtype=torch.float32)]},
        )()
        return out


# Replace from_pretrained with our stubs
_orig_proc_fp = VibeVoiceProcessor.from_pretrained
_orig_model_fp = VibeVoiceForConditionalGenerationInference.from_pretrained
VibeVoiceProcessor.from_pretrained = classmethod(lambda cls, *a, **kw: _StubProcessor())
VibeVoiceForConditionalGenerationInference.from_pretrained = classmethod(
    lambda cls, *a, **kw: _StubModel()
)


def _restore():
    VibeVoiceProcessor.from_pretrained = _orig_proc_fp
    VibeVoiceForConditionalGenerationInference.from_pretrained = _orig_model_fp


# Now import the app — its lifespan will call load() which uses our stubs
from backend.app import create_app  # noqa: E402
from backend.config import Settings  # noqa: E402


def _make_client(tmp_voices: Path, tmp_uploads: Path) -> TestClient:
    settings = Settings(
        model_id="vibevoice/VibeVoice-1.5B",
        device="cpu",
        voices_dir=tmp_voices,
        uploads_dir=tmp_uploads,
        log_level="warning",
    )
    app = create_app(settings)
    # The lifespan loads the model on startup. TestClient only runs lifespan
    # inside a `with` block, but each test wants to fire requests. We instead
    # call the model load manually right after construction.
    import asyncio
    try:
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        # Trigger the same code path that the lifespan startup uses.
        mm = app.state.model_manager
        mm.load()
    finally:
        loop.close()
    return TestClient(app)


def test_health_and_config(tmp_path):
    client = _make_client(tmp_path / "v", tmp_path / "u")
    r = client.get("/api/health")
    assert r.status_code == 200
    body = r.json()
    assert body["status"] == "ok"
    assert body["model_loaded"] is True

    r = client.get("/api/config")
    assert r.status_code == 200
    cfg = r.json()
    assert cfg["sampling_rate"] == 24000
    assert cfg["default_cfg_scale"] == 1.3


def test_voices_list_empty(tmp_path):
    """An empty filesystem still returns Kokoro's built-in voice catalog."""
    client = _make_client(tmp_path / "v", tmp_path / "u")
    r = client.get("/api/voices")
    assert r.status_code == 200
    body = r.json()
    # Filesystem empty; engine built-in voices (Kokoro + Qwen) should still
    # be present. Only built-in-voice engines contribute here.
    voices = body["voices"]
    assert all(v["engine"] in ("kokoro", "qwen") for v in voices)
    assert len(voices) >= 30
    # No uploads or built-in files were placed.
    assert not any(v["source"] == "upload" for v in voices)


def test_synthesize_empty_text_rejected(tmp_path):
    client = _make_client(tmp_path / "v", tmp_path / "u")
    r = client.post(
        "/api/synthesize",
        json={"text": "", "speakers": [{"name": "Alice", "voice": "v"}]},
    )
    assert r.status_code == 422


def test_synthesize_no_speakers_rejected(tmp_path):
    client = _make_client(tmp_path / "v", tmp_path / "u")
    r = client.post(
        "/api/synthesize",
        json={"text": "hello", "speakers": []},
    )
    assert r.status_code == 422


def test_synthesize_unknown_voice(tmp_path):
    client = _make_client(tmp_path / "v", tmp_path / "u")
    r = client.post(
        "/api/synthesize",
        json={"text": "hi", "speakers": [{"name": "Alice", "voice": "missing"}]},
    )
    assert r.status_code == 404
    assert r.json()["code"] == "voice_not_found"


def test_synthesize_too_many_speakers(tmp_path):
    client = _make_client(tmp_path / "v", tmp_path / "u")
    r = client.post(
        "/api/synthesize",
        json={
            "text": "hi",
            "speakers": [{"name": f"S{i}", "voice": "v"} for i in range(5)],
        },
    )
    assert r.status_code == 422


def test_upload_rejects_bad_extension(tmp_path):
    client = _make_client(tmp_path / "v", tmp_path / "u")
    r = client.post(
        "/api/voices/upload",
        files={"file": ("x.txt", b"not audio", "text/plain")},
    )
    assert r.status_code == 400


def test_synthesize_happy_path_with_stub(tmp_path):
    """Full synthesize flow with the stub model returning a 1s zero tensor."""
    # Create a fake built-in voice so the registry can resolve it
    (tmp_path / "v").mkdir(parents=True, exist_ok=True)
    import soundfile as sf
    import numpy as np
    sf.write(str(tmp_path / "v" / "en-test.wav"), np.zeros(24000, dtype=np.float32), 24000, subtype="PCM_16")

    client = _make_client(tmp_path / "v", tmp_path / "u")
    r = client.post(
        "/api/synthesize",
        json={
            "text": "Hello, this is a test.",
            "speakers": [{"name": "Alice", "voice": "en-test"}],
        },
    )
    assert r.status_code == 200
    assert r.headers["content-type"] == "audio/wav"
    body = r.content
    assert body[:4] == b"RIFF"  # WAV header
    assert int(r.headers["X-Sample-Rate"]) == 24000
    # Cache miss on the first call, hit on the second.
    assert "X-Cache-Hash" in r.headers
    assert r.headers.get("X-Cache") == "miss"
    r2 = client.post(
        "/api/synthesize",
        json={
            "text": "Hello, this is a test.",
            "speakers": [{"name": "Alice", "voice": "en-test"}],
        },
    )
    with open("debug.log", "a") as f:
        f.write(f"\n=== DEBUG: r1 headers === {dict(r.headers)}\n")
        f.write(f"=== DEBUG: r2 status === {r2.status_code} headers === {dict(r2.headers)}\n")
        f.write(f"=== DEBUG: r2 body === {r2.text[:500] if r2.status_code != 200 else '(wav)'}\n")
    assert r2.status_code == 200
    assert r2.headers.get("X-Cache") == "hit"
    assert r2.headers["X-Cache-Hash"] == r.headers["X-Cache-Hash"]
    # /api/cache should list the entry
    r3 = client.get("/api/cache")
    assert r3.status_code == 200
    body = r3.json()
    assert body["enabled"] is True
    assert body["entry_count"] >= 1
    # /api/cache/{hash} should delete it
    r4 = client.delete(f"/api/cache/{r.headers['X-Cache-Hash']}")
    assert r4.status_code == 200
    # And clear-all should succeed even with empty cache
    r5 = client.delete("/api/cache")
    assert r5.status_code == 200


def test_synthesize_canonical_speaker_tags(tmp_path):
    """The backend should emit canonical 'Speaker N:' tags regardless of input shape."""
    (tmp_path / "v").mkdir(parents=True, exist_ok=True)
    import soundfile as sf
    import numpy as np
    sf.write(str(tmp_path / "v" / "en-test.wav"), np.zeros(24000, dtype=np.float32), 24000, subtype="PCM_16")

    client = _make_client(tmp_path / "v", tmp_path / "u")
    # Plain text without tags — backend should wrap as Speaker 1
    r = client.post(
        "/api/synthesize",
        json={
            "text": "just plain text without any tags",
            "speakers": [{"name": "Alice", "voice": "en-test"}],
        },
    )
    assert r.status_code == 200, r.text
    # Multi-speaker with named tags (Alice:, Bob:) — backend should remap to Speaker 1/2
    r = client.post(
        "/api/synthesize",
        json={
            "text": "Alice: hi\nBob: hello",
            "speakers": [
                {"name": "Alice", "voice": "en-test"},
                {"name": "Bob", "voice": "en-test"},
            ],
        },
    )
    assert r.status_code == 200, r.text


def test_engines_list_and_activate(tmp_path):
    """Engine endpoints: list, activate, unknown engine."""
    client = _make_client(tmp_path / "v", tmp_path / "u")

    r = client.get("/api/engines")
    assert r.status_code == 200
    body = r.json()
    assert "active" in body and "engines" in body
    names = [e["name"] for e in body["engines"]]
    assert "vibevoice" in names and "kokoro" in names and "chatterbox" in names
    assert body["active"] == "vibevoice"
    assert any(e["name"] == "vibevoice" and e["active"] for e in body["engines"])

    # /api/config should also surface engines + active
    r = client.get("/api/config")
    assert r.status_code == 200
    cfg = r.json()
    assert cfg["active_engine"] == "vibevoice"
    assert any(e["name"] == "kokoro" for e in cfg["engines"])
    assert any(e["name"] == "chatterbox" for e in cfg["engines"])

    # Switch to kokoro
    r = client.post("/api/engines/activate", json={"name": "kokoro"})
    assert r.status_code == 200
    assert r.json()["name"] == "kokoro"
    assert r.json()["active"] is True

    r = client.get("/api/engines")
    assert r.json()["active"] == "kokoro"

    # Switch back
    r = client.post("/api/engines/activate", json={"name": "vibevoice"})
    assert r.status_code == 200

    # Unknown engine → 404
    r = client.post("/api/engines/activate", json={"name": "nope"})
    assert r.status_code == 404


def test_engines_voice_tag(tmp_path):
    """Every voice returned by /api/voices has an `engine` field set."""
    client = _make_client(tmp_path / "v", tmp_path / "u")
    r = client.get("/api/voices")
    assert r.status_code == 200
    for v in r.json()["voices"]:
        assert v["engine"] in ("kokoro", "vibevoice", "qwen")


if __name__ == "__main__":
    import tempfile

    with tempfile.TemporaryDirectory() as td:
        base = Path(td)
        tests = [
            test_health_and_config,
            test_voices_list_empty,
            test_synthesize_empty_text_rejected,
            test_synthesize_no_speakers_rejected,
            test_synthesize_unknown_voice,
            test_synthesize_too_many_speakers,
            test_upload_rejects_bad_extension,
            test_synthesize_happy_path_with_stub,
            test_synthesize_canonical_speaker_tags,
            test_engines_list_and_activate,
            test_engines_voice_tag,
        ]
        for fn in tests:
            try:
                fn(base)
                print(f"  PASS  {fn.__name__}")
            except AssertionError as e:
                import traceback
                print(f"  FAIL  {fn.__name__}: {e!r}")
                traceback.print_exc()
                sys.exit(1)
    _restore()
    print("OK")
