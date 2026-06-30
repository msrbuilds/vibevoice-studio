import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT))

import soundfile as sf  # noqa: E402
import numpy as np  # noqa: E402

from backend.services.voices import VoiceRegistry  # noqa: E402


def _make_registry(tmp_path):
    voices = tmp_path / "voices"
    uploads = tmp_path / "uploads"
    voices.mkdir(exist_ok=True)
    uploads.mkdir(exist_ok=True)
    # one upload voice
    sr = 24000
    sf.write(str(uploads / "user-test-abc123.wav"), np.zeros(sr, dtype="int16"), sr)
    return VoiceRegistry(voices_dir=voices, uploads_dir=uploads)


def test_reference_transcript_round_trips(tmp_path):
    reg = _make_registry(tmp_path)
    reg.update_meta("user-test-abc123", reference_transcript="hello world")
    assert reg.get_reference_transcript("user-test-abc123") == "hello world"
    # New registry reading the same dir sees the persisted transcript.
    reg2 = _make_registry(tmp_path)
    info = next(v for v in reg2.list() if v.id == "user-test-abc123")
    assert info.reference_transcript == "hello world"


def test_reference_transcript_absent_is_none(tmp_path):
    reg = _make_registry(tmp_path)
    assert reg.get_reference_transcript("user-test-abc123") is None
