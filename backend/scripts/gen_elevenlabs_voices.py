"""Generate natural-sounding voice reference clips via ElevenLabs API.

Output: two ~15-second WAV files in backend/voices/, used as voice conditioning
audio for VibeVoice-1.5B.

Requirements:
    pip install elevenlabs
    set ELEVENLABS_API_KEY in your environment (or in a .env file at the
    project root).

The "male" and "female" voices are chosen from ElevenLabs' pre-made voice
library — replace the voice IDs with any other voice you have access to.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

BACKEND_DIR = Path(__file__).resolve().parent.parent
VOICES_DIR = BACKEND_DIR / "voices"
VOICES_DIR.mkdir(parents=True, exist_ok=True)

# Pre-made voice IDs from ElevenLabs' library. Both speak English clearly
# with natural prosody. Swap these for any other voice IDs you like — find
# them at https://elevenlabs.io/app/voice-library
MALE_VOICE_ID = "pNInz6obpgDQGcFmaJgB"    # Adam — deep, clear, conversational
FEMALE_VOICE_ID = "21m00Tcm4TlvDq8ikWAM"  # Rachel — warm, calm, mid-range

# Same text used for both voices, neutral content (no music references, no
# exclamations — keeps the cloned voice natural across the model).
SCRIPT = (
    "Hello, my name is a generic speaker, and I will be recording a short "
    "passage for a text-to-speech system. The weather today is calm, and "
    "people are going about their daily routines. It is a perfectly ordinary "
    "morning, and I am happy to share this moment with you. This recording "
    "will help create a natural sounding voice for synthetic speech."
)


def generate(voice_id: str, voice_label: str, out_path: Path) -> bool:
    api_key = os.environ.get("ELEVENLABS_API_KEY")
    if not api_key:
        print(f"  {voice_label}: ELEVENLABS_API_KEY not set; skipping")
        return False

    try:
        from elevenlabs.client import ElevenLabs
        from elevenlabs import save
    except ImportError:
        print("  elevenlabs SDK not installed. Run: pip install elevenlabs")
        return False

    print(f"  {voice_label}: requesting audio from ElevenLabs (voice_id={voice_id})…")
    client = ElevenLabs(api_key=api_key)
    audio = client.generate(
        text=SCRIPT,
        voice=voice_id,
        model_id="eleven_multilingual_v2",
        # Output format: PCM 24 kHz mono — exactly what the 1.5B model wants.
        output_format="pcm_24000",
    )

    # `save` writes to a file. The SDK accepts a generator and writes raw PCM
    # bytes (no WAV header) for the pcm_24000 format — we'll wrap it below.
    save(audio, str(out_path))

    # The save() helper for pcm_24000 writes raw PCM. Add a WAV header so
    # the 1.5B processor (and any audio player) can read it.
    raw = out_path.read_bytes()
    if not raw.startswith(b"RIFF"):
        from scipy.io import wavfile
        import numpy as np

        # raw is int16 little-endian PCM at 24 kHz mono
        samples = np.frombuffer(raw, dtype="<i2")
        wavfile.write(str(out_path), 24_000, samples)

    size = out_path.stat().st_size
    print(f"  {voice_label}: wrote {out_path.name} ({size} bytes)")
    return True


def main() -> int:
    if not os.environ.get("ELEVENLABS_API_KEY"):
        print(
            "ELEVENLABS_API_KEY is not set.\n"
            "\n"
            "1. Sign up at https://elevenlabs.io/ (free tier is fine for this).\n"
            "2. Copy your API key from the profile page.\n"
            "3. Either:\n"
            "   - Run in PowerShell:  $env:ELEVENLABS_API_KEY = \"sk-...\"\n"
            "   - Or create backend\\.env with:  ELEVENLABS_API_KEY=sk-...\n"
            "   - Or set it as a Windows environment variable.\n"
        )
        return 1

    print(f"Writing reference voices to: {VOICES_DIR}")
    ok = 0
    ok += generate(MALE_VOICE_ID, "male", VOICES_DIR / "en-male.wav")
    ok += generate(FEMALE_VOICE_ID, "female", VOICES_DIR / "en-female.wav")

    if ok == 0:
        print("\nNo voices generated. Check your API key and try again.")
        return 1

    print(f"\nGenerated {ok}/2 voice(s). Restart the backend to pick them up.")
    print("Then in the UI, pick the new voices in the sidebar.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
