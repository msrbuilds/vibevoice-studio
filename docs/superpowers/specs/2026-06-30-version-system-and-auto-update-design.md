# Version System & Auto-Update from GitHub — Design

**Date:** 2026-06-30
**Status:** Approved (brainstorming) — pending implementation plan
**Component:** Voice Studio by MSR (`github.com/msrbuilds/voice-studio`)

## Goal

Give Voice Studio a single, authoritative version number and an in-app
"auto-check, one-click apply" updater that pulls tagged GitHub releases.

## Decisions (locked)

| Question | Decision |
|---|---|
| Version signal | **Tagged GitHub Releases (semver)**. The release tag (e.g. `v0.3.0`) is the version. |
| Update behavior | **Auto-check + manual one-click apply.** No silent auto-apply. |
| Delivery | **git when possible, notify-only fallback.** A clean git checkout updates in place; non-git/dirty installs are told to update manually with a link to the release page. |
| Update target | **Pin to the latest release tag** (not rolling `main`). |
| Dependencies on update | **Main venv only** (`backend/requirements.txt`). Isolated engine venvs are left untouched in v1. |
| Restart | **Manual in v1.** Update finishes with "restart to apply." No in-app self-relaunch. |

## Architecture

The updater reuses the **existing engine-install pattern**: the engine-install
endpoints run `studio.py install-{engine}` as a subprocess and stream the live
log to a polling dialog (`InstallEngineDialog`). The updater mirrors this shape
exactly — a `studio.py update` subcommand driven by a streaming API endpoint and
a polling dialog.

Data flow:

```
VERSION file ──► core/version.py::get_version() ──► /api/health, /api/config ──► frontend
GitHub API   ──► services/update_check.py::UpdateChecker ──► GET /api/update ──► ControlPanel badge
"Update now" ──► POST /api/update ──► studio.py update (subprocess, streamed log) ──► UpdateDialog
```

## Components

### 1. Version source of truth

- **`VERSION`** file at repo root, single line (e.g. `0.2.0`).
- **`backend/core/version.py::get_version() -> str`** reads it once (cached), with
  a safe fallback string (`"0.0.0"`) if the file is missing.
- `/api/health` and `/api/config` return this value, **replacing** the hardcoded
  `"0.2.0"` in `backend/app.py` and the `"0.1.0"` default in
  `backend/api/schemas.py::HealthResponse`.
- The frontend reads the version from the config/health payload it already
  fetches — no build-time injection.
- `backend/pyproject.toml` and `frontend/package.json` versions are synced to
  `VERSION` when cutting a release (cosmetic; the API is the runtime source).

**Release process:** bump `VERSION` → sync pyproject/package.json → commit → tag
`vX.Y.Z` → publish GitHub Release with notes.

### 2. Update detection — `backend/services/update_check.py`

- `UpdateChecker` calls `GET https://api.github.com/repos/msrbuilds/voice-studio/releases/latest`
  (unauthenticated; 60 req/hr/IP is sufficient), reads `tag_name`, strips a
  leading `v`, and semver-compares to the local `VERSION`.
- Returns a snapshot dict:
  `{ current, latest, update_available, html_url, published_at, body, checked_at, error }`.
- **Failure-tolerant:** any network/API/parse error → `update_available: false`
  with a populated `error` field. Never blocks or crashes startup.
- Result is cached in memory. Refreshed once on startup via a **background thread**
  (non-blocking, like `ModelDownloader`) and on demand via `GET /api/update?force=1`.
- Semver compare is a **pure function** (`is_newer(latest, current) -> bool`)
  for unit testing.

### 3. Update application — `studio.py update` + `backend/services/update_run.py`

`studio.py update` (stdlib-only, mirrors the rest of the launcher):

1. **Guard:** confirm (a) a `.git` dir exists, (b) `git` is on PATH, (c) the
   `origin` remote points at the Voice Studio repo, and (d) the working tree is
   clean (`git status --porcelain` empty). Any failure → exit non-zero with a
   clear message (this is the notify-only fallback path).
2. `git fetch --tags origin` → `git checkout <latest tag>`.
3. Re-sync main venv deps: `pip install -r backend/requirements.txt` (into
   `backend/venv`).
4. `npm install` + `npm run build` in `frontend/`.
5. Print a final `UPDATE OK — restart Voice Studio to apply` line on success.

`backend/services/update_run.py::UpdateRunner` runs `studio.py update` as a
subprocess, draining stdout/stderr into a rolling log buffer, exposing a
single-flight status snapshot `{ state, log, returncode, error }` where `state`
∈ `idle | running | done | error`. One job at a time (mirrors the installers).

### 4. API — `backend/api/update.py`

- `GET /api/update` → update-check snapshot (Section 2). `?force=1` refreshes.
- `POST /api/update` → start (or coalesce onto a running) `studio.py update`;
  returns the `UpdateRunner` status.
- `GET /api/update/run` → live `UpdateRunner` status + log (polled by the dialog).

(Exact path split between check/run can be finalized in the plan; the three
operations above are the contract.)

### 5. Frontend

- **`useUpdate` hook** (mirrors `useConfig`): fetches `GET /api/update` on mount,
  exposes `{ current, latest, updateAvailable, notesUrl, body, check(), ... }`.
- **ControlPanel "About" section:** shows `v{current}`. When `updateAvailable`,
  an orange **"Update to v{latest}"** badge + a manual "Check for updates" action.
- **`UpdateDialog`** (mirrors `InstallEngineDialog`): renders the release notes
  (`body`), an "Update now" button that `POST`s and then polls `GET /api/update/run`,
  the live log, and the terminal "Update complete — restart to apply" message.
  If the guard fails (non-git / dirty tree / no network), the dialog shows the
  reason and a link to `html_url` (the GitHub release page).

## Error handling

- No network / GitHub down → silent; app shows current version, no badge.
- Not a git checkout, wrong remote, or dirty working tree → `studio.py update`
  aborts with a specific message; the dialog surfaces it and offers the manual
  download link.
- Update subprocess fails mid-step (pip/npm) → `state: error` + the captured log;
  the on-disk checkout may be on the new tag but deps stale, so the message tells
  the user to re-run or restart and retry. (Acceptable for v1; no auto-rollback.)
- Concurrent "Update now" clicks → coalesced onto the single running job.

## Testing

Pure-function / mocked unit tests (mirroring `backend/tests/test_setup_helpers.py`):

- `is_newer()` semver comparison (equal, older, newer, `v`-prefix, pre-release).
- Release-JSON parsing → snapshot dict (well-formed, missing fields, HTTP error).
- `studio.py update` guard logic: non-git, wrong remote, dirty tree, happy path
  (git/subprocess calls injected/mocked — **no real `git pull` / `npm` in tests**).
- `get_version()` reads `VERSION`, falls back when missing.

API smoke test: `GET /api/update` returns a valid snapshot with the GitHub call
mocked.

## Out of scope (v1)

- In-app self-restart / relaunch of the running server.
- Updating isolated engine venvs (`venv-chatterbox`, etc.) on app update.
- Zip/release-asset replacement for non-git installs (notify-only instead).
- Auto-rollback on a failed update.
- Background polling on a timer (check is on startup + manual only).
