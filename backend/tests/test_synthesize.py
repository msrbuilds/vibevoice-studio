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


def test_cache_key_folds_style_prompt_without_voice_mode():
    # Qwen (supports_style_prompt) sends an always-available style with
    # voice_mode None. Different styles must land in different slots.
    happy = _vck_qwen("Vivian", None, "cheerful", None)
    sad = _vck_qwen("Vivian", None, "somber", None)
    none = _vck_qwen("Vivian", None, None, None)
    assert happy != sad
    assert happy != none and sad != none
    assert none == "Vivian"  # absent style → no churn for other engines


# -- Qwen voice-mode resolution in SynthService._resolve_request_context ------

import numpy as np  # noqa: E402
import soundfile as sf  # noqa: E402

from backend.core.engine_manager import EngineManager  # noqa: E402
from backend.core.engines.qwen_engine import QwenEngine  # noqa: E402
from backend.services.synthesize import (  # noqa: E402
    Speaker,
    SynthRequest,
    SynthService,
)
from backend.services.voices import VoiceRegistry  # noqa: E402


class _LoadedQwen(QwenEngine):
    """Real QwenEngine surface (name=='qwen', supports_voice_modes()==True)
    but pretends to be loaded so _resolve_request_context never spawns the
    isolated worker subprocess."""

    def is_loaded(self) -> bool:
        return True

    def load(self) -> None:  # never spawn the worker in tests
        return None


def _qwen_svc(tmp_path) -> SynthService:
    """Build a SynthService whose active engine is a (stand-in) loaded Qwen."""
    voices_dir = tmp_path / "v"
    uploads_dir = tmp_path / "u"
    voices_dir.mkdir(parents=True, exist_ok=True)
    mgr = EngineManager(
        default_engine="qwen",
        voices_dir=voices_dir,
        uploads_dir=uploads_dir,
        model_id="vibevoice/VibeVoice-1.5B",
        device_request="cpu",
        state_dir=tmp_path,
    )
    # Swap the real (worker-spawning) Qwen engine for a loaded stand-in.
    mgr._engines["qwen"] = _LoadedQwen()
    mgr._active_name = "qwen"
    registry = VoiceRegistry(voices_dir, uploads_dir)
    return SynthService(
        engine_manager=mgr,
        voice_registry=registry,
        max_text_chars=5000,
        synth_timeout_s=60,
        default_cfg_scale=1.3,
    )


def test_qwen_custom_mode_skips_reference_resolution(tmp_path):
    """A Qwen custom-mode speaker with a built-in voice_id must NOT resolve
    a reference WAV — the voice_id is a built-in speaker name, not a clip."""
    svc = _qwen_svc(tmp_path)
    req = SynthRequest(
        text="hello world",
        speakers=[Speaker(name="A", voice_id="Vivian", voice_mode="custom")],
    )
    _eng, name, ref_audio, *_ = svc._resolve_request_context(req)
    assert name == "qwen"
    assert ref_audio is None


def test_qwen_default_mode_skips_reference_resolution(tmp_path):
    """No explicit voice_mode → Qwen default is 'custom', so still no WAV."""
    svc = _qwen_svc(tmp_path)
    req = SynthRequest(
        text="hello world",
        speakers=[Speaker(name="A", voice_id="Vivian")],
    )
    _eng, _name, ref_audio, *_ = svc._resolve_request_context(req)
    assert ref_audio is None


def test_qwen_clone_mode_resolves_reference(tmp_path):
    """A Qwen clone-mode speaker DOES resolve a reference WAV from the
    voice registry."""
    voices_dir = tmp_path / "v"
    voices_dir.mkdir(parents=True, exist_ok=True)
    sf.write(
        str(voices_dir / "myclip.wav"),
        np.zeros(24000, dtype=np.float32),
        24000,
        subtype="PCM_16",
    )
    svc = _qwen_svc(tmp_path)
    req = SynthRequest(
        text="hello world",
        speakers=[Speaker(name="A", voice_id="myclip", voice_mode="clone")],
    )
    _eng, _name, ref_audio, *_ = svc._resolve_request_context(req)
    assert ref_audio is not None
    assert ref_audio.endswith("myclip.wav")
