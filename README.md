# Voice Studio by MSR

A local web UI for **multiple open-source TTS models** — switch engines from the UI; only one loads at a time to keep memory low:

- **VibeVoice-1.5B** (default) — Microsoft's multilingual voice-cloning model, up to 4 speakers, ~5.4 GB. MIT.
- **Kokoro-82M** by [hexgrad](https://huggingface.co/hexgrad/Kokoro-82M) — fast, lightweight (82M), built-in voices across English / Japanese / Mandarin. Apache-2.0.
- **Chatterbox Multilingual V3** by [Resemble AI](https://huggingface.co/ResembleAI/chatterbox) — zero-shot voice cloning across 23 languages. Runs in its own isolated environment. MIT.
- **OmniVoice** by [k2-fsa](https://huggingface.co/k2-fsa/OmniVoice) — 0.6B zero-shot multilingual TTS (600+ languages) with Clone / Design / Auto voice modes. Isolated environment. Apache-2.0.
- **VoxCPM2** by [OpenBMB](https://huggingface.co/openbmb/VoxCPM2) — 2B tokenizer-free TTS, 48 kHz, 30 languages, with voice design and controllable + transcript-guided cloning. Isolated environment. Apache-2.0.

Multi-segment **podcast editor** plus a single-textarea **text-to-voice** mode, voice uploads, per-voice cloning, GPU/CPU/MPS backend, fully offline after first run.

<img width="2536" height="1433" alt="Voice Studio by MSR" src="https://github.com/user-attachments/assets/78ad65a4-67c9-4902-8627-8c8532a7176e" />

```
┌──────────────────────────┐         ┌───────────────────────────┐
│  React + Vite + Tailwind  │  HTTP   │   FastAPI (Python 3.10+)  │
│  localhost:5173           │ ──────▶ │   localhost:8880          │
│  - Engine selector        │         │  5 engines, one loaded:   │
│  - Podcast / TTS modes    │         │   vibevoice · kokoro ·    │
│  - Voice library          │         │   chatterbox · omnivoice ·│
│  - Generate / Play / WAV  │         │   voxcpm                  │
│                           │         │  (chatterbox/omnivoice/   │
│                           │         │   voxcpm in isolated venvs│
│                           │         │   as subprocesses)        │
└──────────────────────────┘         └───────────────────────────┘
```

## Features

- **Five TTS engines, switchable from the UI** — VibeVoice, Kokoro, Chatterbox, OmniVoice, VoxCPM2; only one is loaded at a time. The isolated-environment engines (Chatterbox, OmniVoice, VoxCPM) **install / download weights / delete weights / uninstall** straight from the engine menu, with a live progress log.
- **Two project modes** — a multi-segment **Podcast** editor and a single-textarea **Text-to-Voice** mode (with char / word / duration counts). Each mode keeps its own buffer.
- **Voice modes** (OmniVoice & VoxCPM) — per-speaker **Clone / Design / Auto**. VoxCPM adds **controllable cloning** (clone + an inline style prompt) and **ultimate cloning** (reference + a per-voice transcript), plus a Fast / Balanced / High **Quality** control.
- **Multi-segment podcast editor** — author scripts with multiple speakers, generate each segment, play through, or export one joined WAV.
- **Per-segment cache** — re-running the same text+voice+cfg uses the cached WAV (model is deterministic). A **Regenerate** button forces a fresh take.
- **Backend disk cache** — `cache/` and `cache/downloads/` survive browser refreshes, server restarts, and model reloads.
- **Built-in voices** — drop `.wav / .mp3 / .flac / .ogg` files into `backend/voices/`; they're picked up on boot and listed in the sidebar.
- **Upload custom voices** from the UI — mono 1–60s clips, with name / gender / language fields, stored in `backend/uploads/`.
- **Multi-speaker scripts** — the 1.5B model supports up to 4 speakers; UI lets you assign a different voice to each speaker.
- **Edit voice metadata** — pencil icon next to any voice lets you change name / gender / language, plus an optional **reference transcript** (used by VoxCPM ultimate cloning); works for both built-in and uploaded voices.
- **Sample scripts** — built-in dropdown with English single-host, two-host interview, three-person panel, how-to tutorial, kids' story, and a Roman-Urdu two-friends chat.
- **Per-segment download** — download a single segment's WAV.
- **GPU / CPU / MPS** — auto-detects; falls back to CPU if CUDA is unavailable.
- **Theme toggle** — dark / light.
- **Fully offline** — no cloud, no telemetry, audio never leaves your machine.

## Prerequisites

- **Python 3.10+** (3.11 tested)
- **Node.js 18+** (Node 20 tested)
- **PyTorch** with CUDA support (Windows / Linux), or CPU-only (slower), or Apple Silicon (MPS, experimental)
- **Disk for model weights** (auto-downloaded on first use), per engine: Kokoro ~350 MB · Chatterbox ~500 MB · VoxCPM2 ~5 GB · VibeVoice ~5.4 GB · OmniVoice ~3.3 GB
- **VRAM**: ~3 GB for VibeVoice fp16, up to ~8 GB for VoxCPM2; CPU mode works (slow) on ~2–4 GB RAM
- **Isolated-environment engines** (Chatterbox, OmniVoice, VoxCPM) build their own venv on demand; **VoxCPM requires Python 3.10–3.12**
- **OS**: Windows 10/11, Linux, macOS

## Getting Started

### 1. Clone

```bash
git clone https://github.com/msrbuilds/voice-studio.git
cd voice-studio
```

### 2. Quick setup (recommended)

From the repo root, one command bootstraps everything — it creates the Python virtual environment, **auto-detects your GPU and installs the matching PyTorch/CUDA build**, installs the backend and frontend dependencies, checks system dependencies (`espeak-ng`, `ffmpeg`), and lets you **pick which models to download**:

```bash
python studio.py setup
```

Then launch the app — backend and frontend together, one command:

```bash
python studio.py start          # auto-selects dev/prod; Ctrl+C stops both
python studio.py start --dev    # backend (:8880) + Vite dev server (:5173), hot reload
python studio.py start --prod   # build the UI and serve it + the API on one port (:8880)
python studio.py models         # re-open the model picker anytime
```

Open <http://localhost:5173> (dev) or <http://localhost:8880> (prod). Flags after `start` pass through to the server, e.g. `python studio.py start --dev --device cuda --port 9000`.

> `studio.py` is the recommended path and only uses the Python standard library. If you'd rather wire things up by hand, the manual steps below do exactly the same thing.

> **Some engines install separately.** Chatterbox, OmniVoice, and VoxCPM each need a
> different (and mutually incompatible) `transformers` / `torch` stack, so each runs in
> its own isolated environment (`backend/venv-chatterbox`, `backend/venv-omnivoice`,
> `backend/venv-voxcpm`) as a subprocess. VibeVoice and Kokoro live in the main venv and
> are unaffected.
>
> Install them **from the app** — open the engine menu and click **Install** next to the
> engine; a dialog streams the build log, then **Download** fetches the weights, and you can
> switch to it right away. You can also remove an engine's weights (**Delete weights**) or its
> whole environment (**Uninstall**) from the same menu. Each non-default engine is built on
> demand; nothing is installed until you ask for it.

### Manual setup & running (alternative)

Prefer two terminals and explicit control? Set up and run each side yourself.

**Backend (Terminal 1):**

```bash
cd backend

# Create and activate a virtual environment
python -m venv venv
# Windows (PowerShell): .\venv\Scripts\Activate.ps1
# Windows (cmd):        .\venv\Scripts\activate.bat
# Linux / macOS:        source venv/bin/activate

# Install PyTorch FIRST with a CUDA-matched wheel (skip for CPU-only).
# Pick the cu121 / cu118 / cu124 wheel that matches your NVIDIA driver:
#   pip install torch torchaudio --index-url https://download.pytorch.org/whl/cu121
# Or CPU-only (smaller download, slower inference):
#   pip install torch torchaudio

# Install backend dependencies
pip install -r requirements.txt

# Run the backend (from the repo root, with the venv active)
cd ..
python -m backend.cli --engine vibevoice --device cuda   # engine: vibevoice | kokoro | chatterbox | omnivoice | voxcpm; device: cuda | cpu | mps
# (chatterbox / omnivoice / voxcpm must be installed first — see "Some engines install separately" above, or use `python studio.py setup`)
```

The first boot downloads the selected model's weights from HuggingFace into `backend/models/`. Subsequent boots use that local cache.

**Frontend (Terminal 2):**

```bash
cd frontend
npm install      # first time only
npm run dev
```

Open <http://localhost:5173>. The Vite dev server proxies `/api/*` to the backend on port 8880, so no CORS configuration is needed.

### CLI flags

```bash
python -m backend.cli --help
```

| Flag | Default | Description |
|---|---|---|
| `--engine` | `vibevoice` | Active engine: `vibevoice`, `kokoro`, `chatterbox`, `omnivoice`, or `voxcpm` (persists across restarts) |
| `--device` | `auto` | `auto`, `cuda`, `cpu`, or `mps` |
| `--port` | `8880` | HTTP port |
| `--model` | `vibevoice/VibeVoice-1.5B` | HF model id or local path (VibeVoice only) |
| `--kokoro-lang` | `a` | Kokoro lang code: `a` (US English), `b` (British), `j` (Japanese), `z` (Mandarin) |
| `--chatterbox-lang` | `en` | Default Chatterbox language id (e.g. `en`, `fr`, `ur`, `zh`) |
| `--models-dir` | `backend/models` | Where HuggingFace model weights are cached |
| `--voices-dir` | `backend/voices` | Built-in voice directory |
| `--uploads-dir` | `backend/uploads` | User-uploaded voice directory |
| `--log-level` | `info` | `debug`, `info`, `warning`, `error` |

> Isolated engines (`chatterbox`, `omnivoice`, `voxcpm`) load lazily on first use and must be installed first. Switching engines from the UI is the easiest path; `--engine` just sets the startup default.

## Adding voices

### Built-in voices (drop-in)

1. Find a clean 1–60 second clip of a single speaker in mono.
2. Convert to `.wav`, `.mp3`, `.flac`, or `.ogg` if it isn't already.
3. Drop the file into `backend/voices/` with a descriptive filename stem. The stem becomes the voice id.
4. (Optional) Add an entry to `backend/voices/voices.json` for a friendly name, gender, and language:

   ```json
   {
     "en_Amelia": {"name": "Amelia", "gender": "woman", "language": "en"},
     "ur_Hamza":  {"name": "Hamza",  "gender": "man",   "language": "ur"}
   }
   ```

5. **Restart the backend** (the directory is scanned on startup).

### Upload voices from the UI

1. Click the `+` next to **My voices** in the sidebar.
2. Pick a 1–60 second mono audio file (WAV / FLAC / OGG / MP3).
3. Fill in the name, gender (man / woman / non-binary), and language fields.
4. Hit **Upload**. The voice appears in **My voices** and is available to assign to any speaker.

You can also **edit** any voice's metadata by clicking the pencil icon next to it.

## Usage

### Quick start

1. Open <http://localhost:5173>.
2. The default "Host" speaker has no voice assigned. Pick one in the sidebar.
3. Click **Generate** on the first segment.
4. The audio plays and the cache icon lights up.
5. Click **Play** to replay, **Download** to save the segment WAV, or **Generate** to make a new take.

### Multi-segment podcast

1. Click **+** next to **Speakers** to add a second speaker (e.g., "Guest"). Pick a different voice.
2. Click **+** in the **Action bar** to add more segments.
3. Use the per-segment speaker dropdown to assign each segment to a speaker.
4. Click **Generate All** in the action bar to fill the audio cache.
5. Click **Play Podcast** to play through all segments in order.
6. Click **Download Audio** to export a single concatenated WAV with silence gaps.

### Sample scripts

The **Samples** dropdown in the action bar has ready-made scripts you can load to try things out:

- Two-host interview
- Single narrator
- Three-person panel
- How-to tutorial
- Kids' story
- Urdu/Hindi two-friends chat (Roman script)

### Regenerate

After a segment has audio, the button changes from **Generate** to **Regenerate**. Regenerate **bypasses the cache** and re-runs the model with the same text+voice, producing a different take. The new audio is then written back to the cache.

### Cache

The backend caches:

- **Per-segment audio** in `cache/<hash>.wav` (keyed by text + voice + cfg + voice samples).
- **Joined downloads** in `cache/downloads/<hash>.wav` (keyed by per-segment cache hashes + silence gap).

The cache survives browser refreshes, model reloads, and server restarts. You can browse and clear it from the **Cache** panel in the action bar.

A segment delete only removes it from the browser-side audio cache; orphan backend files can be cleared via the **Clear cache** action.

## API

Base URL: `http://localhost:8880/api`

| Method | Path | Description |
|---|---|---|
| `GET` | `/health` | `{status, model_loaded, device, version}` |
| `GET` | `/config` | `{model_id, device, dtype, sampling_rate, default_cfg_scale, active_engine, engines: […], …}` |
| `GET` | `/engines` | List engines + the active one, each with capabilities and `installed` / `downloaded` flags. |
| `POST` | `/engines/activate` | JSON `{name}`. Switch the active engine (unloads the previous one). |
| `POST` | `/engines/{name}/load` | Eagerly load an engine (UI spinner). |
| `GET` `POST` | `/engines/{name}/install` | Build / poll an isolated engine's venv (Chatterbox / OmniVoice / VoxCPM); streams a log. |
| `GET` `POST` | `/engines/{name}/download` | Download / poll an engine's weights with live progress. |
| `GET` `POST` | `/engines/{name}/delete-weights` | Remove an engine's cached weights with progress. |
| `GET` `POST` | `/engines/{name}/uninstall` | Remove an isolated engine's venv with progress. |
| `GET` | `/voices` | `{voices: [{id, name, source, engine, reference_transcript, …}]}` |
| `POST` | `/voices/upload` | multipart `file` + optional `name` / `gender` / `language`. Returns new voice metadata. |
| `POST` | `/voices/{id}/meta` | JSON `{name?, gender?, language?, reference_transcript?}`. Edits metadata for built-in or upload. |
| `DELETE` | `/voices/{id}` | 204 on success, 403 if `id` is built-in, 404 if missing. |
| `POST` | `/synthesize` | JSON `{text, speakers: [{name, voice, voice_mode?, instruct?}], cfg_scale?, cfg_weight?, exaggeration?, language_id?, inference_steps?, engine?, force_regenerate?}` → `audio/wav` (or `?response_format=base64`). Returns `X-Cache` and `X-Cache-Hash` headers. |
| `POST` | `/download` | JSON `{segments: [{text, voice, voice_mode?, instruct?, cfg_scale?, inference_steps?, cache_hash?}], silence_gap_ms}`. Returns joined WAV. Uses join cache. |
| `GET` | `/cache` | List all cache entries (hash, size, sample rate, duration, etc.). |
| `DELETE` | `/cache` | Clear all cache entries. |
| `DELETE` | `/cache/{hash}` | Delete a single cache entry. |
| `WS` | `/stream` | Stub — returns `{"streaming": "planned"}`. Streaming exists only for engines whose `supports_streaming()` is true. |

## Notes & gotchas

- **One engine loads at a time.** Switching engines unloads the previous model to keep memory low; the active choice persists across restarts (`backend/.last_engine`). Chatterbox, OmniVoice, and VoxCPM run as a subprocess in their own isolated venv (incompatible `transformers` / `torch` pins); VibeVoice and Kokoro share the main venv.
- **VibeVoice-1.5B supports up to 4 speakers** with voice cloning from short reference clips. Voice identity comes from a 1–60s clip you assign to each speaker in the sidebar. (Other engines synthesize one speaker per line and the backend concatenates, so multi-speaker scripts still work.)
- **Microsoft removed the original repo and code in Sept 2025** for responsible-AI reasons. The `vibevoice` Python package (from the community fork) and the 1.5B weights (from `microsoft/VibeVoice-1.5B` on HuggingFace) are how you run it now. The model embeds an audible AI disclaimer in every clip and logs a hashed request ID, per Microsoft's policy.
- **First-boot download is ~5.4 GB.** Model weights cache to `backend/models/` (override with the `MODELS_DIR` env var, `--models-dir` CLI flag, or `HF_HOME`).
- **Concurrent requests serialize.** The backend uses a single `threading.Lock` so two requests don't fight over the GPU. Set up a queue upstream if you need fan-out.
- **`max-text-chars` defaults to 5000.** The model's 64K-token context is much larger, but text > 5K chars risks OOM on smaller GPUs.
- **On Windows, install PyTorch from the official wheel index** before `pip install -r requirements.txt` — otherwise you get a CPU-only torch and CUDA will silently fall back to CPU.
- **CPU mode works** but is slow (RTF ~10–30×). For real use, run on a CUDA GPU. Apple Silicon (MPS) is supported but experimental.
- **Reference audio quality matters a lot.** Cloned voice sounds robotic if the reference clip is synthetic, low quality, has music in the background, or has reverb. Use a clean 24 kHz mono recording of natural speech.

## Troubleshooting

- **`backend not reachable` on the frontend** — make sure `python -m backend.cli` is running on port 8880 and didn't crash at startup. Tail the logs.
- **CUDA available but model runs on CPU** — you probably installed the CPU-only PyTorch wheel. Reinstall from `https://download.pytorch.org/whl/cu121` (or `cu118` / `cu124` matching your driver).
- **`flash_attn seems to be not installed`** — safe to ignore; the backend retries with `sdpa`.
- **`Kokoro failed to init for lang_code='j'`** — install the matching misaki extra: `pip install misaki[ja]`. Same for `'z'` (Mandarin) — `pip install misaki[zh]`.
- **Kokoro is silent / no audio** — `espeak-ng` is not on PATH. Install it (see "Notes & gotchas" above) and restart the backend.
- **Switched to Kokoro but old cached audio still plays** — the cache is per-engine, so the old VibeVoice audio remains valid. Click **Regenerate** on each segment to produce new Kokoro audio.
- **`out of memory` during generation** — switch to `--device cpu` or shorten the text. The backend returns 507 with a clear message and empties the CUDA cache.
- **No built-in voices in the sidebar** — drop a `.wav`/`.mp3`/`.flac`/`.ogg` into `backend/voices/` and restart the backend.
- **Generated voice sounds robotic** — your reference clip is too clean / synthetic / has reverb. Re-record with a real voice on a quiet room.
- **Regenerate button does nothing** — clear the audio cache from the **Cache** panel and try again. (Regenerate bypasses the cache; if audio still doesn't change, the model is genuinely producing the same output for the same input.)
- **`processor failed: float() argument must be a string or real number, not 'WindowsPath'`** — your backend is running an older version. Stop it (Ctrl+C), pull the latest code, and restart.
- **`No valid speaker lines found in script`** — your segment text needs to be wrapped as `Speaker 1: <text>`. The UI does this automatically when you pick a speaker; if you call the API directly, include the `speakers` array.

## Development

### Run the smoke tests (no model required)

```bash
cd backend
python -m pytest tests/  # or just: python tests/test_smoke.py
```

The smoke tests cover health, config, voices, synthesize (validation paths), upload, and the canonical speaker-tag normalization. They use a stubbed model and run in a few seconds.

### Frontend typecheck + build

```bash
cd frontend
npm run typecheck
npm run build
```

## License

**MIT** for the code in this repo. Each bundled engine keeps its own license and model-usage policy — review them before redistributing generated audio:

| Engine | License | Model card |
|---|---|---|
| VibeVoice-1.5B | MIT — embeds an audible AI disclaimer + hashed request ID in every clip | <https://huggingface.co/microsoft/VibeVoice-1.5B> |
| Kokoro-82M | Apache-2.0 | <https://huggingface.co/hexgrad/Kokoro-82M> |
| Chatterbox Multilingual V3 | MIT — PerTh neural watermark on by default | <https://huggingface.co/ResembleAI/chatterbox> |
| OmniVoice | Apache-2.0 | <https://huggingface.co/k2-fsa/OmniVoice> |
| VoxCPM2 | Apache-2.0 | <https://huggingface.co/openbmb/VoxCPM2> |
