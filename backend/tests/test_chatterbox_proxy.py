"""Tests for the Chatterbox proxy engine using a STUB worker.

No real chatterbox-tts is required: we point the proxy at a tiny stub
worker script run by the MAIN venv's Python. The stub speaks the same
JSON protocol and writes a small valid WAV.
"""

import sys
import textwrap
import wave
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT))

from backend.core.engines import EngineSynthRequest  # noqa: E402
from backend.core.engines.chatterbox_engine import ChatterboxEngine  # noqa: E402

# A stub worker: same protocol, writes 100 samples of silence as a WAV.
_STUB_WORKER = textwrap.dedent('''
    import json, sys, wave
    def reply(o): sys.stdout.write(json.dumps(o)+"\\n"); sys.stdout.flush()
    for line in sys.stdin:
        line = line.strip()
        if not line: continue
        req = json.loads(line)
        op = req.get("op")
        if op == "load":
            reply({"ok": True})
        elif op == "synth":
            with wave.open(req["out_wav"], "wb") as w:
                w.setnchannels(1); w.setsampwidth(2); w.setframerate(24000)
                w.writeframes(b"\\x00\\x00" * 100)
            reply({"ok": True, "sample_rate": 24000, "duration_sec": 100/24000, "inference_ms": 7})
        elif op == "shutdown":
            reply({"ok": True}); break
        else:
            reply({"ok": False, "error": "bad op"})
''')


def _make_stub_engine(tmp_path: Path) -> ChatterboxEngine:
    stub = tmp_path / "stub_worker.py"
    stub.write_text(_STUB_WORKER, encoding="utf-8")
    return ChatterboxEngine(
        worker_python=Path(sys.executable),  # the main venv python runs the stub
        worker_script=stub,
    )


def test_load_then_is_loaded(tmp_path):
    eng = _make_stub_engine(tmp_path)
    assert eng.is_loaded() is False
    eng.load()
    assert eng.is_loaded() is True
    eng.unload()
    assert eng.is_loaded() is False


def test_synthesize_returns_wav_bytes(tmp_path):
    eng = _make_stub_engine(tmp_path)
    eng.load()
    ref = tmp_path / "ref.wav"
    ref.write_bytes(b"RIFF")  # stub ignores contents
    req = EngineSynthRequest(
        text="hello", voice_id="x", reference_audio=str(ref),
        language_id="en", cfg_weight=0.5, exaggeration=0.5,
    )
    result = eng.synthesize(req)
    assert result.sample_rate == 24000
    assert result.wav_bytes[:4] == b"RIFF"
    assert result.wav_bytes[8:12] == b"WAVE"
    eng.unload()


def test_load_raises_when_venv_missing(tmp_path):
    # Point at a non-existent python so the friendly error fires.
    eng = ChatterboxEngine(
        worker_python=tmp_path / "no" / "such" / "python.exe",
        worker_script=tmp_path / "missing_worker.py",
    )
    try:
        eng.load()
        assert False, "expected RuntimeError"
    except RuntimeError as exc:
        assert "studio.py models" in str(exc)


def test_capabilities_unchanged(tmp_path):
    eng = _make_stub_engine(tmp_path)
    assert eng.name == "chatterbox"
    assert eng.sample_rate() == 24000
    assert eng.max_speakers() == 1
    assert eng.supports_voice_cloning() is True
    assert eng.supports_streaming() is False
    assert eng.available_voices() == []
