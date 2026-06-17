# VibeVoice Studio

A local web UI for **Microsoft's VibeVoice-1.5B** text-to-speech model. Multi-segment podcast-style editor, voice uploads, GPU/CPU/MPS backend, fully offline.

```
┌─────────────────────────┐         ┌──────────────────────────┐
│  React + Vite + Tailwind │  HTTP   │   FastAPI (Python 3.10+) │
│  localhost:5173          │ ──────▶ │   localhost:8880         │
│  - Sidebar: speakers     │         │  - transformers >= 4.51 │
│  - Segments list         │         │  - VibeVoice-1.5B        │
│  - Generate / Play / WAV │         │  - voices/ + uploads/    │
└─────────────────────────┘         └──────────────────────────┘
```

## What's in here

- **`backend/`** — FastAPI server. Loads VibeVoice-1.5B from HuggingFace, exposes `/api/{health,config,voices,synthesize}`, serializes requests with a single `threading.Lock`.
- **`frontend/`** — React + Vite + Tailwind. Sidebar of speakers, scrollable segment list, dark/light theme, client-side audio cache, WAV export.
- **`backend/voices/`** — drop in your own `.wav` reference clips; they're picked up automatically on next boot.
- **`backend/uploads/`** — user-uploaded voices (managed from the UI's sidebar).

## Prerequisites

- **Python 3.10+**
- **Node.js 18+** (Node 20 tested)
- **PyTorch** with CUDA support (Windows/Linux), or CPU-only (slower)
- **~6 GB disk** for the model weights (auto-downloaded on first run)
- **~3 GB VRAM** for fp16 inference; **~2 GB** for CPU

## Quick start

### 1. Backend

```bash
cd backend

# Create venv (skip if you have one)
python -m venv venv
# Windows:
.\venv\Scripts\activate
# Linux / macOS:
source venv/bin/activate

# Install deps. On Windows, use a CUDA-matched PyTorch wheel:
#   pip install torch torchaudio --index-url https://download.pytorch.org/whl/cu121
pip install -r requirements.txt

# Start the server (auto-detects CUDA → MPS → CPU)
python cli.py
# Or pin a device:
#   python cli.py --device cpu
#   python cli.py --device cuda --port 8880
```

The first boot downloads the 5.4 GB `microsoft/VibeVoice-1.5B` weights from HuggingFace. Subsequent boots use the cache.

You should see:
```
[startup] Loading processor from microsoft/VibeVoice-1.5B …
[startup] Loading model weights (device=cuda, dtype=bfloat16, attn=sdpa) …
[startup] Model ready. sampling_rate=24000 Hz, attn=sdpa
INFO:     Uvicorn running on http://0.0.0.0:8880
```

### 2. Frontend

```bash
cd frontend
npm install
npm run dev
```

Open <http://localhost:5173>. The Vite dev server proxies `/api/*` to the backend, so no CORS configuration is needed.

### 3. Add a voice

On first run, the sidebar will show **0 built-in voices** until you add some. Two ways:

- **Drop a `.wav` into `backend/voices/`** (e.g. `en-Emma_woman.wav`) and restart the backend. See `backend/voices/README.md` for the naming convention and where to source the canonical 4 voices.
- **Upload from the UI**: click the `+` next to **My voices** in the sidebar. Pick a 1–60s mono WAV/FLAC/OGG/MP3. The voice is saved to `backend/uploads/`.

Then in the sidebar, pick a voice for your default "Host" speaker. Type text into a segment, hit **Generate**, audio plays back.

### 4. Make a multi-segment podcast

1. Click **Add Segment** for each new line.
2. Switch the speaker dropdown on each segment to assign a different voice.
3. Click **Generate All** to fill the audio cache.
4. Click **Play Podcast** to play through.
5. Click **Download Audio** to export a single concatenated WAV.

## Project layout

```
vibe-podcast/
├── backend/
│   ├── app.py              # FastAPI app factory + lifespan + exception handlers
│   ├── cli.py              # `python cli.py --device cuda --port 8880`
│   ├── config.py           # pydantic-settings (env + .env + CLI)
│   ├── core/
│   │   ├── device.py       # resolve_device() → (torch.device, dtype, attn_impl)
│   │   ├── exceptions.py   # Domain errors → HTTP status codes
│   │   └── model.py        # ModelManager singleton (load/unload)
│   ├── services/
│   │   ├── voices.py       # VoiceRegistry: built-in scans + uploads
│   │   └── synthesize.py   # SynthService: processor → model.generate → WAV bytes
│   ├── api/
│   │   ├── health.py       # /api/health, /api/config
│   │   ├── voices.py       # /api/voices (GET, POST upload, DELETE)
│   │   ├── synthesize.py   # /api/synthesize
│   │   ├── schemas.py      # All Pydantic models
│   │   └── deps.py         # FastAPI dependencies
│   ├── voices/             # built-in voices (gitignored)
│   ├── uploads/            # user uploads (gitignored)
│   ├── tests/              # smoke tests
│   └── requirements.txt
└── frontend/
    ├── vite.config.ts      # /api proxy → :8880
    ├── tailwind.config.js
    └── src/
        ├── App.tsx         # Layout: Sidebar + ActionBar + segments + PlayerFooter
        ├── components/     # Sidebar, SegmentCard, ActionBar, PlayerFooter, …
        ├── hooks/          # useConfig, useVoices
        ├── lib/            # api.ts, audio.ts, store.ts (useReducer)
        └── types/          # models.ts
```

## API

| Method | Path | Description |
|---|---|---|
| `GET` | `/api/health` | `{status, model_loaded, device, version}` |
| `GET` | `/api/config` | `{model_id, device, dtype, sampling_rate, default_cfg_scale, …}` |
| `GET` | `/api/voices` | `{voices: [{id, name, source, …}]}` |
| `POST` | `/api/voices/upload` | multipart `file` field. Returns new voice metadata. |
| `DELETE` | `/api/voices/{id}` | 204 on success, 403 if `id` is built-in, 404 if missing. |
| `POST` | `/api/synthesize` | JSON `{text, voice, cfg_scale?}`. Returns `audio/wav` (or `?response_format=base64`). |
| `WS` | `/api/stream` | Stub — returns `{"streaming": "planned"}`. 1.5B is offline long-form; streaming is out of scope for v1. |

CLI flags: `--model PATH` to point at a local copy, `--device {auto,cuda,cpu,mps}`, `--port 8880`, `--voices-dir`, `--uploads-dir`.

## Notes & gotchas

- **VibeVoice-1.5B supports up to 4 speakers** with voice cloning from short reference clips. Voice identity comes from a 1–60s `.wav` you assign to each speaker in the sidebar.
- **Microsoft removed the original repo and code in Sept 2025** for responsible-AI reasons. The `vibevoice` Python package (from the community fork) and the 1.5B weights (from `vibevoice/VibeVoice-1.5B` on HuggingFace) are how you run it now. The model embeds an audible AI disclaimer in every clip and logs a hashed request ID, per Microsoft's policy.
- **First-boot download is ~5.4 GB.** Subsequent boots load from `~/.cache/huggingface/`. Set `HF_HOME` to relocate.
- **Concurrent requests serialize.** The backend uses a single `threading.Lock` so two requests don't fight over the GPU. Set up a queue upstream if you need fan-out.
- **`max_text_chars` is 5000** by default. The model's 64K-token context is much larger, but text > 5K characters risks OOM on smaller GPUs.
- **On Windows, install PyTorch from the official wheel index** before `pip install -r requirements.txt` — otherwise you get a CPU-only torch and CUDA will silently fall back to CPU.
- **CPU mode works** but is slow (RTF ~10–30×). For real use, run on a CUDA GPU. Apple Silicon (MPS) is supported but experimental.

## Troubleshooting

- **`backend not reachable` on the frontend** — make sure `python cli.py` is running on port 8880 and didn't crash at startup. Tail the logs.
- **CUDA available but model runs on CPU** — you probably installed the CPU-only PyTorch wheel. Reinstall from `https://download.pytorch.org/whl/cu121` (or `cu118` / `cu124` matching your driver).
- **`flash_attn seems to be not installed`** — safe to ignore; the backend retries with `sdpa`.
- **`out of memory` during generation** — switch to `--device cpu` or shorten the text. The backend returns 507 with a clear message and empties the CUDA cache.
- **No built-in voices in the sidebar** — drop a `.wav` into `backend/voices/` (e.g. from the `vibevoice-community/VibeVoice` mirror) and restart.

## License

MIT for the code in this repo. The VibeVoice model is released under MIT by Microsoft. See <https://huggingface.co/microsoft/VibeVoice-1.5B> for the model's own usage policy — it embeds an audible AI disclaimer and is intended for research use.
odel's own usage policy — it embeds an audible AI disclaimer and is intended for research use.
eVoice` mirror) and restart.

## License

MIT for the code in this repo. The VibeVoice model is released under MIT by Microsoft. See <https://huggingface.co/microsoft/VibeVoice-1.5B> for the model's own usage policy — it embeds an audible AI disclaimer and is intended for research use.
