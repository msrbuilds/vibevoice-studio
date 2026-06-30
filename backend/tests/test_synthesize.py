"""Unit tests for SynthService helpers (engine-agnostic)."""

from backend.services.synthesize import _voice_cache_key


def test_cache_key_folds_reference_transcript():
    plain = _voice_cache_key("v", "clone", None, "/tmp/v.wav", None, None)
    ult = _voice_cache_key("v", "clone", None, "/tmp/v.wav", "a transcript", None)
    assert plain != ult  # ultimate clone must not collide with plain clone


def test_cache_key_folds_timesteps():
    fast = _voice_cache_key("v", "clone", None, "/tmp/v.wav", None, 5)
    high = _voice_cache_key("v", "clone", None, "/tmp/v.wav", None, 25)
    assert fast != high


def test_cache_key_identical_inputs_collide():
    a = _voice_cache_key("v", "clone", None, "/tmp/v.wav", "t", 10)
    b = _voice_cache_key("v", "clone", None, "/tmp/v.wav", "t", 10)
    assert a == b


def test_cache_key_backwards_compatible_without_new_args():
    # Existing callers passing only the original 4 args still work via defaults.
    assert _voice_cache_key("v", None, None, None) == "v"
