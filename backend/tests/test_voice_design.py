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


import numpy as np  # noqa: E402

from backend.core.engines import EngineResult, EngineSynthRequest, wrap_pcm_as_wav  # noqa: E402
from backend.services.synthesize import (  # noqa: E402
    SynthRequest,
    SynthService,
    Speaker,
    _voice_cache_key,
)


def test_voice_cache_key_diverges_by_mode_and_prompt():
    k_clone = _voice_cache_key("v", "clone", None, "/voices/v.wav")
    k_auto = _voice_cache_key("", "auto", None, None)
    k_d1 = _voice_cache_key("", "design", "female", None)
    k_d2 = _voice_cache_key("", "design", "male", None)
    assert len({k_clone, k_auto, k_d1, k_d2}) == 4          # all distinct
    assert _voice_cache_key("", "design", "female", None) == k_d1  # stable
    # Other engines (voice_mode None) keep their existing keys — no cache churn.
    assert _voice_cache_key("v", None, None, "/voices/v.wav") == "v.wav"
    assert _voice_cache_key("v", None, None, None) == "v"


class _StubEngine:
    name = "omnivoice"
    display_name = "OmniVoice"

    def __init__(self):
        self.last_req = None

    def is_loaded(self):
        return True

    def load(self):
        pass

    def max_speakers(self):
        return 1

    def supports_voice_cloning(self):
        return True

    def supports_streaming(self):
        return False

    def default_cfg_scale(self):
        return None

    def synthesize(self, req):
        self.last_req = req
        return EngineResult(
            wav_bytes=wrap_pcm_as_wav(np.zeros(100, dtype=np.int16), 24000),
            sample_rate=24000,
            duration_sec=100 / 24000,
            inference_ms=1,
        )


class _StubManager:
    def __init__(self, eng):
        self._eng = eng

    @property
    def active_engine(self):
        return self._eng

    @property
    def active_name(self):
        return "omnivoice"

    def get_engine(self, name):
        return self._eng


class _StubVoices:
    def get(self, voice_id):
        return f"/voices/{voice_id}.wav"

    def get_language(self, voice_id):
        return None


def _make_service():
    eng = _StubEngine()
    svc = SynthService(
        engine_manager=_StubManager(eng),
        voice_registry=_StubVoices(),
        max_text_chars=5000,
        synth_timeout_s=30,
        default_cfg_scale=1.0,
        cache=None,
    )
    return svc, eng


def test_design_request_skips_voice_and_threads_mode():
    svc, eng = _make_service()
    svc.synthesize(SynthRequest(
        text="hello",
        speakers=[Speaker(name="A", voice_id="", voice_mode="design", instruct="female, warm")],
    ))
    assert eng.last_req.voice_mode == "design"
    assert eng.last_req.instruct == "female, warm"
    assert eng.last_req.reference_audio is None


def test_auto_request_needs_no_voice():
    svc, eng = _make_service()
    svc.synthesize(SynthRequest(
        text="hello",
        speakers=[Speaker(name="A", voice_id="", voice_mode="auto")],
    ))
    assert eng.last_req.voice_mode == "auto"
    assert eng.last_req.reference_audio is None


def test_clone_request_resolves_reference_audio():
    svc, eng = _make_service()
    svc.synthesize(SynthRequest(
        text="hello",
        speakers=[Speaker(name="A", voice_id="v", voice_mode="clone")],
    ))
    assert eng.last_req.reference_audio == "/voices/v.wav"
    assert eng.last_req.voice_mode == "clone"


def test_multiline_design_threads_mode():
    svc, eng = _make_service()
    svc.synthesize(SynthRequest(
        text="line one\nline two",
        speakers=[Speaker(name="A", voice_id="", voice_mode="design", instruct="warm")],
    ))
    assert eng.last_req.voice_mode == "design"
    assert eng.last_req.instruct == "warm"


def test_clone_empty_voice_raises_for_non_omnivoice():
    import pytest
    from backend.core.exceptions import TextInvalid

    eng = _StubEngine()

    class _VibeManager(_StubManager):
        @property
        def active_name(self):
            return "vibevoice"

    svc = SynthService(
        engine_manager=_VibeManager(eng),
        voice_registry=_StubVoices(),
        max_text_chars=5000,
        synth_timeout_s=30,
        default_cfg_scale=1.0,
        cache=None,
    )
    with pytest.raises(TextInvalid):
        svc.synthesize(SynthRequest(text="hi", speakers=[Speaker(name="A", voice_id="")]))


def test_download_segment_allows_empty_voice_with_mode():
    from backend.api.download import DownloadSegment
    s = DownloadSegment(text="hi", voice="", voice_mode="design", instruct="female")
    assert s.voice == "" and s.voice_mode == "design" and s.instruct == "female"


def test_join_canonical_diverges_by_mode_and_prompt():
    from backend.api.download import DownloadSegment, _join_canonical
    base = dict(text="hi", voice="")
    d1 = [DownloadSegment(**base, voice_mode="design", instruct="female")]
    d2 = [DownloadSegment(**base, voice_mode="design", instruct="male")]
    auto = [DownloadSegment(**base, voice_mode="auto")]
    assert _join_canonical(d1, 150, 1.0) != _join_canonical(d2, 150, 1.0)
    assert _join_canonical(d1, 150, 1.0) != _join_canonical(auto, 150, 1.0)
    # backward-compat: a plain clone segment (no mode) still hashes
    clone = [DownloadSegment(text="hi", voice="v")]
    assert isinstance(_join_canonical(clone, 150, 1.0), str)
