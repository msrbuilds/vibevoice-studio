"""VoxCPMEngine proxy tests: message building + capability flags.

The proxy's _build_synth_msg is pure logic (no subprocess), so we test the
five-mode → worker-message mapping directly.
"""

import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT))

from backend.core.engines import EngineSynthRequest  # noqa: E402
from backend.core.engines.voxcpm_engine import VoxCPMEngine  # noqa: E402


def _eng():
    return VoxCPMEngine(inference_timesteps=10)


def test_capabilities():
    e = _eng()
    assert e.name == "voxcpm"
    assert e.sample_rate() == 48000
    assert e.max_speakers() == 1
    assert e.supports_voice_cloning() is True
    assert e.supports_voice_modes() is True
    assert e.supports_style_clone() is True
    assert e.supports_streaming() is False


def test_auto_message():
    msg = _eng()._build_synth_msg(
        EngineSynthRequest(text="hi", voice_id="", voice_mode="auto"), "/tmp/o.wav"
    )
    assert msg["mode"] == "auto"
    assert msg["text"] == "hi"
    assert "ref_audio" not in msg
    assert msg["inference_timesteps"] == 10


def test_design_message_carries_instruct():
    msg = _eng()._build_synth_msg(
        EngineSynthRequest(text="hi", voice_id="", voice_mode="design", instruct="warm"),
        "/tmp/o.wav",
    )
    assert msg["mode"] == "design"
    assert msg["instruct"] == "warm"
    assert "ref_audio" not in msg


def test_clone_message():
    msg = _eng()._build_synth_msg(
        EngineSynthRequest(text="hi", voice_id="v", voice_mode="clone", reference_audio="/tmp/v.wav"),
        "/tmp/o.wav",
    )
    assert msg["mode"] == "clone"
    assert msg["ref_audio"] == "/tmp/v.wav"
    assert "prompt_text" not in msg


def test_controllable_clone_carries_style():
    msg = _eng()._build_synth_msg(
        EngineSynthRequest(
            text="hi", voice_id="v", voice_mode="clone",
            reference_audio="/tmp/v.wav", instruct="cheerful",
        ),
        "/tmp/o.wav",
    )
    assert msg["ref_audio"] == "/tmp/v.wav"
    assert msg["instruct"] == "cheerful"


def test_ultimate_clone_carries_transcript():
    msg = _eng()._build_synth_msg(
        EngineSynthRequest(
            text="hi", voice_id="v", voice_mode="clone",
            reference_audio="/tmp/v.wav", reference_text="a transcript",
        ),
        "/tmp/o.wav",
    )
    assert msg["ref_audio"] == "/tmp/v.wav"
    assert msg["prompt_text"] == "a transcript"


def test_clone_without_ref_raises():
    try:
        _eng()._build_synth_msg(
            EngineSynthRequest(text="hi", voice_id="", voice_mode="clone"), "/tmp/o.wav"
        )
    except ValueError:
        return
    raise AssertionError("expected ValueError for clone with no reference")


def test_cfg_value_passed_through():
    msg = _eng()._build_synth_msg(
        EngineSynthRequest(text="hi", voice_id="", voice_mode="auto", cfg_scale=2.5),
        "/tmp/o.wav",
    )
    assert msg["cfg_value"] == 2.5


def test_design_ignores_reference_text():
    msg = _eng()._build_synth_msg(
        EngineSynthRequest(
            text="hi", voice_id="", voice_mode="design",
            instruct="warm", reference_text="leak",
        ),
        "/tmp/o.wav",
    )
    assert "prompt_text" not in msg
