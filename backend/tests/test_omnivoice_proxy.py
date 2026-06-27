"""Tests for the OmniVoice proxy engine using a STUB worker + message builder.

No real omnivoice is required: we point the proxy at a tiny stub worker run by
the MAIN venv's Python, speaking the same JSON protocol.
"""

import sys
import textwrap
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT))

import pytest  # noqa: E402

from backend.core.engines import EngineSynthRequest  # noqa: E402
from backend.core.engines.omnivoice_engine import OmniVoiceEngine  # noqa: E402

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


def _make_stub_engine(tmp_path: Path) -> OmniVoiceEngine:
    stub = tmp_path / "stub_worker.py"
    stub.write_text(_STUB_WORKER, encoding="utf-8")
    return OmniVoiceEngine(worker_python=Path(sys.executable), worker_script=stub)


def test_capabilities():
    eng = OmniVoiceEngine(worker_python=Path("x"), worker_script=Path("y"))
    assert eng.name == "omnivoice"
    assert eng.sample_rate() == 24000
    assert eng.max_speakers() == 1
    assert eng.supports_voice_cloning() is True
    assert eng.supports_streaming() is False
    assert eng.default_cfg_scale() is None
    assert eng.available_voices() == []


def test_build_synth_msg_clone():
    eng = OmniVoiceEngine(worker_python=Path("x"), worker_script=Path("y"), num_step=24)
    req = EngineSynthRequest(text="hi", voice_id="v", reference_audio="/ref.wav", speed=1.2)
    msg = eng._build_synth_msg(req, "/out.wav")
    assert msg["op"] == "synth"
    assert msg["mode"] == "clone"
    assert msg["text"] == "hi"
    assert msg["ref_audio"] == "/ref.wav"
    assert msg["out_wav"] == "/out.wav"
    assert msg["speed"] == 1.2
    assert msg["num_step"] == 24


def test_build_synth_msg_requires_reference_audio():
    eng = OmniVoiceEngine(worker_python=Path("x"), worker_script=Path("y"))
    req = EngineSynthRequest(text="hi", voice_id="v")  # no reference_audio
    with pytest.raises(ValueError):
        eng._build_synth_msg(req, "/out.wav")


def test_load_then_synthesize_with_stub(tmp_path):
    eng = _make_stub_engine(tmp_path)
    assert eng.is_loaded() is False
    eng.load()
    assert eng.is_loaded() is True
    ref = tmp_path / "ref.wav"
    ref.write_bytes(b"RIFF")
    req = EngineSynthRequest(text="hello", voice_id="v", reference_audio=str(ref))
    result = eng.synthesize(req)
    assert result.sample_rate == 24000
    assert result.wav_bytes[:4] == b"RIFF"
    assert result.wav_bytes[8:12] == b"WAVE"
    eng.unload()
    assert eng.is_loaded() is False


def test_load_raises_when_venv_missing(tmp_path):
    eng = OmniVoiceEngine(
        worker_python=tmp_path / "no" / "such" / "python.exe",
        worker_script=tmp_path / "missing_worker.py",
    )
    with pytest.raises(RuntimeError) as exc:
        eng.load()
    assert "studio.py" in str(exc.value)


def test_installed_flag_requires_ready_marker(tmp_path):
    venv = tmp_path / "venv-omnivoice"
    (venv / "Scripts").mkdir(parents=True)
    py = venv / "Scripts" / "python.exe"
    py.write_text("", encoding="utf-8")
    eng = OmniVoiceEngine(worker_python=py, worker_script=tmp_path / "w.py")
    assert eng.installed() is False
    assert eng.info()["installed"] is False
    (venv / ".omnivoice-ready").write_text("ok", encoding="utf-8")
    assert eng.installed() is True
    assert eng.info()["installed"] is True
