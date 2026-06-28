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


def test_build_synth_msg_clone_requires_reference_audio():
    eng = OmniVoiceEngine(worker_python=Path("x"), worker_script=Path("y"))
    req = EngineSynthRequest(text="hi", voice_id="v", voice_mode="clone")  # explicit clone, no ref
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


def test_engine_manager_registers_omnivoice(tmp_path):
    from backend.core.engine_manager import EngineManager

    em = EngineManager(
        default_engine="vibevoice",
        voices_dir=tmp_path / "voices",
        uploads_dir=tmp_path / "uploads",
        model_id="vibevoice/VibeVoice-1.5B",
        device_request="cpu",
        state_dir=tmp_path,
    )
    names = [e.name for e in em.list_engines()]
    assert "omnivoice" in names
    eng = em.get_engine("omnivoice")
    assert eng.display_name == "OmniVoice"
    # `installed` reflects whether the isolated venv marker exists on this
    # machine, so don't assert its value — just that the engine reports it.
    assert "installed" in eng.info()


def test_build_synth_msg_design():
    eng = OmniVoiceEngine(worker_python=Path("x"), worker_script=Path("y"), num_step=20)
    req = EngineSynthRequest(text="hi", voice_id="", voice_mode="design", instruct="female, british accent")
    msg = eng._build_synth_msg(req, "/out.wav")
    assert msg["mode"] == "design"
    assert msg["instruct"] == "female, british accent"
    assert "ref_audio" not in msg
    assert msg["num_step"] == 20


def test_build_synth_msg_empty_design_becomes_auto():
    eng = OmniVoiceEngine(worker_python=Path("x"), worker_script=Path("y"))
    req = EngineSynthRequest(text="hi", voice_id="", voice_mode="design", instruct="   ")
    msg = eng._build_synth_msg(req, "/out.wav")
    assert msg["mode"] == "auto"
    assert "instruct" not in msg


def test_build_synth_msg_auto():
    eng = OmniVoiceEngine(worker_python=Path("x"), worker_script=Path("y"))
    req = EngineSynthRequest(text="hi", voice_id="", voice_mode="auto")
    msg = eng._build_synth_msg(req, "/out.wav")
    assert msg["mode"] == "auto"
    assert "ref_audio" not in msg
    assert "instruct" not in msg


def test_downloaded_probes_model_id(monkeypatch):
    from backend.core import model_cache

    seen = {}

    def fake_model_downloaded(repo_id):
        seen["repo_id"] = repo_id
        return True

    monkeypatch.setattr(model_cache, "model_downloaded", fake_model_downloaded)
    eng = OmniVoiceEngine(worker_python=Path("x"), worker_script=Path("y"))
    assert eng.downloaded() is True
    assert seen["repo_id"] == "k2-fsa/OmniVoice"
    assert eng.info()["downloaded"] is True


def test_downloaded_false_when_not_cached(monkeypatch):
    from backend.core import model_cache

    monkeypatch.setattr(model_cache, "model_downloaded", lambda repo_id: False)
    eng = OmniVoiceEngine(worker_python=Path("x"), worker_script=Path("y"))
    assert eng.downloaded() is False
    assert eng.info()["downloaded"] is False


def test_concurrent_load_calls_popen_once(tmp_path, monkeypatch):
    """Two threads calling load() simultaneously must spawn exactly one worker."""
    import threading
    import subprocess as _subprocess

    popen_count = 0
    count_lock = threading.Lock()
    real_popen = _subprocess.Popen

    def counting_popen(*args, **kwargs):
        nonlocal popen_count
        with count_lock:
            popen_count += 1
        return real_popen(*args, **kwargs)

    monkeypatch.setattr(
        "backend.core.engines.omnivoice_engine.subprocess.Popen",
        counting_popen,
    )

    eng = _make_stub_engine(tmp_path)
    barrier = threading.Barrier(2)
    thread_errors = []
    errors_lock = threading.Lock()

    def load_with_barrier():
        barrier.wait()
        try:
            eng.load()
        except Exception as exc:  # noqa: BLE001
            with errors_lock:
                thread_errors.append(exc)

    threads = [threading.Thread(target=load_with_barrier) for _ in range(2)]
    for t in threads:
        t.start()
    for t in threads:
        t.join(timeout=3.0)

    assert not any(t.is_alive() for t in threads), "threads did not finish — possible deadlock"
    assert thread_errors == [], f"threads raised: {thread_errors}"
    assert popen_count == 1
    assert eng.is_loaded() is True
    eng.unload()


def test_sequential_load_idempotent(tmp_path):
    """A second sequential load() reuses the existing worker proc."""
    eng = _make_stub_engine(tmp_path)
    eng.load()
    first_proc = eng._proc
    eng.load()
    assert eng._proc is first_proc
    eng.unload()
