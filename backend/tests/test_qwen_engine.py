"""QwenEngine proxy tests: capabilities, voices, message building (no subprocess)."""

import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT))

from backend.core.engines import EngineSynthRequest  # noqa: E402
from backend.core.engines.qwen_engine import QwenEngine  # noqa: E402


def _eng():
    return QwenEngine()


def test_capabilities():
    e = _eng()
    assert e.name == "qwen"
    assert e.sample_rate() == 24000
    assert e.supports_voice_cloning() is True
    assert e.supports_voice_modes() is True
    assert e.supports_style_clone() is False
    assert e.supports_streaming() is False
    assert e.default_cfg_scale() is None


def test_nine_builtin_voices():
    voices = _eng().available_voices()
    ids = {v.id for v in voices}
    assert ids == {
        "Vivian", "Serena", "Uncle_Fu", "Dylan", "Eric",
        "Ryan", "Aiden", "Ono_Anna", "Sohee",
    }
    vivian = next(v for v in voices if v.id == "Vivian")
    assert vivian.source == "builtin"
    assert vivian.gender == "woman"
    assert vivian.language == "zh"
    assert "young female" in vivian.name.lower()


def test_languages_include_auto_first():
    langs = _eng().languages()
    codes = [l["code"] for l in langs]
    assert codes[0] == "Auto"
    assert "Chinese" in codes and "English" in codes
    assert len(codes) == 11  # Auto + 10


def test_build_msg_custom_mode():
    msg = _eng()._build_synth_msg(
        EngineSynthRequest(text="hi", voice_id="Vivian", voice_mode="custom",
                           instruct="cheerful", language_id="English"), "/tmp/o.wav")
    assert msg["mode"] == "custom"
    assert msg["speaker"] == "Vivian"
    assert msg["instruct"] == "cheerful"
    assert msg["language"] == "English"
    assert "ref_audio" not in msg


def test_build_msg_custom_defaults_when_mode_absent():
    msg = _eng()._build_synth_msg(EngineSynthRequest(text="hi", voice_id="Aiden"), "/tmp/o.wav")
    assert msg["mode"] == "custom"
    assert msg["speaker"] == "Aiden"


def test_build_msg_clone_mode():
    msg = _eng()._build_synth_msg(
        EngineSynthRequest(text="hi", voice_id="", voice_mode="clone", reference_audio="/tmp/r.wav",
                           reference_text="hello"), "/tmp/o.wav")
    assert msg["mode"] == "clone"
    assert msg["ref_audio"] == "/tmp/r.wav"
    assert msg["ref_text"] == "hello"
    assert "speaker" not in msg


def test_build_msg_design_mode():
    msg = _eng()._build_synth_msg(
        EngineSynthRequest(text="hi", voice_id="", voice_mode="design", instruct="a calm man"), "/tmp/o.wav")
    assert msg["mode"] == "design"
    assert msg["instruct"] == "a calm man"
    assert "speaker" not in msg and "ref_audio" not in msg


def test_build_msg_custom_requires_speaker():
    try:
        _eng()._build_synth_msg(EngineSynthRequest(text="hi", voice_id="", voice_mode="custom"), "/tmp/o.wav")
    except ValueError:
        return
    raise AssertionError("expected ValueError: custom mode needs a speaker")
