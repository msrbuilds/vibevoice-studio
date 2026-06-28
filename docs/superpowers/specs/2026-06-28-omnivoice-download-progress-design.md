# OmniVoice Download Progress — Design

**Date:** 2026-06-28
**Status:** Approved (pending spec review)
**Builds on:** the model-download-progress feature (`2026-06-27-model-download-progress-design.md`) — the in-process `ModelDownloader` + `DownloadModelDialog` that already serve VibeVoice/Kokoro — and the OmniVoice engine (Spec A/B).

## Problem / goal

OmniVoice's ~1.6 GB weights currently download **lazily inside the isolated `venv-omnivoice` worker** on first load, with **no progress UI** — the first generation appears to hang for minutes. We already built an in-process model-download-with-progress system, but it was scoped to the in-process engines (VibeVoice/Kokoro). This change **wires OmniVoice into that existing system** so the user gets a real progress bar (%, speed, ETA) before first use.

## Key insight that makes this small

The weights are plain HuggingFace files in a **shared cache** (`backend/models/`, via `HF_HOME`). The OmniVoice worker *loads* the model, but it *reads* from that shared cache. So the **main backend process can pre-download** `k2-fsa/OmniVoice` with the existing `ModelDownloader` (a background-thread `snapshot_download` with a `tqdm` byte callback), and the worker then finds everything cached. No worker instrumentation, no new protocol — just opt OmniVoice into the system that already exists.

## What OmniVoice actually downloads (verified from the local HF cache)

| Repo | Size | Covered by this design? |
|---|---|---|
| `k2-fsa/OmniVoice` (model.safetensors + `audio_tokenizer/` + tokenizer) | ~1.6 GB | **Yes** — pre-downloaded with progress |
| `Qwen/Qwen2.5-1.5B` (tokenizer/config slice only, *not* the 3 GB weights) | ~11 MB | No — streams silently on first load (negligible) |

`from_pretrained` pulls the main repo plus a tiny tokenizer slice of Qwen2.5-1.5B. The progress bar covers the main repo (essentially all the bytes); the ~11 MB remainder downloads on first load without a bar. This is an explicit, accepted limitation (Approach B — scraping the worker's tqdm to cover the last 11 MB — was rejected as not worth the brittleness).

## Approach

Reuse the in-process `ModelDownloader` + `DownloadModelDialog` unchanged; just register OmniVoice as a downloadable engine. The button flow falls out of the **existing** `EngineSelector` precedence (`installed===false` → Install; else `downloaded===false` → Download; else Switch) with **no UI logic changes**:

1. **venv missing** → "Install OmniVoice" (existing install dialog: venv + torch).
2. **venv present, weights missing** → "Download OmniVoice" (existing progress dialog, ~1.6 GB with %/speed/ETA).
3. **both present** → "Switch to OmniVoice".

## Components (all small; reuse the proven system)

### Backend
1. **`backend/scripts/download_models.py` — `MODEL_CATALOG`**: add an `omnivoice` entry: `{"repo_id": "k2-fsa/OmniVoice", "size": "~1.6 GB", "label": "OmniVoice"}`. The `ModelDownloader` reads `repo_id` from here. (Note: the interactive *setup* picker in `studio.py::_interactive_model_picker` has its own separate hardcoded list and is intentionally **not** touched — OmniVoice weights are fetched via the new in-UI Download dialog after the venv is installed, not at setup time.)
2. **`backend/services/model_download.py` — `DOWNLOADABLE`**: add `"omnivoice"` to the frozenset.
3. **`backend/api/engines.py` — `_DOWNLOADABLE`**: add `"omnivoice"` so `GET/POST /api/engines/omnivoice/download` work (currently 400).
4. **`backend/core/engines/omnivoice_engine.py` — `downloaded()`**: override the base `True` with a real probe, mirroring VibeVoice/Kokoro:
   ```python
   def downloaded(self) -> bool:
       from ..model_cache import model_downloaded
       return model_downloaded(self._model_id)   # self._model_id == "k2-fsa/OmniVoice"
   ```
   This runs network-free (`snapshot_download(local_files_only=True)`) on each `/api/engines` call, so the selector knows whether to show Download or Switch.

### Frontend
5. **`frontend/src/components/DownloadModelDialog.tsx` — `MODEL_SIZES`**: add `omnivoice: "~1.6 GB"` for the confirm-step label. (The live progress bar still uses the runtime total from `HfApi().model_info`, so the label is only the up-front estimate.) No other frontend change — the dialog, polling, and `EngineSelector` Download branch are engine-agnostic already.

## Data flow

1. Engine list: OmniVoice with `installed:true` (venv built) but `downloaded:false` → selector shows **Download OmniVoice**.
2. Click → `DownloadModelDialog` confirm ("~1.6 GB") → `POST /api/engines/omnivoice/download` → `ModelDownloader` runs `snapshot_download("k2-fsa/OmniVoice")` on a daemon thread with live `tqdm` byte aggregation; dialog polls `GET …/download` for `percent/speed/eta/log`.
3. On `done`, the dialog switches + loads OmniVoice; the worker's `from_pretrained` finds `k2-fsa/OmniVoice` fully cached and pulls only the ~11 MB Qwen tokenizer slice (effectively instant), then loads.
4. `downloaded()` now returns `true`, so the button reads "Switch to OmniVoice" thereafter.

## Error handling

- All inherited from the existing `ModelDownloader`/dialog: network failure → `state:error` + Retry; total-size unknown → indeterminate bar; backend restart mid-download → the engine simply reports `downloaded:false` again and the user re-downloads (HF resumes partial files).
- Ordering: if a user somehow reaches Download before Install (they can't via the UI — Install precedence gates it), the worker load would still lazy-download; harmless.
- Other engines unaffected — this only adds `omnivoice` to existing allow-lists.

## Testing

- **Backend:**
  - `MODEL_CATALOG` contains `omnivoice` with `repo_id == "k2-fsa/OmniVoice"`.
  - `omnivoice` is in `model_download.DOWNLOADABLE` and `ModelDownloader.start("omnivoice")` resolves the repo (use the existing injected-runner pattern — no network).
  - `GET`/`POST /api/engines/omnivoice/download` return the snapshot (200), not 400 (mirror the vibevoice/kokoro endpoint tests).
  - `OmniVoiceEngine.downloaded()` calls `model_downloaded(self._model_id)` — monkeypatch `model_downloaded` and assert it's probed with `"k2-fsa/OmniVoice"` and that `info()["downloaded"]` reflects it.
- **Frontend:** `npm run typecheck` + `npm run build`; `MODEL_SIZES.omnivoice` present so the confirm step shows a size.

## Out of scope / non-goals

- Covering the ~11 MB Qwen2.5-1.5B tokenizer slice with a progress bar (streams on first load; negligible).
- Worker-side tqdm streaming (Approach B — rejected).
- Any change to Chatterbox (it keeps its lazy in-worker weight download; only its venv-install has a dialog).
- Folding the weight download into `studio.py install-omnivoice` (kept separate so the weights get the %-bar dialog rather than the install log).
