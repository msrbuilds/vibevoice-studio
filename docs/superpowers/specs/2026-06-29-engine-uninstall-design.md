# Engine Uninstall & Delete Weights — Design

**Date:** 2026-06-29  
**Status:** Approved  
**Scope:** Backend + Frontend. Mirrors the existing install/download pattern exactly.

## Goal

Allow users to reclaim disk space by (a) deleting downloaded model weights for any engine and (b) removing the isolated venv for Chatterbox and OmniVoice — both with live-progress feedback in the UI, using the same patterns as the existing Install and Download Model dialogs.

## Decisions locked during brainstorming

| Question | Decision |
|---|---|
| One combined action vs two separate? | **Two separate actions:** "Delete weights" (all 4 engines) and "Uninstall environment" (Chatterbox/OmniVoice only) |
| UI pattern | **Full progress dialog** (Approach A) — mirrors InstallEngineDialog / DownloadModelDialog exactly, including live log stream |

---

## What gets deleted

| Engine | Delete weights | Uninstall environment |
|---|---|---|
| VibeVoice | `backend/models/hub/models--vibevoice--VibeVoice-1.5B/` | n/a (in-process, no isolated env) |
| Kokoro | `backend/models/hub/models--hexgrad--Kokoro-82M/` | n/a (in-process) |
| Chatterbox | `backend/models/hub/models--ResembleAI--chatterbox/` | `backend/venv-chatterbox/` (whole dir) |
| OmniVoice | `backend/models/hub/models--k2-fsa--OmniVoice/` | `backend/venv-omnivoice/` (whole dir) |

The HF cache layout uses dashes instead of slashes: `models--{org}--{repo}`.

**Ready-marker note:** The `.{engine}-ready` marker file lives *inside* the venv directory (`backend/venv-chatterbox/.chatterbox-ready`, `backend/venv-omnivoice/.omnivoice-ready` — confirmed in `chatterbox_engine.py:_ready_marker`, `omnivoice_engine.py:_ready_marker`, and `studio.py`). So removing the venv directory with a single `shutil.rmtree` deletes the marker too — no separate `unlink` step is needed. After removal, `engine.installed()` (which probes the marker) returns `False` automatically.

---

## Backend

### New file: `backend/services/model_delete.py`

Mirrors `model_download.py`. Locates the HF snapshot directory for a given engine's `repo_id` and deletes it with `shutil.rmtree` on a daemon thread. State machine: `idle → deleting → deleted | error`.

```python
# Public surface
class ModelDeleter:
    def status(self) -> dict:   # {state, log, error}
    def start(self, engine_name: str) -> dict

# All 4 engines have weights in the HF cache and can have them deleted.
# Note: DOWNLOADABLE (model_download.py) = {vibevoice, kokoro, omnivoice} — chatterbox
# is NOT in DOWNLOADABLE because its weights arrive via the chatterbox worker pip install,
# not the in-process HF downloader. But the weights DO land in the shared HF cache, so
# DELETABLE includes chatterbox too.
DELETABLE: frozenset[str]  # {vibevoice, kokoro, omnivoice, chatterbox}
```

The HF cache path is derived from the engine's `repo_id` in `MODEL_CATALOG`. **Preferred (robust) approach:** locate the repo's actual cache dir via the snapshot resolver rather than hand-building a path, then delete the whole repo dir:

```python
def _repo_cache_dir(repo_id: str) -> Path | None:
    """Return the `models--{org}--{repo}` dir in the HF cache, or None if absent.

    Resolve via snapshot_download(local_files_only=True) → that returns
    .../models--org--repo/snapshots/<rev>; walk up two levels to the repo root.
    Falling back to the documented layout if resolution fails.
    """
    try:
        from huggingface_hub import snapshot_download
        snap = Path(snapshot_download(repo_id, local_files_only=True))
        return snap.parent.parent  # snapshots/<rev> -> snapshots -> repo root
    except Exception:
        # Not cached, or partial — fall back to the documented layout so a
        # partial/corrupt download can still be cleaned up.
        from huggingface_hub.constants import HF_HUB_CACHE
        cand = Path(HF_HUB_CACHE) / f"models--{repo_id.replace('/', '--')}"
        return cand if cand.exists() else None
```

Deleting the entire `models--{org}--{repo}/` dir removes blobs + snapshots + refs together, so a subsequent `model_downloaded(repo_id)` probe correctly returns `False`. (Layout for reference: `repo_id="vibevoice/VibeVoice-1.5B"` → `models--vibevoice--VibeVoice-1.5B`; cache root `backend/models/hub/`, set via `HF_HOME`/`HUGGINGFACE_HUB_CACHE` in `core/hf_paths.py`.)

**Note on `downloaded()` for Chatterbox (in scope):** The base `Engine.downloaded()` returns `True` by default. `ChatterboxEngine` currently inherits this (confirmed — no override), so the UI always sees `downloaded=True` for Chatterbox even before its weights exist, and the "Delete weights" button can't gate correctly. Add an override copied verbatim from `OmniVoiceEngine.downloaded()` (its closest sibling — also an isolated engine whose weights live in the shared HF cache):

```python
def downloaded(self) -> bool:
    from ..model_cache import model_downloaded
    return model_downloaded(self._model_id)  # self._model_id == "ResembleAI/chatterbox"
```

**Safety:** before deleting, if the engine is currently loaded, call `engine.unload()` via `EngineManager` to release file handles.

**Status fields:**
```python
{
    "state": "idle" | "deleting" | "deleted" | "error",
    "log": list[str],   # human-readable progress lines
    "error": str | None,
}
```

### New file: `backend/services/engine_uninstall.py`

Mirrors `chatterbox_install.py`. Removes the isolated venv directory and the `.{engine}-ready` marker file using `shutil.rmtree` + `Path.unlink` on a daemon thread. State machine: `idle → uninstalling → uninstalled | error`.

```python
class EngineEnvUninstaller:
    def __init__(self, engine_name: str, ...) -> None
    def status(self) -> dict   # {state, log, error}
    def start(self) -> dict

# Concrete aliases:
class ChatterboxUninstaller(EngineEnvUninstaller): ...
class OmniVoiceUninstaller(EngineEnvUninstaller): ...
```

**What it removes for `chatterbox`:**
- `backend/venv-chatterbox/` (single `rmtree` — the `.chatterbox-ready` marker is inside this dir, so it goes too)

**What it removes for `omnivoice`:**
- `backend/venv-omnivoice/` (single `rmtree` — `.omnivoice-ready` is inside)

**Safety (Windows file lock — critical):** A loaded Chatterbox/OmniVoice engine holds an open `venv-{engine}/Scripts/python.exe` worker subprocess. On Windows you **cannot** `rmtree` a directory containing a running executable — the rmtree will fail with a permission error. So the uninstaller MUST call `engine.unload()` (which kills the worker subprocess) and wait for the process to exit **before** rmtree. The uninstaller resolves the engine via `EngineManager.get_engine(name)` and calls `.unload()` if `.is_loaded()`. Same unload-first applies to model_delete.py (weights may be mmap'd by a loaded model).

**Status fields:**
```python
{
    "state": "idle" | "uninstalling" | "uninstalled" | "error",
    "log": list[str],
    "error": str | None,
}
```

### New endpoints in `backend/api/engines.py`

**Delete model weights:**
```
POST /api/engines/{name}/delete-weights    → start deletion (returns DeleteWeightsStatus)
GET  /api/engines/{name}/delete-weights    → poll status (returns DeleteWeightsStatus)
```

**Uninstall isolated environment:**
```
POST /api/engines/{name}/uninstall    → start uninstall (returns UninstallStatus)
GET  /api/engines/{name}/uninstall    → poll status (returns UninstallStatus)
```

**New Pydantic models:**
```python
class DeleteWeightsStatusModel(BaseModel):
    state: str          # idle | deleting | deleted | error
    log: list[str]
    error: str | None

class UninstallStatusModel(BaseModel):
    state: str          # idle | uninstalling | uninstalled | error
    log: list[str]
    error: str | None
```

**Error responses:**
- 400 if `name` not in `DELETABLE` (for delete-weights) or not in the uninstallable set
- 404 if engine unknown
- 503 if a delete/uninstall is already in-flight (coalesce like the installer does)

### `backend/api/deps.py` additions

Register the new singletons on `app.state` and expose them as FastAPI dependencies:
```python
def get_model_deleter(req: Request) -> ModelDeleter: ...
def get_engine_uninstallers(req: Request) -> dict[str, EngineEnvUninstaller]: ...
```

### `backend/app.py`

Wire the new singletons in `lifespan`:
```python
app.state.model_deleter = ModelDeleter(em=engine_manager)
app.state.engine_uninstallers = {
    "chatterbox": ChatterboxUninstaller(em=engine_manager),
    "omnivoice": OmniVoiceUninstaller(em=engine_manager),
}
```

Include the existing `engines` router (no new router needed — new endpoints are in the same `engines.py`).

---

## Frontend

### New API wrappers in `frontend/src/lib/api.ts`

```ts
export interface DeleteWeightsStatus {
  state: "idle" | "deleting" | "deleted" | "error";
  log: string[];
  error: string | null;
}

export interface UninstallStatus {
  state: "idle" | "uninstalling" | "uninstalled" | "error";
  log: string[];
  error: string | null;
}

export async function startDeleteWeights(name: string): Promise<DeleteWeightsStatus>
export async function getDeleteWeightsStatus(name: string): Promise<DeleteWeightsStatus>
export async function startUninstallEngine(name: string): Promise<UninstallStatus>
export async function getUninstallStatus(name: string): Promise<UninstallStatus>
```

### New component: `frontend/src/components/DeleteWeightsDialog.tsx`

Mirrors `DownloadModelDialog.tsx` structurally:
- Props: `{ isDark, engineName, displayName, sizeLabel, onClose, onDone }`
- On mount: shows a confirmation message with the engine name and size that will be freed
- "Delete weights" button triggers `startDeleteWeights` then polls `getDeleteWeightsStatus` every 500ms
- Renders a scrollable log output (reuse the same log-display pattern from `InstallEngineDialog`)
- On `state === "deleted"`: shows success message, "Close" button calls `onDone()`
- On `state === "error"`: shows error in red, "Close" button calls `onClose()`
- Backdrop click = close (same as existing dialogs)

**Styling:** danger-themed confirm button (red, same as `ConfirmDialog` danger mode), not orange — deleting weights is destructive.

### New component: `frontend/src/components/UninstallEngineDialog.tsx`

Mirrors `InstallEngineDialog.tsx` structurally:
- Props: `{ isDark, engineName, displayName, onClose, onUninstalled }`
- Warns what will be removed (venv path, marker file)
- "Uninstall" button triggers `startUninstallEngine` then polls `getUninstallStatus` every 500ms
- Same log display, same success/error handling
- On `state === "uninstalled"`: calls `onUninstalled()` (which triggers engine list refresh in `App.tsx`)

**Styling:** danger-themed confirm button (red).

### `frontend/src/components/EngineSelector.tsx` changes

In the engine card (`<li>` for each engine), add secondary action buttons below the primary action:

```
[Switch to VibeVoice]         ← primary (existing)
[Delete weights  X]           ← new secondary (shown when downloaded===true)

[Switch to Chatterbox]        ← primary (existing, for installed+downloaded engine)
[Delete weights  X]           ← new secondary
[Uninstall env   X]           ← new secondary (only for Chatterbox/OmniVoice when installed)
```

Button styling: small, text-only with a red tint — `text-xs text-red-600 hover:text-red-700 dark:text-red-400 dark:hover:text-red-300`. No background — low visual weight so it doesn't compete with the primary action button.

**State-gating (definitive):**
- "Delete weights" shown only when `engine.downloaded === true`.
- "Uninstall environment" shown only when `engine.installed === true` AND engine name is `chatterbox` or `omnivoice` (the only two with isolated venvs).
- **Both destructive actions are hidden for the currently-active engine** (`engine.active === true`). Rationale: deleting weights / removing the venv of the engine you're actively using would unload it mid-session (and on Windows, unload-first is required anyway). The user must switch to another engine first; then the buttons appear on the now-inactive card. This is simpler and safer than disabled-with-tooltip, and avoids a "deleted the model out from under myself" footgun.

### `frontend/src/App.tsx` additions

Add two new state variables mirroring `installEngine` and `downloadEngine`:
```tsx
const [deleteWeightsEngine, setDeleteWeightsEngine] = useState<string | null>(null);
const [uninstallEngine, setUninstallEngine] = useState<string | null>(null);
```

Pass new callbacks to `ControlPanel` → `EngineSelector`:
```tsx
onDeleteWeights={(name) => setDeleteWeightsEngine(name)}
onUninstallEngine={(name) => setUninstallEngine(name)}
```

Render new dialogs at the bottom of the main return:
```tsx
{deleteWeightsEngine && (
  <DeleteWeightsDialog
    isDark={isDark}
    engineName={deleteWeightsEngine}
    displayName={engines.find(e => e.name === deleteWeightsEngine)?.display_name ?? deleteWeightsEngine}
    sizeLabel={/* from MODEL_CATALOG */}
    onClose={() => setDeleteWeightsEngine(null)}
    onDone={async () => { await refreshEngines(); setDeleteWeightsEngine(null); }}
  />
)}
{uninstallEngine && (
  <UninstallEngineDialog
    isDark={isDark}
    engineName={uninstallEngine}
    displayName={engines.find(e => e.name === uninstallEngine)?.display_name ?? uninstallEngine}
    onClose={() => setUninstallEngine(null)}
    onUninstalled={async () => { await refreshEngines(); setUninstallEngine(null); }}
  />
)}
```

### `frontend/src/components/ControlPanel.tsx`

Add `onDeleteWeights` and `onUninstallEngine` to the Props interface and pass them through to `EngineSelector`.

### `frontend/src/types/models.ts`

The `EngineInfo` type already has `installed: boolean` and `downloaded: boolean`. No new fields needed.

---

## Testing

### Backend tests (`backend/tests/`)

New file: `backend/tests/test_engine_uninstall.py`
- `test_model_deleter_transitions`: mock `shutil.rmtree`, verify state goes `idle → deleting → deleted`
- `test_model_deleter_missing_dir`: directory doesn't exist → `deleted` (idempotent, nothing to remove)
- `test_model_deleter_error`: rmtree raises → `error` state, error message captured in log
- `test_env_uninstaller_transitions`: mock rmtree + unlink, verify state machine
- `test_env_uninstaller_idempotent`: ready marker absent → still succeeds (unlink with missing_ok)
- `test_delete_weights_endpoint_400`: non-deletable engine returns 400
- `test_uninstall_endpoint_400`: non-uninstallable engine (vibevoice) returns 400
- `test_chatterbox_downloaded_probes_cache`: `ChatterboxEngine.downloaded()` returns False when HF dir absent, True when present

### Frontend

- `npm run typecheck` and `npm run build` pass
- Manual Playwright: trigger Delete weights on an installed engine, confirm dialog opens, log streams, card reverts to "Download" after completion

---

## Out of scope

- Re-downloading after deletion is handled by the existing Download Model flow
- Re-installing after uninstall is handled by the existing Install flow
- No CLI (`studio.py uninstall-chatterbox`) needed — backend API is sufficient
- No progress percentage for deletion (rmtree doesn't stream progress) — just log lines like "Removing venv-chatterbox (may take a few seconds)…" then "Done."
