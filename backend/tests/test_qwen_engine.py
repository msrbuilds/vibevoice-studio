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
    assert e.max_speakers() == 1
    assert e.supports_voice_cloning() is False
    assert e.supports_voice_modes() is False
    assert e.supports_style_prompt() is True
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


def test_build_msg_basic():
    msg = _eng()._build_synth_msg(
        EngineSynthRequest(text="hi", voice_id="Vivian", language_id="English"), "/tmp/o.wav"
    )
    assert msg["speaker"] == "Vivian"
    assert msg["language"] == "English"
    assert msg["text"] == "hi"
    assert "instruct" not in msg


def test_build_msg_language_defaults_auto():
    msg = _eng()._build_synth_msg(
        EngineSynthRequest(text="hi", voice_id="Aiden"), "/tmp/o.wav"
    )
    assert msg["language"] == "Auto"


def test_build_msg_instruct_and_quality():
    msg = _eng()._build_synth_msg(
        EngineSynthRequest(
            text="hi", voice_id="Vivian", instruct="Very happy.",
            temperature=0.8, top_p=0.9, top_k=40, repetition_penalty=1.1, seed=7,
        ),
        "/tmp/o.wav",
    )
    assert msg["instruct"] == "Very happy."
    assert msg["temperature"] == 0.8
    assert msg["top_p"] == 0.9
    assert msg["top_k"] == 40
    assert msg["repetition_penalty"] == 1.1
    assert msg["seed"] == 7


def test_build_msg_requires_speaker():
    try:
        _eng()._build_synth_msg(EngineSynthRequest(text="hi", voice_id=""), "/tmp/o.wav")
    except ValueError:
        return
    raise AssertionError("expected ValueError when no voice/speaker")
