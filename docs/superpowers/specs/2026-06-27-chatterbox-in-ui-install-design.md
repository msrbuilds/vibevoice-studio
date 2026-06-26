# In-UI Chatterbox Install — Design

**Date:** 2026-06-27
**Status:** Approved (design)

## Problem

Chatterbox now runs in an isolated `backend/venv-chatterbox` (it needs `transformers
5.x`, which breaks VibeVoice). That venv is built only via `python studio.py setup` /
`models` (select Chatterbox). So if a user selects Chatterbox in the UI without having
done that one-time install, they hit a "run `studio.py models`" error. The user wants
the previous "just select it in the UI" experience back — without re-merging the envs.

## Goal

Let the user install Chatterbox from the UI: when Chatterbox isn't installed, the engine
selector offers an **Install Chatterbox** action that builds `venv-chatterbox` in the
background, streams the full install log into a modal, and — on success — lets the user
switch to Chatterbox normally.

## Non-Goals (YAGNI)

- A generic per-engine install framework (only Chatterbox has an isolated env).
- Cancel / uninstall.
- Persisting install progress across a backend restart.
- Pre-downloading model weights during install (weights stay lazy, like every engine).
- Re-merging Chatterbox into the main venv (the isolation must hold).

## Solution Overview

The engine list already flows backend → UI via `/api/engines`. Add an `installed` flag to
each engine, a thread-safe backend **install manager** that runs the build as a background
subprocess (reusing `studio.py`'s install logic), and a **full-log modal** in the UI that
starts the install and polls its log to completion.

```
EngineSelector row (chatterbox, installed:false)
   └─ "Install Chatterbox" → InstallChatterboxDialog (modal)
         POST /api/engines/chatterbox/install   → starts background install
         GET  /api/engines/chatterbox/install   → {state, log[], returncode}  (polled ~1s)
                          │
                 ChatterboxInstaller (backend singleton on app.state)
                          │ spawns  sys.executable studio.py install-chatterbox
                          └─ studio._ensure_chatterbox_env(): venv + CUDA torch + chatterbox-tts
```

## Backend Components

### 1. `installed` flag on engines

`Engine.info()` (in `backend/core/engines/__init__.py`) gains an `installed: bool` key.
The base implementation returns `True`. `ChatterboxEngine.info()` overrides it to
`self._worker_python.is_file()` (the isolated venv's Python exists). Add `installed: bool`
to `EngineInfoModel` and map it in `_to_model` (`backend/api/engines.py`).

### 2. `studio.py install-chatterbox` (non-interactive subcommand)

- Refactor `_ensure_chatterbox_env()` to **return a bool** (`True` on success, `False` on
  any failure) instead of returning `None`. Existing callers (`_interactive_model_picker`)
  ignore the return value, so they're unaffected.
- Add a `install-chatterbox` subparser to `main()`; `cmd_install_chatterbox(args)` calls
  `_ensure_chatterbox_env()` and returns `0` on success, `1` on failure. This is the
  single source of truth for the install steps; the backend just runs it.

### 3. `backend/services/chatterbox_install.py` — `ChatterboxInstaller`

A thread-safe singleton stored on `app.state.chatterbox_installer`.

State machine: `not_installed` → `installing` → `installed` | `error`.

- `__init__(self, *, runner=None, repo_root=None)` — `runner` is an injectable callable
  used to execute the install and yield log lines (default: spawn
  `sys.executable studio.py install-chatterbox` via `subprocess.Popen` and iterate merged
  stdout/stderr). `repo_root` defaults to the repo root (parent of `backend/`).
- `status() -> dict` — `{"state": <str>, "log": list[str], "returncode": int | None}`.
  The `log` is a capped list (e.g. last 2000 lines).
- `start() -> dict` — under a lock: if `installing`, return current status (idempotent,
  no second process); else clear the log, set `installing`, and launch a daemon thread
  that runs the runner, appending each yielded line to the log, then sets `installed`
  (returncode 0) or `error` (non-zero / exception). Returns the status snapshot.
- The default runner streams lines via `Popen(..., stdout=PIPE, stderr=STDOUT, text=True)`
  and iterates `proc.stdout`. (Merging stderr into stdout avoids the separate-pipe
  drain concern; a single stream is read to EOF.)

The installer does NOT itself decide "already installed" — that's the engine's `installed`
flag. If `start()` is called when the venv already exists, the install simply re-runs
(`_ensure_chatterbox_env` is idempotent: it skips venv creation and pip no-ops satisfied
packages). The UI only shows the Install action when `installed` is false, so this is rare.

### 4. Endpoints (in `backend/api/engines.py`)

- `POST /api/engines/{name}/install` → `400` unless `name == "chatterbox"`; else
  `installer.start()` and return the status.
- `GET /api/engines/{name}/install` → `400` unless `name == "chatterbox"`; else
  `installer.status()`.

Response model `InstallStatusModel`: `{state: str, log: list[str], returncode: int | None}`.
The installer is resolved via a `get_chatterbox_installer` dependency (mirrors
`get_engine_manager`), reading `request.app.state.chatterbox_installer`. `app.py`
constructs the singleton and assigns it to `app.state`.

## Frontend Components

### 1. Types + API (`frontend/src/types/models.ts`, `frontend/src/lib/api.ts`)

- `EngineInfo` gains `installed: boolean`.
- `lib/api.ts` adds `startChatterboxInstall(): Promise<InstallStatus>` (POST) and
  `getChatterboxInstallStatus(): Promise<InstallStatus>` (GET), where
  `InstallStatus = { state: "not_installed" | "installing" | "installed" | "error";
  log: string[]; returncode: number | null }`.

### 2. `EngineSelector` (`frontend/src/components/EngineSelector.tsx`)

When a row's engine has `installed === false`, its button reads **"Install Chatterbox"**
(styled like the others) and, on click, opens the install dialog instead of switching.
Installed engines behave exactly as today. A new optional prop `onInstall(name)` is passed
from `App.tsx`.

### 3. `InstallChatterboxDialog.tsx` (new)

A modal (matches the existing dialog styling, e.g. `UploadVoiceDialog`). On mount it POSTs
`startChatterboxInstall()`, then polls `getChatterboxInstallStatus()` every ~1s while
`state === "installing"`, rendering the accumulated `log` in a scrollable, auto-scrolling
`<pre>`. States:
- *installing* — spinner + live log; close is disabled or warns it keeps running.
- *installed* — success banner; **Close** triggers an engines refresh (so the row flips to
  "Switch to Chatterbox") and dismisses.
- *error* — full log + a **Retry** button (re-POST) and **Close**.

Polling stops on unmount and when the state is terminal.

### 4. Wiring (`frontend/src/App.tsx`)

Hold `installEngineOpen` state; pass `onInstall` to `EngineSelector` (via `ActionBar`);
render `InstallChatterboxDialog` when open; on its success-close call the existing engine
refresh (`useEngine().refresh`).

## Data Flow & Lifecycle

1. `/api/engines` reports `chatterbox.installed = false` → selector shows "Install Chatterbox".
2. Click → modal → `POST .../install` → installer spawns `studio.py install-chatterbox`,
   state `installing`.
3. Modal polls `GET .../install` → renders log lines as they arrive.
4. Subprocess exits 0 → state `installed`; modal shows success.
5. Close → engines refresh → `installed = true` → row shows "Switch to Chatterbox".
6. User switches; the worker spawns lazily on first Generate; model weights download then.

## Error Handling

- Pip/network failure → `error` state, full log shown, **Retry** re-POSTs.
- Concurrent `start()` calls coalesce (lock + `installing` check) — one process only.
- Backend restart mid-install loses the in-memory state; on restart status is re-derived
  from venv presence (`installed` or `not_installed`). Acceptable.
- Partial venv from a failed run: re-running install is safe (`_ensure_chatterbox_env`
  skips existing venv and re-runs idempotent pip installs).

## Testing

- **Installer state machine** (`ChatterboxInstaller`) with an **injected fake runner**
  (a generator yielding canned log lines + a return code): `not_installed → installing →
  installed`; failure path → `error`; idempotent `start()` while installing returns
  without launching a second run; log accumulates in order. Use a thread-join/poll helper
  so the test is deterministic.
- **`installed` flag**: `ChatterboxEngine(worker_python=<existing path>).info()["installed"]`
  is `True`; with a nonexistent path it's `False`. Base engines report `True`.
- **Endpoints** via `TestClient`: `GET /api/engines/chatterbox/install` returns a status;
  `POST`/`GET` with a non-chatterbox name → `400`; POST starts the (fake-runner) installer.
- **`studio.py install-chatterbox`**: `main(["install-chatterbox"])` calls
  `_ensure_chatterbox_env` (monkeypatched to return True/False — no real pip) and returns
  the right exit code.
- **Frontend**: `npm run typecheck` + manual modal walkthrough.

All backend tests run on the main venv with fakes/monkeypatch — none run real pip or
require `chatterbox-tts`.

## File Summary

| Path | Change |
|------|--------|
| `backend/core/engines/__init__.py` | Modify — add `installed` to `Engine.info()` (base True) |
| `backend/core/engines/chatterbox_engine.py` | Modify — override `info()["installed"]` from venv presence |
| `studio.py` | Modify — `_ensure_chatterbox_env()` returns bool; add `install-chatterbox` subcommand |
| `backend/services/chatterbox_install.py` | New — `ChatterboxInstaller` singleton + state machine |
| `backend/api/engines.py` | Modify — `installed` in model; `GET`/`POST /{name}/install` |
| `backend/api/deps.py` | Modify — `get_chatterbox_installer` dependency |
| `backend/app.py` | Modify — construct installer onto `app.state` |
| `backend/tests/test_chatterbox_install.py` | New — installer + endpoint + flag tests |
| `frontend/src/types/models.ts` | Modify — `EngineInfo.installed`; `InstallStatus` |
| `frontend/src/lib/api.ts` | Modify — install start/status calls |
| `frontend/src/components/EngineSelector.tsx` | Modify — Install action when not installed |
| `frontend/src/components/InstallChatterboxDialog.tsx` | New — full-log install modal |
| `frontend/src/App.tsx` (+ `ActionBar.tsx`) | Modify — wire the dialog + refresh on success |
| `README.md` / `CLAUDE.md` | Modify — note the in-UI install path |
