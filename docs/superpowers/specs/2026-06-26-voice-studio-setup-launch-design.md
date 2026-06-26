# Voice Studio by MSR — Simplified Setup & Launch

**Date:** 2026-06-26
**Status:** Approved (design)

## Problem

Installing and running the app today is a manual, multi-step, error-prone process:

- Backend: `cd backend`, create venv, activate, install a CUDA-matched PyTorch wheel
  *before* the rest, then `pip install -r requirements.txt`.
- Frontend: `cd frontend`, `npm install`.
- Run: two terminals — `python -m backend.cli` and `npm run dev`.
- Models (VibeVoice ~5.4 GB, Kokoro ~350 MB, Chatterbox ~500 MB) download **lazily**
  on first engine use; there is no way to choose ahead of time, and the first
  synthesis stalls for minutes on a multi-GB download.

The #1 footgun is installing a CPU-only PyTorch wheel, which makes CUDA silently
fall back to CPU.

## Goals

1. Reduce install + run to two commands.
2. A single startup command launches both frontend and backend.
3. Smart, opt-in model downloads — the user picks which models to fetch up front.
4. Cross-platform (Windows / Linux / macOS), Python-based.

## Non-Goals (YAGNI)

- OS double-click wrappers (`.bat` / `.sh` / `.command`).
- In-app (web UI) model-download button — lazy-on-first-use already covers ad-hoc.
- Auto-installing OS-level packages (espeak-ng, ffmpeg).
- Packaging into a pip-installable distribution.

## Solution Overview

A single **stdlib-only** dispatcher at the repo root, `studio.py`, with three
subcommands:

```
python studio.py setup            # one-time: venv, deps, system-dep checks, model picker
python studio.py start            # run app (mode auto-selected)
python studio.py start --dev      # force dev: two processes, hot reload
python studio.py start --prod     # force prod: one server, one port
python studio.py models           # re-open the model picker anytime
```

`studio.py` imports only the Python standard library so it runs on a bare system
Python before any venv exists. It bootstraps `backend/venv`, then delegates heavy
work (model download, running the server) to the venv's Python interpreter.

The two concerns stay cleanly separated:
- **setup** = install + provision (run once, re-runnable).
- **start** = run the app (run every time).

## Components

### 1. `studio.py` (repo root, stdlib only)

Argparse dispatcher. Responsibilities:

- Resolve repo paths (repo root, `backend/`, `frontend/`, `backend/venv`).
- Locate the venv's Python (`backend/venv/Scripts/python.exe` on Windows,
  `backend/venv/bin/python` on POSIX).
- `setup` and `models` orchestration (below).
- `start` orchestration (below).
- CUDA detection + torch-index mapping lives in a stdlib-only helper module
  (`tools/envdetect.py`) so it is importable by `studio.py` (which has no venv
  deps) and unit-testable.

Constraint: **no third-party imports in `studio.py` or `tools/envdetect.py`** —
they must run before the venv is built.

### 2. `tools/envdetect.py` (repo root, stdlib only)

Pure helpers (no side effects beyond running `nvidia-smi`):

- `detect_cuda_tag() -> str | None` — run `nvidia-smi`, parse the reported CUDA
  version, map to a wheel tag (`cu124` / `cu121` / `cu118`). Returns `None` when
  no NVIDIA GPU is present.
- `torch_index_url(tag: str | None, platform: str) -> str | None` — map a CUDA
  tag (or `None`/`mps`) to the PyTorch wheel `--index-url`, or `None` for the
  default CPU/MPS wheel.
- `parse_nvidia_smi_cuda_version(text: str) -> str | None` — pure string parse,
  separated out for unit testing.

### 3. `backend/scripts/download_models.py` (runs inside venv)

Holds the model catalog and download logic. Standalone-runnable:

```
python -m backend.scripts.download_models --models kokoro,chatterbox
```

- `MODEL_CATALOG`: ordered mapping of engine key → `{repo_id, human_size, label}`.
  - `vibevoice` → `vibevoice/VibeVoice-1.5B`, ~5.4 GB
  - `kokoro`    → `hexgrad/Kokoro-82M`, ~350 MB
  - `chatterbox`→ `ResembleAI/chatterbox`, ~500 MB
  - (repo ids sourced from `backend/config.py` defaults where applicable.)
- Sets the project-local HF cache via the existing
  `backend.core.hf_paths.configure_hf_cache(models_dir)` before importing
  `huggingface_hub`, then `snapshot_download(repo_id)` per selected engine.
- Skips models already fully present in `backend/models/`.
- Prints per-model progress and a final summary.

The setup picker and `studio.py models` both shell into this module via the
venv Python, passing the selected engine keys.

### 4. `app.py` static-mount change (enables `--prod`)

Add an **optional** static mount. After the API routers are registered:

- If `frontend/dist/index.html` exists, mount `frontend/dist` at `/` using
  `StaticFiles(html=True)` with an SPA fallback that returns `index.html` for
  unknown non-`/api` paths.
- Registered *after* all `/api/*` routers so the API is never shadowed.
- When `dist` is absent (dev mode), behavior is identical to today.

This makes `--prod` a true single-process, single-port deployment (8880), with
no Node needed at runtime.

## Flows

### `setup`

1. Verify Python ≥ 3.10 (abort with a clear message otherwise).
2. Create `backend/venv` if missing (`python -m venv`).
3. **PyTorch / CUDA (auto-detect + confirm):** `detect_cuda_tag()` →
   `torch_index_url()`; print the choice (e.g. "Detected CUDA 12.4 → installing
   torch cu124"). Allow the user to override (CUDA 12.1 / 11.8 / CPU / MPS).
   Install `torch torchaudio` from the chosen index into the venv.
4. `pip install -r backend/requirements.txt` into the venv.
5. **System deps (detect + guide):** check PATH for `espeak-ng` and `ffmpeg`;
   if missing, print the exact per-OS install command (winget / brew / apt) and
   continue (non-fatal — only Kokoro needs espeak-ng).
6. Check `node`/`npm`. If present, run `npm install` in `frontend/`. If missing,
   print the install guidance and continue (frontend can be set up later).
7. **Model picker:** interactive checklist (VibeVoice / Kokoro / Chatterbox) with
   sizes. Selected engines are pre-downloaded via `download_models.py`. Already-
   present models are skipped.

Idempotent: re-running `setup` adds a model, repairs deps, or re-confirms torch.

### `start [--dev | --prod] [passthrough flags]`

- If `backend/venv` is missing → offer to run `setup` first, then exit.
- Default mode selection (when neither `--dev` nor `--prod` is passed): use **dev**
  if `npm` is available on PATH; otherwise, if `frontend/dist` exists, use **prod**
  (so the app still runs without Node); otherwise error with guidance to install
  Node or run `setup`. An explicit `--dev`/`--prod` flag always wins.
- **`--dev`:** spawn two subprocesses —
  - backend: `<venv python> -m backend.cli <passthrough: --device/--port/...>`
  - frontend: `npm run dev` in `frontend/`
  Merge stdout/stderr with `[backend]` / `[frontend]` prefixes. A single Ctrl+C
  terminates both cleanly: Windows uses `CREATE_NEW_PROCESS_GROUP` +
  `CTRL_BREAK_EVENT`; POSIX uses `start_new_session` + `killpg`.
- **`--prod`:** if `frontend/dist` is missing, run `npm run build` in `frontend/`
  (requires Node at build time). Then start only
  `<venv python> -m backend.cli` (which now serves the static UI + API on 8880).

Passthrough flags (`--device`, `--port`, `--engine`, etc.) are forwarded to
`backend.cli` unchanged.

## Error Handling

- Each setup step prints a clear status line and, on failure, an actionable
  message (what failed + the manual command to recover).
- Missing Python/Node/system deps produce guidance, not stack traces.
- `start` with a missing venv guides the user to `setup` instead of crashing.
- Subprocess crashes in `--dev`: if either child exits non-zero, print which one
  and tear down the other so the user isn't left with a half-running stack.

## Testing

Pure, deterministic units (unit tests under `backend/tests/`):

- `parse_nvidia_smi_cuda_version()` — sample `nvidia-smi` outputs → version/None.
- `torch_index_url()` — every tag (`cu124`/`cu121`/`cu118`/`None`/`mps`) → expected
  index URL or `None`.
- Model-selection parsing in `download_models.py` — `"kokoro,chatterbox"` → the
  right catalog subset; unknown key → clear error.
- `app.py` static mount guard — with `dist` present a `/` route is served and
  `/api/health` still resolves; with `dist` absent, only `/api/*` exists.

Interactive prompts and live subprocess orchestration are kept thin and verified
manually (documented run-through in the plan).

## Docs & Branding

- Rebrand user-facing strings to **Voice Studio by MSR** (short **Voice Studio**):
  setup/start banners, `backend.cli` `prog`/description, README headings.
  Internal package names (`backend`, frontend package) are left unchanged.
- Update `README.md` install/run sections to the two-command flow.
- Update `CLAUDE.md` Commands section to the new entry points (keeping the raw
  `python -m backend.cli` / `npm run dev` as the underlying primitives).

## File Summary

| Path | Change |
|------|--------|
| `studio.py` | New — stdlib dispatcher (setup / start / models) |
| `tools/envdetect.py` | New — stdlib CUDA detection + torch-index mapping |
| `backend/scripts/download_models.py` | New — model catalog + snapshot download |
| `backend/app.py` | Modified — optional static mount for `--prod` |
| `backend/cli.py` | Modified — rebrand `prog`/description strings |
| `backend/tests/test_setup_helpers.py` | New — unit tests for pure helpers |
| `README.md`, `CLAUDE.md` | Modified — new flow + branding |
