# Built-in voices

This directory holds reference audio samples used as voice conditioning for
VibeVoice-1.5B. The 1.5B model is **single-speaker**: voice identity is
controlled by passing a reference `.wav` (10–30 seconds of clean speech from
one speaker) to the processor.

We ship 4 default voices by convention:

- `en-Carter_man.wav`
- `en-Emma_woman.wav`
- `en-Frank_man.wav`
- `en-Grace_woman.wav`

## Adding your own built-in voice

1. Record or download a clean 10–30s mono WAV at 16 kHz – 48 kHz, single speaker.
2. Save it here with the filename pattern `<lang>-<Name>_<gender>.wav` (the
   gender suffix is used by the frontend to label the speaker; it's optional).
3. Restart the backend. The voice will appear in `GET /api/voices` with
   `source: "builtin"` and be selectable from the sidebar.

You can also upload voices from the UI — those land in `../uploads/` and
remain deletable from the sidebar.

## Sourcing the shipped voices

If the four files aren't present at first boot, the app will start with an
empty built-in list (the sidebar will still show any voices you upload).
To populate them, the canonical sources are:

- The archived `demo/voices/` directory from the original `microsoft/VibeVoice`
  repo (mirror: <https://github.com/vibevoice-community/VibeVoice>)
- The Hugging Face Space `microsoft/vibevoice-1.5b-demo`

Drop the resulting `.wav` files into this directory and restart.
