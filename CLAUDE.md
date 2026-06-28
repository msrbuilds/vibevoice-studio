# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What this is

Voice Studio by MSR — a fully-offline, local web UI for **multiple open-source TTS engines** (VibeVoice-1.5B, Kokoro-82M, Chatterbox Multilingual V3, OmniVoice). FastAPI backend serves the models; React + Vite frontend is a multi-segment podcast editor. Only one engine is loaded at a time to keep memory low.

## Commands

Primary entry point (cross-platform, from repo root):
```bash
python studio.py setup            # one-time: venv, deps, PyTorch/CUDA auto-detect, system-dep checks, model picker
python studio.py start            # run backend + frontend together (auto dev/prod)
python studio.py start --dev      # force dev (uvicorn :8880 + Vite :5173, hot reload)
python studio.py start --prod     # force prod (single server :8880 serving UI + API)
python studio.py models           # re-open the interactive model picker
```
`studio.py` is stdlib-only and bootstraps `backend/venv`; it forwards `start` flags (`--device`, `--port`, …) to `backend.cli`. The raw commands below are the underlying primitives.

Backend (run from repo root; package is `backend`):
```bash
python -m backend.cli --engine vibevoice --device cuda   # start server :8880; --device cpu|mps|auto
python -m backend.cli --help                             # all flags (--engine, --model, --kokoro-lang, --chatterbox-lang, --models-dir, --port)
cd backend && python -m pytest tests/                    # smoke tests (stubbed model, no weights needed, ~seconds)
cd backend && python -m pytest tests/test_smoke.py::<name>   # single test
```

Frontend (from `frontend/`):
```bash
npm run dev        # Vite :5173, proxies /api/* → :8880 (no CORS setup needed)
npm run typecheck  # tsc -b --noEmit
npm run build      # tsc -b && vite build
```

Two terminals: one backend, one frontend. First backend boot downloads model weights to `backend/models/` (VibeVoice ~5.4 GB). On Windows, install a CUDA PyTorch wheel *before* `pip install -r backend/requirements.txt` or CUDA silently falls back to CPU.

## Architecture

The backend is organized around a pluggable **engine abstraction**. Understanding it requires reading across `core/engines/`, `core/engine_manager.py`, and `services/synthesize.py`:

- **`core/engines/__init__.py`** — the `Engine` ABC. Each engine (`vibevoice_engine.py`, `kokoro_engine.py`, `chatterbox_engine.py`) is a self-contained model+processor implementing `load/unload/is_loaded/synthesize/...`. Engines are constructed at startup but loaded **lazily** on first use. `EngineSynthRequest`/`EngineResult` are the engine-agnostic I/O dataclasses; engines ignore fields they don't understand (e.g. Kokoro ignores `reference_audio`; only Chatterbox uses `cfg_weight`/`exaggeration`/`language_id`).
- **`core/engine_manager.py`** — `EngineManager` owns the engine registry and tracks the single active engine. Switching engines unloads the previous one. The active choice is persisted to `backend/.last_engine` and restored on restart. **Register new engines here** (the dict order drives the UI selector).
- **Some engines run out-of-process in isolated venvs.** Two engines can't share the main venv because of hard dependency pins: `chatterbox-tts` pins `transformers==5.2.0` and **OmniVoice** pins `transformers>=5.3.0` + `torch 2.8`, both incompatible with VibeVoice's `transformers==4.51.3` (and with each other). So `core/engines/chatterbox_engine.py` and `core/engines/omnivoice_engine.py` are **proxies**: each keeps the normal `Engine` interface but drives a worker (`backend/chatterbox_worker.py` / `backend/omnivoice_worker.py`) running in its own venv (`backend/venv-chatterbox` / `backend/venv-omnivoice`, built on demand by `studio.py`). They talk newline-delimited JSON over stdin/stdout (stderr drained on a thread to avoid pipe deadlock; the worker fd-redirects its own stdout so model-load noise can't corrupt the protocol); audio passes as temp WAV paths. Each engine's deps live in `requirements-chatterbox.txt` / `requirements-omnivoice.txt`, never the main `requirements.txt`; `studio.py` installs the package first, then force-reinstalls a CUDA-matched torch wheel (Chatterbox: cu124/cu118 for torch 2.6; OmniVoice: cu128/cu126 for torch 2.8, via `envdetect.detect_omnivoice_cuda_tag`). A `.{engine}-ready` marker (written last) gates `installed()` so an interrupted install never looks complete. The **install flow is generic over installable engines**: `app.state.engine_installers` is a registry of `EngineEnvInstaller(subcommand)` (`backend/services/chatterbox_install.py`; `ChatterboxInstaller` is a thin alias), `POST/GET /api/engines/{name}/install` runs `studio.py install-{name}` and streams the live log, and the frontend `InstallEngineDialog` (parametrized by engine) drives it. Each engine's `info()` carries an `installed` flag (isolated engines = their venv marker exists). OmniVoice supports **all three voice modes** — clone (reference clip), design (a free-text `instruct` attribute prompt), and auto (no prompt) — via a per-speaker Clone/Design/Auto toggle in the sidebar (shown only when OmniVoice is active). The mode + optional `instruct` ride **per-speaker** through the synth request (`SynthSpeaker.voice_mode`/`instruct` → `EngineSynthRequest` → the proxy's mode-dispatching `_build_synth_msg`); design/auto carry no reference voice, so `SynthService` skips voice resolution for them and folds mode/`instruct` into the per-segment + join cache keys so modes/prompts never collide. The per-speaker mode is **derived** in the UI (`omnivoiceMode ?? (voice ? "clone" : "auto")`, see `frontend/src/lib/omnivoice.ts`).
- **Model weights download with progress (in-process engines).** Each engine's `info()` also carries a `downloaded` flag — `True` by default, but VibeVoice/Kokoro override `Engine.downloaded()` to probe the local HF cache via `core/model_cache.py::model_downloaded` (a network-free `snapshot_download(local_files_only=True)`). When the UI sees `downloaded:false` it offers a **Download** button instead of **Switch**: `POST /api/engines/{name}/download` drives `backend/services/model_download.py::ModelDownloader` (single-flight daemon thread running `snapshot_download` with a custom `tqdm` subclass that aggregates byte deltas; total size pre-fetched via `HfApi().model_info`), and the `DownloadModelDialog` polls `GET /api/engines/{name}/download` for a live `{percent, speed_bps, eta_sec, log, …}` snapshot. `vibevoice`/`kokoro`/`omnivoice` are downloadable here (the endpoints 400 otherwise). OmniVoice runs in an isolated worker but its weights live in the same shared HF cache, so the main-process downloader pre-fetches the `k2-fsa/OmniVoice` repo with a progress bar (the ~11 MB Qwen tokenizer slice still streams on first worker load). Chatterbox keeps its separate venv-install flow and lazy in-worker weight download.
- **`services/synthesize.py`** — `SynthService` is everything engine-*agnostic*: input validation, normalizing free text into canonical `Speaker N:` scripts, per-segment disk cache lookup/write, and **thread serialization** (a single `threading.Lock` + single-worker `ThreadPoolExecutor` so concurrent requests don't fight over the GPU). Multi-speaker scripts are split per-line and synthesized as separate calls, then PCM-concatenated with silence gaps. Cache keys fold engine name + cfg/exaggeration/language knobs in, so cross-engine or cross-knob results never collide. The `ModelDownloader` thread is independent of this lock/executor, so weight downloads never block synthesis.
- **`app.py`** — FastAPI factory. Wires the singletons (`VoiceRegistry`, `SynthCache`, `JoinCache`, `EngineManager`, `SynthService`) onto `app.state`, merges each engine's built-in voices into the registry, eager-loads the active engine in `lifespan`, and maps `BackendError` → HTTP status. **Critical ordering quirk:** `app.py` and `cli.py` configure the HuggingFace cache dir (`core/hf_paths.py`) *before* importing anything that pulls in transformers/kokoro/huggingface_hub. Keep heavy imports below that call.
- **`api/`** — thin routers (`health`, `engines`, `voices`, `synthesize`, `download`, `cache`, `stream`). All Pydantic models live in `api/schemas.py`; FastAPI dependencies in `api/deps.py`. `/stream` (WebSocket) is mostly a stub — streaming only exists for engines whose `supports_streaming()` is True.
- **`config.py`** — `pydantic-settings`, sourced from env + `backend/.env` + CLI overrides (CLI flags in `cli.py` map to `Settings` field overrides). Holds per-engine defaults.

- **`studio.py` + `tools/envdetect.py` (repo root)** — the cross-platform launcher. `studio.py` is **stdlib-only** (runs before the venv exists) and orchestrates setup/start/models; `tools/envdetect.py` does CUDA detection → PyTorch wheel-index mapping. Model pre-download lives in `backend/scripts/download_models.py` (catalog + `snapshot_download`). Prod mode is enabled by `_mount_frontend()` in `app.py`, which serves `frontend/dist` at `/` when present. Pure helpers for all of this are unit-tested in `backend/tests/test_setup_helpers.py`.

Frontend: `frontend/src/App.tsx` is the orchestrator (segments, speakers, playback, export). State lives in `lib/store.ts` (`useReducer`). `lib/api.ts` has typed `/api/*` wrappers; engine/voice/config state come from the `hooks/` (`useEngine`, `useVoices`, `useConfig`). The CFG slider is engine-aware — it maps to VibeVoice's `cfg_scale` or Chatterbox's `cfg_weight` depending on the active engine (`lib/engineHints.ts`).

## Gotchas

- The README is detailed but predates the multi-engine refactor — its "Project layout" lists `core/config.py`/`core/model.py` paths that have moved. Trust the actual tree (`config.py` at `backend/` root, engines under `core/engines/`).
- `backend/voices/`, `backend/uploads/`, `backend/cache/`, and `backend/models/` are gitignored runtime dirs. Built-in voices are scanned at startup — adding a file to `backend/voices/` requires a restart.
- Concurrent synthesize requests serialize by design. Don't add parallelism inside `SynthService` without a queue upstream.
