# Model Download Progress — Design

**Date:** 2026-06-27
**Status:** Approved (pending spec review)

## Problem

When a user switches to an engine whose model weights aren't on disk yet, the
backend downloads them lazily inside `engine.load()` (`snapshot_download`). The
UI only shows a "Loading…" spinner, so for VibeVoice (~5.4 GB) the app looks
frozen for many minutes with no indication of what's happening. The user is
blind to a large, slow operation.

## Goal

When the user selects an engine whose weights are missing, show a visual
download experience: a confirmation of the download size, then a progress bar
with percentage, download speed, ETA, and a live log — instead of a silent
spinner.

## Scope

- **In scope:** VibeVoice and Kokoro (the two in-process engines).
- **Out of scope:** Chatterbox. It keeps its existing isolated-venv install flow
  (`ChatterboxInstaller` + `InstallChatterboxDialog`) and its lazy weight
  download inside the out-of-process worker. Its `downloaded` flag stays `true`
  so none of this new UI engages for it.
- **Out of scope:** changing setup-time downloads (`download_models.py`,
  `studio.py models`). Those are unaffected.

## Approach

**In-process background download with a `tqdm` callback.** Run
`snapshot_download` on a daemon thread inside the FastAPI process, passing a
custom `tqdm_class` that folds byte deltas into a shared progress snapshot. The
total size is pre-computed via `HfApi().model_info(repo_id,
files_metadata=True)` so the percentage is accurate; speed and ETA are derived
from bytes-over-wall-clock. The frontend polls a status endpoint.

This mirrors the proven `ChatterboxInstaller` shape (state machine + background
work + polling endpoint + modal), but downloads in-process rather than via a
subprocess so we get exact byte counts instead of scraping HF's per-file tqdm
text (which is brittle with parallel `hf_transfer` downloads).

The download thread is independent of the synth `ThreadPoolExecutor`/lock, so it
never blocks or is blocked by synthesis.

## Components

### 1. `ModelDownloader` service — `backend/services/model_download.py`

A small state machine, one instance on `app.state`, tracking at most one active
download at a time (downloads are large; serialize them).

**State:** `idle → downloading → done | error`.

**Progress snapshot** (returned by `status()`):

```
{
  "engine": str | None,        # engine key currently/last downloading
  "state": str,                # idle | downloading | done | error
  "percent": float | None,     # 0..100, None if total unknown
  "downloaded_bytes": int,
  "total_bytes": int | None,
  "speed_bps": float | None,   # rolling bytes/sec
  "eta_sec": float | None,     # None if speed or total unknown
  "current_file": str | None,
  "log": list[str],            # short tail of human-readable lines
  "error": str | None,
  "returncode": int | None,    # 0 success, non-zero/None on failure
}
```

**Methods:**

- `start(engine_key)` — validates `engine_key` is downloadable
  (`vibevoice`/`kokoro`); if a download is already running, coalesces (returns
  current status without starting a second). Otherwise resets the snapshot,
  resolves `repo_id` from `MODEL_CATALOG`, sets `state="downloading"`, and spawns
  a daemon thread running the download. Returns the initial status.
- `status()` — returns the current snapshot (recomputing `speed_bps`/`eta_sec`
  from the rolling sample so the values stay live between tqdm updates).
- Injectable `runner` (default `_default_runner`) so tests drive a fake
  download. `_default_runner(repo_id, on_total, on_bytes, on_file, log)`:
  computes total via `model_info`, calls `on_total(total)`, then runs
  `snapshot_download(repo_id, tqdm_class=_ProgressTqdm(...))`.

**`_ProgressTqdm`** — a `tqdm` subclass whose `update(n)` adds `n` to the shared
downloaded-bytes counter, but only for byte-unit bars (`self.unit == "B"`), so
the "Fetching N files" item-bar is ignored. It also reports `current_file` from
the bar's description. Aggregation across the (possibly parallel) per-file bars
is just summation of deltas, which is order- and concurrency-independent.

**Speed/ETA math:** keep `(timestamp, downloaded_bytes)` samples in a short
deque; `speed_bps` = delta-bytes / delta-time over the window; `eta_sec` =
`(total - downloaded) / speed_bps` when both known. `status()` computes these on
read so they don't depend on tqdm update cadence. (Wall-clock uses
`time.monotonic()`; this is backend Python, not a workflow script.)

On exception, capture the message into `error`, set `state="error"`,
`returncode != 0`. On success, set `state="done"`, `percent=100`,
`returncode=0`.

### 2. Download detection — `downloaded` flag

- Helper `model_downloaded(repo_id, cache_dir) -> bool` in a new small module
  `backend/core/model_cache.py` (kept out of the import-order-sensitive
  `hf_paths.py`): returns whether the repo's weights are present in the local HF
  cache. Implementation: resolve the
  repo snapshot via `huggingface_hub` (e.g. `snapshot_download(repo_id,
  local_files_only=True)` succeeds, or `try_to_load_from_cache` finds the
  weights file). It must distinguish "fully present" from "absent/partial" well
  enough that a fresh machine reports `False` and a downloaded one reports
  `True`.
- `Engine.downloaded() -> bool` on the ABC, default `True`. VibeVoice and Kokoro
  override it to call `model_downloaded(self._model_id, cache_dir)`. Chatterbox
  inherits the default `True`.
- `Engine.info()` gains `"downloaded": self.downloaded()`.

### 3. API — `backend/api/engines.py`

Mirror the existing `/install` pair:

- `GET /api/engines/{name}/download` → `DownloadStatusModel` (the snapshot).
- `POST /api/engines/{name}/download` → starts/coalesces; returns the snapshot.
- Both return `400` unless `name in {"vibevoice", "kokoro"}`.
- `EngineInfoModel` gains `downloaded: bool`.
- New `DownloadStatusModel` Pydantic schema matching the snapshot.
- Dependency `get_model_downloader` in `api/deps.py`; instance created on
  `app.state.model_downloader` in `app.py`.

### 4. Frontend — `DownloadModelDialog`

New component `frontend/src/components/DownloadModelDialog.tsx`, opened from
`EngineSelector` when `e.downloaded === false` (a new branch beside the existing
`e.installed === false` install branch).

- **Step 1 — confirm:** "VibeVoice needs ~5.4 GB. Download now?" with
  Download / Cancel. The size string comes from a small frontend constant keyed
  by engine name (e.g. `{ vibevoice: "~5.4 GB", kokoro: "~350 MB" }`), mirroring
  the catalog sizes in `download_models.py`. No new backend field is needed.
- **Step 2 — progress:** a real progress bar bound to `percent`, with
  `downloaded / total` (GB), `speed_bps` (MB/s), and `eta_sec` (mm:ss), plus a
  live log tail styled like the existing install modal. Polls
  `getModelDownloadStatus(name)` every ~1 s.
- **On `done`:** proceed to switch + load the engine (same flow the normal
  "Switch" button uses), then close.
- **On `error`:** show the error and a Retry button.

`EngineSelector` selection logic: if `downloaded === false`, open the download
dialog instead of calling `onLoad`; the existing `installed === false` branch is
unchanged and takes precedence for Chatterbox.

### 5. Types / api client

- `EngineInfo.downloaded: boolean` in `frontend/src/types/models.ts`.
- `DownloadStatus` type matching the snapshot.
- `getModelDownloadStatus(name)` / `startModelDownload(name)` in
  `frontend/src/lib/api.ts`.

## Data flow

1. UI lists engines; VibeVoice shows `downloaded: false` → its button reads
   "Download VibeVoice" instead of "Switch to…".
2. User clicks it → `DownloadModelDialog` opens at the confirm step.
3. Confirm → `POST /api/engines/vibevoice/download` → `ModelDownloader.start`
   spawns the thread; dialog moves to the progress step and begins polling
   `GET …/download`.
4. The tqdm callback folds byte deltas into the snapshot; each poll returns live
   `percent/speed/eta/current_file/log`.
5. On `done`, the dialog switches to the engine (activate + load) and closes;
   `downloaded` is now `true`, so the normal "Switch to…" button appears
   thereafter.

## Error handling

- Network failure / partial download → `state="error"`, message surfaced in the
  dialog log with a Retry button (re-`POST`).
- A second `POST` while downloading coalesces onto the running job (no duplicate
  threads), matching the installer's behavior.
- `model_info` failure (can't get total) → download still proceeds with
  `total_bytes=None`; the UI shows an indeterminate bar + downloaded bytes +
  speed (no % / ETA) rather than failing.
- Backend restart mid-download loses the in-memory state; the engine simply
  reports `downloaded: false` again and the user can restart the download
  (HF cache resumes partial files).

## Testing

- `ModelDownloader`: state transitions (`idle→downloading→done`,
  `…→error`), coalescing of a second `start`, and the progress math (feed a fake
  runner that emits `on_total` then a sequence of `on_bytes` deltas; assert
  `percent`, `speed_bps`, `eta_sec`, `downloaded_bytes`). Injected runner — no
  network, no real weights.
- `_ProgressTqdm` byte-only filtering (item-unit bar ignored).
- `model_downloaded` detection: returns `False` for an absent repo, `True` for a
  present one (use a temp cache dir; can stub `try_to_load_from_cache`).
- API: `GET`/`POST …/download` return the snapshot for vibevoice/kokoro and
  `400` for chatterbox/unknown.
- Engine `info()` includes `downloaded`.
- Frontend: `npm run typecheck` passes with the new types/props.

## Out of scope / non-goals

- No streaming of Chatterbox weight download (kept as-is).
- No parallel/multiple simultaneous downloads (one at a time by design).
- No change to setup-time `download_models.py` behavior.
- No pause/resume UI (HF resumes partial files automatically on retry; that's
  enough).
