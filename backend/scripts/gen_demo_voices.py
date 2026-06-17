"""Generate 4 short mono WAV reference clips for the VibeVoice 1.5B voice cloning.

Uses Windows' built-in SAPI5 TTS to synthesize a clean ~10 second clip for
each of the 4 default voices. The output is a 24 kHz mono PCM_16 WAV that
the model can use directly as voice conditioning audio.

Output files:
  backend/voices/en-Emma_woman.wav
  backend/voices/en-Carter_man.wav
  backend/voices/en-Frank_man.wav
  backend/voices/en-Grace_woman.wav

Run with: python -m backend.scripts.gen_demo_voices
"""

from __future__ import annotations

import sys
import tempfile
from pathlib import Path

VOICES_DIR = Path(__file__).resolve().parent.parent / "voices"

# Voice name, SAPI5 voice token to use (None = default), text to read.
# The text is intentionally plain (no exclamation, no music references) so
# the cloned voice stays neutral.
VOICES: list[tuple[str, str | None, str]] = [
    (
        "en-Emma_woman",
        "Microsoft Zira Desktop",
        "Hello, my name is Emma. I will be reading a short passage about everyday life. "
        "The weather today is calm, and people are going about their routines. "
        "It is a perfectly ordinary morning, and I am happy to share this moment with you.",
    ),
    (
        "en-Carter_man",
        "Microsoft David Desktop",
        "Hello, my name is Carter. I will be reading a short passage about everyday life. "
        "The weather today is calm, and people are going about their routines. "
        "It is a perfectly ordinary morning, and I am happy to share this moment with you.",
    ),
    (
        "en-Frank_man",
        "Microsoft Mark - English (United States)",
        "Hello, my name is Frank. I will be reading a short passage about everyday life. "
        "The weather today is calm, and people are going about their routines. "
        "It is a perfectly ordinary morning, and I am happy to share this moment with you.",
    ),
    (
        "en-Grace_woman",
        None,  # fall back to default
        "Hello, my name is Grace. I will be reading a short passage about everyday life. "
        "The weather today is calm, and people are going about their routines. "
        "It is a perfectly ordinary morning, and I am happy to share this moment with you.",
    ),
]


def _pick_voice(token: str | None) -> str | None:
    if token is None:
        return None
    # The pythoncom SAPI5 module needs a specific voice token. On Windows,
    # the easiest way is to instantiate the SAPI5.SpVoice COM object, but
    # we use the win32com.client wrapper for that. If unavailable, we skip.
    try:
        import win32com.client  # type: ignore
    except ImportError:
        return None
    try:
        sapi = win32com.client.Dispatch("SAPI.SpVoice")
        voices = sapi.GetVoices()
        for i in range(voices.Count):
            v = voices.Item(i)
            desc = v.GetDescription()
            if token in desc:
                return desc
    except Exception:
        return None
    return None


def synth_one(name: str, voice_token: str | None, text: str, out_path: Path) -> bool:
    """Synthesize one clip via SAPI5 and write a 24kHz mono PCM_16 WAV.

    Returns True on success.
    """
    try:
        import win32com.client  # type: ignore
    except ImportError:
        print("  pywin32 not installed; cannot generate reference voices.")
        print("  Install with: pip install pywin32")
        print("  Or use the UI to upload your own .wav files instead.")
        return False

    try:
        sapi = win32com.client.Dispatch("SAPI.SpVoice")
        # Try to find the requested voice
        if voice_token is not None:
            voices = sapi.GetVoices()
            for i in range(voices.Count):
                v = voices.Item(i)
                if voice_token in v.GetDescription():
                    sapi.Voice = v
                    break
        # Set rate slightly slower for naturalness (-2 on a scale of -10..10)
        try:
            sapi.Rate = -1
        except Exception:
            pass

        # SAPI5 can't write 24kHz PCM_16 directly to a wav file cleanly across
        # all Windows versions, so we route through an in-memory stream.
        # The simpler path: write to a temp .wav, then re-read with soundfile
        # and rewrite as 24kHz mono PCM_16.
        import pythoncom  # type: ignore
        from win32com.client import Dispatch  # type: ignore
        import soundfile as sf
        import numpy as np

        sp_file = Dispatch("SAPI.SpFileStream")
        sp_file.Format.Type = 22  # SAFT22kHz16BitMono (22050 Hz, 16-bit, mono)
        # SAPI also accepts 24kHz: SAFT24kHz16BitMono = 23
        sp_file.Format.Type = 23

        tmp_in = Path(tempfile.mkstemp(suffix=".wav")[1])
        try:
            sp_file.Open(str(tmp_in), 3, False)  # SSFMOpenForRead = 3
            sapi.AudioOutputStream = sp_file
            # 4 = SPF_IS_NOT_XML + SPF_PARSE_SAPI (use plain text), 1 = SPF_DEFAULT
            sapi.Speak(text, 1)
            # Commit
            try:
                sp_file.Close() if False else None
            except Exception:
                pass
            sapi.AudioOutputStream = None
        finally:
            try:
                sp_file.Close()
            except Exception:
                pass

        # Read the SAPI output, re-encode as 24 kHz mono PCM_16
        if not tmp_in.exists() or tmp_in.stat().st_size < 1000:
            print(f"  {name}: SAPI produced no/empty output")
            tmp_in.unlink(missing_ok=True)
            return False
        data, sr_in = sf.read(str(tmp_in), dtype="float32")
        if data.ndim > 1:
            data = data.mean(axis=1)
        # Resample to 24kHz if needed
        target_sr = 24_000
        if sr_in != target_sr:
            from scipy.signal import resample_poly
            from math import gcd
            g = gcd(sr_in, target_sr)
            data = resample_poly(data, target_sr // g, sr_in // g)
        sf.write(str(out_path), data.astype(np.float32), samplerate=target_sr, subtype="PCM_16")
        duration = len(data) / target_sr
        print(f"  {name}: {duration:.1f}s @ {target_sr}Hz -> {out_path.name} ({out_path.stat().st_size} bytes)")
        tmp_in.unlink(missing_ok=True)
        return True
    except Exception as exc:  # noqa: BLE001
        print(f"  {name}: failed: {exc!r}")
        return False


def main() -> int:
    VOICES_DIR.mkdir(parents=True, exist_ok=True)
    print(f"Writing reference voices to: {VOICES_DIR}")
    ok = 0
    for name, token, text in VOICES:
        out = VOICES_DIR / f"{name}.wav"
        if synth_one(name, token, text, out):
            ok += 1
    if ok == 0:
        print(
            "\nNone of the voices could be generated. The most reliable fallback is\n"
            "to record a 10-30 second clip of any speaker and upload it from the UI\n"
            "(+ button next to 'My voices' in the sidebar)."
        )
        return 1
    print(f"\nGenerated {ok}/{len(VOICES)} voice(s). Restart the backend to pick them up.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
