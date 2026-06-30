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


from backend.services.synthesize import _voice_cache_key as _vck_qwen  # noqa: E402


def test_cache_key_folds_qwen_quality():
    base = dict(voice_id="Vivian", voice_mode=None, instruct=None, reference_audio=None)
    a = _vck_qwen(**base)
    b = _vck_qwen(**base, qwen_gen="t0.8|p0.9|k40|r1.1|s7")
    c = _vck_qwen(**base, qwen_gen="t0.5|p0.9|k40|r1.1|s7")
    assert a != b and b != c  # quality signature changes the slot


def test_cache_key_qwen_omitted_when_absent():
    # No qwen_gen → unchanged key (no churn for other engines)
    assert _vck_qwen("Vivian", None, None, None) == "Vivian"
