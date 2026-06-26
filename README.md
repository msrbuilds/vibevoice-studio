# Voice Studio by MSR

A local web UI for **multiple open-source TTS models**, starting with:

- **Microsoft VibeVoice-1.5B** (default) — multilingual voice cloning, ~5.4 GB
- **Kokoro-82M** by [hexgrad](https://huggingface.co/hexgrad/Kokoro-82M) — fast, lightweight, Apache-2.0, 38 built-in voices across English/Japanese/Mandarin

Multi-segment podcast editor, voice uploads, GPU/CPU/MPS backend, fully offline after first run.

<img width="2536" height="1433" alt="Voice Studio by MSR" src="https://github.com/user-attachments/assets/78ad65a4-67c9-4902-8627-8c8532a7176e" />

```
┌─────────────────────────┐         ┌──────────────────────────┐
│  React + Vite + Tailwind │  HTTP   │   FastAPI (Python 3.10+) │
│  localhost:5173          │ ──────▶ │   localhost:8880         │
│  - Engine selector       │         │  - vibevoice  (5.4 GB)   │
│  - Sidebar: speakers     │         │  - kokoro     (~350 MB)  │
│  - Segments list         │         │  - voices/ + uploads/    │
│  - Generate / Play / WAV │         │  - one engine loaded     │
└─────────────────────────┘         └──────────────────────────┘
```

## Quick Start

Requires Python 3.10+ (and Node.js 18+ for the dev UI). From the repo root:

```bash
python studio.py setup     # creates the venv, installs deps, auto-picks a PyTorch/CUDA build,
                           # checks system deps, and lets you choose which models to download
python studio.py start     # launches backend + frontend together (Ctrl+C stops both)
```

- `python studio.py start --dev` — backend (:8880) + Vite dev server (:5173), hot reload.
- `python studio.py start --prod` — builds the UI and serves it + the API on a single port (:8880); no Node needed at runtime.
- `python studio.py models` — re-open the model picker anytime.
- Flags after `start` pass through to the server, e.g. `python studio.py start --dev --device cuda --port 9000`.

The manual two-terminal setup below still works and remains the underlying primitive.

## Features

- **Multi-segment podcast editor** — author scripts with multiple speakers, generate each segment, play through, or export one joined WAV.
- **Per-segment cache** — re-running the same text+voice+cfg uses the cached WAV (model is deterministic). A **Regenerate** button forces a fresh take.
- **Backend disk cache** — `cache/` and `cache/downloads/` survive browser refreshes, server restarts, and model reloads.
- **Built-in voices** — drop `.wav / .mp3 / .flac / .ogg` files into `backend/voices/`; they're picked up on boot and listed in the sidebar.
- **Upload custom voices** from the UI — mono 1–60s clips, with name / gender / language fields, stored in `backend/uploads/`.
- **Multi-speaker scripts** — the 1.5B model supports up to 4 speakers; UI lets you assign a different voice to each speaker.
- **Edit voice metadata** — pencil icon next to any voice lets you change name / gender / language; works for both built-in and uploaded voices.
- **Sample scripts** — built-in dropdown with English single-host, two-host interview, three-person panel, how-to tutorial, kids' story, and a Roman-Urdu two-friends chat.
- **Per-segment download** — download a single segment's WAV.
- **GPU / CPU / MPS** — auto-detects; falls back to CPU if CUDA is unavailable.
- **Theme toggle** — dark / light.
- **Fully offline** — no cloud, no telemetry, audio never leaves your machine.

## Prerequisites

- **Python 3.10+** (3.11 tested)
- **Node.js 18+** (Node 20 tested)
- **PyTorch** with CUDA support (Windows / Linux), or CPU-only (slower), or Apple Silicon (MPS, experimental)
- **~6 GB disk** for the model weights (auto-downloaded on first run)
- **~3 GB VRAM** for fp16 inference; **~2 GB RAM** for CPU
- **OS**: Windows 10/11, Linux, macOS

## Installation

### 1. Clone

```bash
git clone https://github.com/<your-username>/vibe-podcast.git
cd vibe-podcast
```

### 2. Backend

```bash
cd backend

# Create and activate a virtual environment
python -m venv venv
# Windows (PowerShell):
.\venv\Scripts\Activate.ps1
# Windows (cmd):
.\venv\Scripts\activate.bat
# Linux / macOS:
source venv/bin/activate

# Install PyTorch FIRST with a CUDA-matched wheel.
# Skip this line if you only want CPU inference.
# Pick the cu121 / cu118 / cu124 wheel that matches your NVIDIA driver:
#   pip install torch torchaudio --index-url https://download.pytorch.org/whl/cu121
#
# Or, just install a CPU-only torch (smaller download, slower inference):
#   pip install torch torchaudio

# Install backend dependencies
pip install -r requirements.txt

# If pip fails with "WinError 2 ... cannot find the file specified"
# when installing `kokoro`, `weasel`, `spacy`, or `jsonschema`
# (these packages install CLI launchers to `C:\Python311\Scripts\`),
# run with `--user` to skip the Scripts write:
#   pip install --user -r requirements.txt
```

### 3. Frontend

```bash
cd ../frontend
npm install
```

## Running

You'll need two terminals — one for the backend, one for the frontend.

### Terminal 1 — Backend

```bash
cd backend

# Activate venv if you haven't already
# Windows (PowerShell): .\venv\Scripts\Activate.ps1
# Linux / macOS:        source venv/bin/activate

python -m backend.cli --device cuda   # or: cpu, mps
```

You should see:

```
[startup] Loading processor from microsoft/VibeVoice-1.5B …
[startup] Loading model weights (device=cuda, dtype=bfloat16, attn=sdpa) …
[startup] Model ready. sampling_rate=24000 Hz, attn=sdpa
INFO:     Uvicorn running on http://0.0.0.0:8880
```

The first boot downloads the **5.4 GB** `microsoft/VibeVoice-1.5B` weights from HuggingFace. Subsequent boots use the local cache (`~/.cache/huggingface/`).

### Terminal 2 — Frontend

```bash
cd frontend
npm run dev
```

Open <http://localhost:5173>. The Vite dev server proxies `/api/*` to the backend on port 8880, so no CORS configuration is needed.

### CLI flags

```bash
python -m backend.cli --help
```

| Flag | Default | Description |
|---|---|---|
| `--device` | `auto` | `auto`, `cuda`, `cpu`, or `mps` |
| `--port` | `8880` | HTTP port |
| `--model` | `microsoft/VibeVoice-1.5B` | HF model id or local path |
| `--voices-dir` | `backend/voices` | Built-in voice directory |
| `--uploads-dir` | `backend/uploads` | User-uploaded voice directory |
| `--cache-dir` | `backend/cache` | Per-segment + join cache directory |
| `--max-text-chars` | `5000` | Hard cap on input text length |
| `--log-level` | `info` | `debug`, `info`, `warning`, `error` |

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
| `GET` | `/config` | `{model_id, device, dtype, sampling_rate, default_cfg_scale, …}` |
| `GET` | `/voices` | `{voices: [{id, name, source, …}]}` |
| `POST` | `/voices/upload` | multipart `file` + optional `name` / `gender` / `language`. Returns new voice metadata. |
| `POST` | `/voices/{id}/meta` | JSON `{name?, gender?, language?}`. Edits metadata for built-in or upload. |
| `DELETE` | `/voices/{id}` | 204 on success, 403 if `id` is built-in, 404 if missing. |
| `POST` | `/synthesize` | JSON `{text, speakers, cfg_scale?, force_regenerate?}` → `audio/wav` (or `?response_format=base64`). Returns `X-Cache` and `X-Cache-Hash` headers. |
| `POST` | `/download` | JSON `{segments: [{text, voice, cfg_scale?, cache_hash?}], silence_gap_ms}`. Returns joined WAV. Uses join cache. |
| `GET` | `/cache` | List all cache entries (hash, size, sample rate, duration, etc.). |
| `DELETE` | `/cache` | Clear all cache entries. |
| `DELETE` | `/cache/{hash}` | Delete a single cache entry. |
| `WS` | `/stream` | Stub — returns `{"streaming": "planned"}`. 1.5B is offline long-form; streaming is out of scope for v1. |

## Project layout

```
vibe-podcast/
├── backend/
│   ├── app.py                    # FastAPI app factory + lifespan + exception handlers
│   ├── cli.py                    # `python -m backend.cli --device cuda --port 8880`
│   ├── requirements.txt
│   ├── core/
│   │   ├── config.py             # pydantic-settings (env + .env + CLI)
│   │   ├── device.py             # resolve_device() → (torch.device, dtype, attn_impl)
│   │   ├── exceptions.py         # Domain errors → HTTP status codes
│   │   └── model.py              # ModelManager singleton (load/unload)
│   ├── services/
│   │   ├── voices.py             # VoiceRegistry: built-in scans + uploads + metadata
│   │   ├── synthesize.py         # SynthService: processor → model.generate → WAV bytes
│   │   ├── synth_cache.py        # Per-segment disk cache
│   │   └── join_cache.py         # Per-download disk cache
│   ├── api/
│   │   ├── health.py             # /api/health, /api/config
│   │   ├── voices.py             # /api/voices (GET, POST upload, POST meta, DELETE)
│   │   ├── synthesize.py         # /api/synthesize
│   │   ├── download.py           # /api/download (multi-segment join)
│   │   ├── cache.py              # /api/cache (list / clear)
│   │   ├── schemas.py            # All Pydantic models
│   │   └── deps.py               # FastAPI dependencies
│   ├── voices/                   # built-in voices (gitignored; .mp3 / .wav / .flac / .ogg)
│   │   └── voices.json           # metadata overrides
│   ├── uploads/                  # user-uploaded voices (gitignored)
│   │   └── voices.json           # metadata for uploads
│   ├── cache/                    # per-segment + joined download cache (gitignored)
│   └── tests/
│       └── test_smoke.py         # 9 endpoint smoke tests (no model required)
└── frontend/
    ├── vite.config.ts            # /api proxy → :8880
    ├── tailwind.config.js
    ├── package.json
    └── src/
        ├── App.tsx               # Layout: Sidebar + ActionBar + segments + PlayerFooter
        ├── main.tsx
        ├── components/
        │   ├── Sidebar.tsx
        │   ├── SegmentCard.tsx
        │   ├── ActionBar.tsx
        │   ├── SampleMenu.tsx
        │   ├── CachePanel.tsx
        │   ├── PlayerFooter.tsx
        │   ├── UploadVoiceDialog.tsx
        │   ├── VoiceMetaDialog.tsx
        │   └── ThemeToggle.tsx
        ├── hooks/
        │   ├── useConfig.ts
        │   └── useVoices.ts
        ├── lib/
        │   ├── api.ts            # Typed wrappers for /api/*
        │   ├── audio.ts          # WAV decoding
        │   ├── store.ts          # useReducer for segments / speakers / cache
        │   └── samples.ts        # Built-in sample scripts
        └── types/
            └── models.ts
```

## Notes & gotchas

- **VibeVoice-1.5B supports up to 4 speakers** with voice cloning from short reference clips. Voice identity comes from a 1–60s clip you assign to each speaker in the sidebar.
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

MIT for the code in this repo. The VibeVoice model weights are released under MIT by Microsoft. See <https://huggingface.co/microsoft/VibeVoice-1.5B> for the model's own usage policy — it embeds an audible AI disclaimer in every generated clip and is intended for research use.
odel's own usage policy — it embeds an audible AI disclaimer in every generated clip and is intended for research use.

```bash
cd frontend
npm run typecheck
npm run build
```

## License

MIT for the code in this repo. The VibeVoice model weights are released under MIT by Microsoft. See <https://huggingface.co/microsoft/VibeVoice-1.5B> for the model's own usage policy — it embeds an audible AI disclaimer in every generated clip and is intended for research use.
odel's own usage policy — it embeds an audible AI disclaimer in every generated clip and is intended for research use.
