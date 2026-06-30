"""Tests for the VoxCPM worker's mode dispatch, using a fake voxcpm model."""

import importlib
import sys
import types
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT))


def _load_worker():
    # Import the worker module fresh (it imports voxcpm lazily inside _load, so
    # importing the module itself needs no fake).
    import backend.voxcpm_worker as w
    return importlib.reload(w)


def test_auto_mode_passes_plain_text():
    w = _load_worker()
    kwargs, mode = w._build_generate_kwargs(
        {"text": "hello", "mode": "auto", "cfg_value": 2.0, "inference_timesteps": 10}
    )
    assert mode == "auto"
    assert kwargs["text"] == "hello"
    assert "reference_wav_path" not in kwargs
    assert kwargs["cfg_value"] == 2.0
    assert kwargs["inference_timesteps"] == 10


def test_design_mode_prefixes_style():
    w = _load_worker()
    kwargs, mode = w._build_generate_kwargs(
        {"text": "hi", "mode": "design", "instruct": "a young woman, gentle"}
    )
    assert mode == "design"
    assert kwargs["text"] == "(a young woman, gentle)hi"
    assert "reference_wav_path" not in kwargs


def test_design_without_style_downgrades_to_auto():
    w = _load_worker()
    kwargs, mode = w._build_generate_kwargs({"text": "hi", "mode": "design", "instruct": ""})
    assert mode == "auto"
    assert kwargs["text"] == "hi"


def test_clone_mode_sets_reference():
    w = _load_worker()
    kwargs, mode = w._build_generate_kwargs(
        {"text": "hi", "mode": "clone", "ref_audio": "/tmp/v.wav"}
    )
    assert mode == "clone"
    assert kwargs["reference_wav_path"] == "/tmp/v.wav"
    assert kwargs["text"] == "hi"
    assert "prompt_text" not in kwargs


def test_controllable_clone_prefixes_style_with_reference():
    w = _load_worker()
    kwargs, mode = w._build_generate_kwargs(
        {"text": "hi", "mode": "clone", "ref_audio": "/tmp/v.wav", "instruct": "cheerful"}
    )
    assert kwargs["reference_wav_path"] == "/tmp/v.wav"
    assert kwargs["text"] == "(cheerful)hi"


def test_ultimate_clone_sets_prompt_wav_and_text():
    w = _load_worker()
    kwargs, mode = w._build_generate_kwargs(
        {"text": "hi", "mode": "clone", "ref_audio": "/tmp/v.wav", "prompt_text": "a transcript"}
    )
    assert kwargs["reference_wav_path"] == "/tmp/v.wav"
    assert kwargs["prompt_wav_path"] == "/tmp/v.wav"
    assert kwargs["prompt_text"] == "a transcript"


def test_clone_mode_requires_ref():
    w = _load_worker()
    try:
        w._build_generate_kwargs({"text": "hi", "mode": "clone"})
    except ValueError:
        return
    raise AssertionError("expected ValueError when clone mode lacks ref_audio")


def test_synth_end_to_end_with_fake_model(tmp_path):
    """_Worker._synth calls the fake model and writes a 48k WAV."""
    import numpy as np

    w = _load_worker()
    worker = w._Worker()

    class _FakeModel:
        class tts_model:
            sample_rate = 48000

        def generate(self, **kwargs):
            return np.zeros(48000, dtype=np.float32)  # 1 second of silence

    worker._model = _FakeModel()
    out = tmp_path / "out.wav"
    resp = worker._synth({"text": "hi", "mode": "auto", "out_wav": str(out)})
    assert resp["ok"] is True
    assert resp["sample_rate"] == 48000
    assert abs(resp["duration_sec"] - 1.0) < 0.01
    assert out.is_file() and out.stat().st_size > 0
