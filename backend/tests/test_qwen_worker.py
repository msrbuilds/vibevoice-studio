"""Tests for the Qwen worker's 3-way dispatch (custom/clone/design, fake model)."""

import importlib
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT))


def _load_worker():
    import backend.qwen_worker as w
    return importlib.reload(w)


def test_language_normalized_to_package_vocabulary():
    w = _load_worker()
    # Display names (any case) and the voice's 2-letter codes both map to the
    # lowercase vocabulary generate_custom_voice accepts.
    def lang(v):
        return w._build_call({"mode": "custom", "text": "hi", "speaker": "Vivian", "language": v})[1]["language"]
    assert lang("English") == "english"
    assert lang("en") == "english"      # SynthService voice-language fallback
    assert lang("zh") == "chinese"
    assert lang("Japanese") == "japanese"
    assert lang("Auto") == "auto"
    assert lang("klingon") == "auto"    # unknown → auto, never raises
    assert lang(None) == "auto"


def test_max_new_tokens_scales_with_text():
    w = _load_worker()
    short = w._build_call({"mode": "custom", "text": "hi", "speaker": "Vivian"})[1]["max_new_tokens"]
    long = w._build_call({"mode": "custom", "text": "x" * 1000, "speaker": "Vivian"})[1]["max_new_tokens"]
    assert long >= short


def test_custom_mode_lowercases_speaker():
    w = _load_worker()
    op, kw = w._build_call({"mode": "custom", "text": "hi", "speaker": "Vivian", "language": "English"})
    assert op == "custom"
    assert kw["speaker"] == "vivian"
    assert kw["language"] == "english"
    assert kw["text"] == "hi"


def test_custom_mode_requires_speaker():
    w = _load_worker()
    try:
        w._build_call({"mode": "custom", "text": "hi"})
    except ValueError:
        return
    raise AssertionError("expected ValueError when custom mode lacks a speaker")


def test_clone_mode_icl_when_ref_text_present():
    w = _load_worker()
    op, kw = w._build_call({"mode": "clone", "text": "hi", "ref_audio": "/tmp/r.wav", "ref_text": "hello there"})
    assert op == "clone"
    assert kw["ref_audio"] == "/tmp/r.wav"
    assert kw["ref_text"] == "hello there"
    assert kw["x_vector_only_mode"] is False


def test_clone_mode_xvector_when_no_ref_text():
    w = _load_worker()
    op, kw = w._build_call({"mode": "clone", "text": "hi", "ref_audio": "/tmp/r.wav"})
    assert op == "clone"
    assert kw["x_vector_only_mode"] is True
    assert "ref_text" not in kw


def test_clone_mode_requires_ref_audio():
    w = _load_worker()
    try:
        w._build_call({"mode": "clone", "text": "hi"})
    except ValueError:
        return
    raise AssertionError("expected ValueError when clone mode lacks ref_audio")


def test_design_mode_requires_instruct():
    w = _load_worker()
    op, kw = w._build_call({"mode": "design", "text": "hi", "instruct": "a calm elderly man"})
    assert op == "design"
    assert kw["instruct"] == "a calm elderly man"
    try:
        w._build_call({"mode": "design", "text": "hi", "instruct": "  "})
    except ValueError:
        return
    raise AssertionError("expected ValueError when design mode lacks instruct")


def test_quality_kwargs_forwarded_in_every_mode():
    w = _load_worker()
    for req in (
        {"mode": "custom", "text": "hi", "speaker": "Vivian"},
        {"mode": "clone", "text": "hi", "ref_audio": "/tmp/r.wav"},
        {"mode": "design", "text": "hi", "instruct": "x"},
    ):
        _op, kw = w._build_call({**req, "temperature": 0.8, "top_p": 0.9})
        assert kw["temperature"] == 0.8 and kw["top_p"] == 0.9
        assert kw["max_new_tokens"] > 0


def test_synth_dispatches_to_method(tmp_path):
    import numpy as np
    w = _load_worker()
    worker = w._Worker()

    class _FakeModel:
        def __init__(self):
            self.called = None
        def generate_custom_voice(self, **k):
            self.called = "custom"; return [np.zeros(24000, dtype=np.float32)], 24000
        def generate_voice_clone(self, **k):
            self.called = "clone"; return [np.zeros(24000, dtype=np.float32)], 24000
        def generate_voice_design(self, **k):
            self.called = "design"; return [np.zeros(24000, dtype=np.float32)], 24000

    worker._model = _FakeModel()
    out = tmp_path / "o.wav"
    resp = worker._synth({"mode": "design", "text": "hi", "instruct": "calm", "out_wav": str(out)})
    assert resp["ok"] is True and worker._model.called == "design"
    assert out.is_file() and out.stat().st_size > 0
