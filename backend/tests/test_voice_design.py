"""Spec B: OmniVoice voice_mode/instruct plumbing, cache-key divergence,
and design/auto voice-resolution skipping. No real model required."""

import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT))


def test_synth_speaker_model_allows_empty_voice_with_mode():
    from backend.api.schemas import SynthSpeakerModel
    m = SynthSpeakerModel(name="A", voice="", voice_mode="design", instruct="female, warm")
    assert m.voice == ""
    assert m.voice_mode == "design"
    assert m.instruct == "female, warm"


def test_synth_speaker_model_defaults():
    from backend.api.schemas import SynthSpeakerModel
    m = SynthSpeakerModel(name="A", voice="v")
    assert m.voice_mode is None
    assert m.instruct is None


def test_engine_synth_request_has_mode_fields():
    from backend.core.engines import EngineSynthRequest
    r = EngineSynthRequest(text="x", voice_id="v", voice_mode="auto", instruct=None)
    assert r.voice_mode == "auto"
    assert r.instruct is None
