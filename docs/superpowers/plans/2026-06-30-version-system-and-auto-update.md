# Version System & Auto-Update from GitHub — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Give Voice Studio one authoritative version number and an in-app "auto-check, one-click apply" updater that pulls tagged GitHub releases.

**Architecture:** A root `VERSION` file is the single source of truth, surfaced through `/api/health` + `/api/config`. An `UpdateChecker` service compares the local version against the latest GitHub release (via the public API). Applying an update reuses the existing engine-install pattern: a new `studio.py update --tag <tag>` subcommand is driven by an `UpdateRunner` (a clone of `EngineEnvInstaller`) behind `/api/update`, with a polling `UpdateDialog` on the frontend. Non-git / dirty installs fall back to notify-only.

**Tech Stack:** Python 3.11 / FastAPI / pytest (backend); React + Vite + TypeScript (frontend); stdlib-only `studio.py` launcher; GitHub REST API (unauthenticated).

**Spec:** `docs/superpowers/specs/2026-06-30-version-system-and-auto-update-design.md`

**Conventions to follow:**
- Backend tests run with the project venv: `./backend/venv/Scripts/python.exe -m pytest backend/tests/...` (from repo root). Do NOT install isolated venvs or run real `git`/`npm`/`pip` in tests — inject/mferock those.
- Frontend types mirror backend JSON keys verbatim (snake_case, e.g. `update_available`).
- Commit after each task. Never checkout/switch/reset/rebase/merge/push from a subagent — only `git add` + `git commit`.

---

## File Structure

**Backend (new):**
- `VERSION` — repo-root single-line version string (source of truth).
- `backend/core/version.py` — `get_version()` reads `VERSION`.
- `backend/services/update_check.py` — semver compare + `UpdateChecker` (GitHub release polling, cached).
- `backend/services/update_run.py` — `UpdateRunner` (subprocess runner for `studio.py update`, mirrors `EngineEnvInstaller`).
- `backend/api/update.py` — `/api/update` router + Pydantic models.
- `backend/tests/test_version.py`, `test_update_check.py`, `test_update_run.py`, `test_update_api.py` — tests.

**Backend (modified):**
- `studio.py` — add `cmd_update` + `update` subparser + pure guard helpers.
- `backend/app.py` — wire `update_checker`/`update_runner` onto `app.state`; refresh check in lifespan; include router; use `get_version()`.
- `backend/api/health.py` — version from `get_version()`; add `version` to `/config`.
- `backend/api/schemas.py` — `version` on `ConfigResponse`; `HealthResponse.version` default unchanged.
- `backend/api/deps.py` — `get_update_checker`, `get_update_runner`.
- `backend/tests/test_setup_helpers.py` — tests for the new `studio.py` guard helpers.

**Frontend (new):**
- `frontend/src/hooks/useUpdate.ts` — fetches update info.
- `frontend/src/components/UpdateDialog.tsx` — apply-update dialog (mirrors `InstallEngineDialog`).

**Frontend (modified):**
- `frontend/src/types/models.ts` — `UpdateInfo`, `UpdateRunStatus`; `version` on `ConfigResponse`.
- `frontend/src/lib/api.ts` — `getUpdateInfo`, `checkUpdate`, `startUpdate`, `getUpdateRunStatus`.
- `frontend/src/components/ControlPanel.tsx` — "About" section + `UpdateDialog` wiring.

**Docs:**
- `CLAUDE.md` — document the version/update system.

---

## Task 1: VERSION file + `get_version()`

**Files:**
- Create: `VERSION`
- Create: `backend/core/version.py`
- Test: `backend/tests/test_version.py`

- [ ] **Step 1: Create the VERSION file**

Create `VERSION` (repo root) with exactly one line and a trailing newline:

```
0.2.0
```

- [ ] **Step 2: Write the failing test**

Create `backend/tests/test_version.py`:

```python
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT))

from backend.core.version import get_version  # noqa: E402


def test_get_version_reads_root_version_file():
    # The repo-root VERSION file is the single source of truth.
    expected = (REPO_ROOT / "VERSION").read_text(encoding="utf-8").strip()
    assert get_version() == expected
    # Must look like semver X.Y.Z.
    parts = get_version().split(".")
    assert len(parts) == 3 and all(p.isdigit() for p in parts)
```

- [ ] **Step 3: Run the test to verify it fails**

Run: `./backend/venv/Scripts/python.exe -m pytest backend/tests/test_version.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'backend.core.version'`.

- [ ] **Step 4: Implement `get_version()`**

Create `backend/core/version.py`:

```python
"""Single source of truth for the application version.

Reads the repo-root VERSION file (the same string GitHub release tags use).
Cached after first read; falls back to "0.0.0" if the file is missing so the
app never crashes on a malformed checkout.
"""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parents[2]  # backend/core/.. -> repo root
_FALLBACK = "0.0.0"


@lru_cache(maxsize=1)
def get_version() -> str:
    try:
        text = (_REPO_ROOT / "VERSION").read_text(encoding="utf-8").strip()
    except OSError:
        return _FALLBACK
    return text or _FALLBACK
```

- [ ] **Step 5: Run the test to verify it passes**

Run: `./backend/venv/Scripts/python.exe -m pytest backend/tests/test_version.py -v`
Expected: PASS.

- [ ] **Step 6: Commit**

```bash
git add VERSION backend/core/version.py backend/tests/test_version.py
git commit -m "feat(version): VERSION file + get_version() single source of truth"
```

---

## Task 2: Surface the version through `/api/health` and `/api/config`

**Files:**
- Modify: `backend/api/schemas.py`
- Modify: `backend/api/health.py`
- Modify: `backend/app.py`
- Test: `backend/tests/test_version_api.py` (create)

- [ ] **Step 1: Write the failing test**

Create `backend/tests/test_version_api.py`:

```python
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT))

from fastapi.testclient import TestClient  # noqa: E402

from backend.app import create_app  # noqa: E402
from backend.core.version import get_version  # noqa: E402


def test_health_and_config_report_get_version():
    client = TestClient(create_app())
    v = get_version()
    assert client.get("/api/health").json()["version"] == v
    assert client.get("/api/config").json()["version"] == v
```

- [ ] **Step 2: Run the test to verify it fails**

Run: `./backend/venv/Scripts/python.exe -m pytest backend/tests/test_version_api.py -v`
Expected: FAIL — `/config` has no `version` key (KeyError), and `/health` returns hardcoded `"0.2.0"` which only passes by luck; the `/config` assertion fails first.

- [ ] **Step 3: Add `version` to the `ConfigResponse` schema**

In `backend/api/schemas.py`, find the `ConfigResponse` class and add a `version` field (place it as the first field):

```python
class ConfigResponse(BaseModel):
    version: str = "0.0.0"
    model_id: str
    # ... existing fields unchanged ...
```

(Leave `HealthResponse.version` as-is; `health.py` will populate it from `get_version()`.)

- [ ] **Step 4: Populate the version in `health.py`**

In `backend/api/health.py`, add the import near the top:

```python
from ..core.version import get_version
```

In the `health(...)` function, change the `version="0.2.0"` argument to:

```python
        version=get_version(),
```

In the `config(...)` function, add `version=get_version(),` as the first argument to the `ConfigResponse(...)` constructor:

```python
    return ConfigResponse(
        version=get_version(),
        model_id=model_id,
        # ... existing args unchanged ...
```

- [ ] **Step 5: Replace the hardcoded version in `app.py`**

In `backend/app.py`, add the import alongside the other `core` imports (above the FastAPI construction, after the HF-cache setup block):

```python
from .core.version import get_version
```

Change the FastAPI app construction `version="0.2.0",` to:

```python
        version=get_version(),
```

- [ ] **Step 6: Run the tests to verify they pass**

Run: `./backend/venv/Scripts/python.exe -m pytest backend/tests/test_version_api.py -v`
Expected: PASS.

- [ ] **Step 7: Commit**

```bash
git add backend/api/schemas.py backend/api/health.py backend/app.py backend/tests/test_version_api.py
git commit -m "feat(version): report get_version() from /health and /config"
```

---

## Task 3: Update-detection service (`update_check.py`)

**Files:**
- Create: `backend/services/update_check.py`
- Test: `backend/tests/test_update_check.py`

- [ ] **Step 1: Write the failing tests**

Create `backend/tests/test_update_check.py`:

```python
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT))

from backend.services.update_check import (  # noqa: E402
    UpdateChecker,
    build_snapshot,
    is_newer,
)


def test_is_newer_basic():
    assert is_newer("0.3.0", "0.2.0") is True
    assert is_newer("v0.3.0", "0.2.0") is True
    assert is_newer("0.2.0", "0.2.0") is False
    assert is_newer("0.1.0", "0.2.0") is False


def test_is_newer_prerelease_and_garbage():
    # A pre-release ranks below the same X.Y.Z release.
    assert is_newer("0.3.0-rc1", "0.2.0") is True
    assert is_newer("0.2.0-rc1", "0.2.0") is False
    # Malformed input is never "newer" (fail safe).
    assert is_newer("garbage", "0.2.0") is False
    assert is_newer("0.3.0", "nonsense") is False


def test_build_snapshot_update_available():
    payload = {
        "tag_name": "v0.3.0",
        "html_url": "https://github.com/msrbuilds/voice-studio/releases/tag/v0.3.0",
        "published_at": "2026-07-01T00:00:00Z",
        "body": "Release notes here",
    }
    snap = build_snapshot(payload, current="0.2.0", checked_at=123.0)
    assert snap["current"] == "0.2.0"
    assert snap["latest"] == "0.3.0"
    assert snap["update_available"] is True
    assert snap["html_url"].endswith("/v0.3.0")
    assert snap["body"] == "Release notes here"
    assert snap["checked_at"] == 123.0
    assert snap["error"] is None


def test_build_snapshot_error_is_safe():
    snap = build_snapshot(None, current="0.2.0", checked_at=1.0, error="boom")
    assert snap["update_available"] is False
    assert snap["latest"] is None
    assert snap["error"] == "boom"


def test_checker_uses_injected_fetcher_and_caches():
    calls = {"n": 0}

    def fetcher():
        calls["n"] += 1
        return {"tag_name": "v0.9.0", "html_url": "u", "published_at": "p", "body": "b"}

    chk = UpdateChecker(current="0.2.0", fetcher=fetcher)
    first = chk.check()
    assert first["update_available"] is True
    assert first["latest"] == "0.9.0"
    # Second call is served from cache (no extra fetch).
    chk.check()
    assert calls["n"] == 1
    # force=True re-fetches.
    chk.check(force=True)
    assert calls["n"] == 2


def test_checker_swallows_fetch_errors():
    def fetcher():
        raise RuntimeError("network down")

    chk = UpdateChecker(current="0.2.0", fetcher=fetcher)
    snap = chk.check()
    assert snap["update_available"] is False
    assert snap["error"] is not None
    # snapshot() returns the last result without crashing.
    assert chk.snapshot()["current"] == "0.2.0"
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `./backend/venv/Scripts/python.exe -m pytest backend/tests/test_update_check.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'backend.services.update_check'`.

- [ ] **Step 3: Implement `update_check.py`**

Create `backend/services/update_check.py`:

```python
"""GitHub-release update detection.

Pure helpers (`parse_semver`, `is_newer`, `build_snapshot`) are unit-tested in
isolation. `UpdateChecker` compares the local version against the latest GitHub
release and caches the result. The fetcher is injectable so tests never hit the
network. All failures are swallowed into the snapshot's `error` field — checking
for updates must never crash or block the app.
"""

from __future__ import annotations

import json
import logging
import re
import threading
import time
import urllib.request
from typing import Callable, Optional

log = logging.getLogger(__name__)

_REPO = "msrbuilds/voice-studio"
_API_URL = f"https://api.github.com/repos/{_REPO}/releases/latest"
_TIMEOUT_SEC = 8
# Re-check at most this often unless force=True (avoids hammering the API).
_CACHE_TTL_SEC = 600

_SEMVER_RE = re.compile(r"^v?(\d+)\.(\d+)\.(\d+)(?:[-+].*)?$")

Fetcher = Callable[[], dict]


def parse_semver(s: str) -> Optional[tuple[int, int, int, int]]:
    """(major, minor, patch, release_rank) or None if unparseable.

    release_rank is 1 for a final release and 0 for a pre-release (anything with
    a '-' suffix), so a release sorts above the same X.Y.Z pre-release.
    """
    m = _SEMVER_RE.match((s or "").strip())
    if not m:
        return None
    is_pre = "-" in (s or "")
    return (int(m.group(1)), int(m.group(2)), int(m.group(3)), 0 if is_pre else 1)


def is_newer(latest: str, current: str) -> bool:
    """True iff `latest` is a strictly newer semver than `current`. Fail-safe:
    any unparseable input returns False."""
    pl, pc = parse_semver(latest), parse_semver(current)
    if pl is None or pc is None:
        return False
    return pl > pc


def build_snapshot(
    payload: Optional[dict],
    *,
    current: str,
    checked_at: float,
    error: Optional[str] = None,
) -> dict:
    """Normalize a GitHub release payload into the API snapshot dict."""
    if error is not None or not payload:
        return {
            "current": current,
            "latest": None,
            "update_available": False,
            "html_url": None,
            "published_at": None,
            "body": None,
            "checked_at": checked_at,
            "error": error,
        }
    tag = str(payload.get("tag_name") or "")
    return {
        "current": current,
        "latest": tag.lstrip("v") or None,
        "update_available": is_newer(tag, current),
        "html_url": payload.get("html_url"),
        "published_at": payload.get("published_at"),
        "body": payload.get("body"),
        "checked_at": checked_at,
        "error": None,
    }


def _default_fetcher() -> dict:
    """GET the latest release from GitHub (unauthenticated). Raises on failure."""
    req = urllib.request.Request(
        _API_URL,
        headers={
            "Accept": "application/vnd.github+json",
            "User-Agent": "VoiceStudio-Updater",
        },
    )
    with urllib.request.urlopen(req, timeout=_TIMEOUT_SEC) as resp:  # noqa: S310
        return json.loads(resp.read().decode("utf-8"))


class UpdateChecker:
    """Caches the latest-release comparison. Thread-safe; failure-tolerant."""

    def __init__(self, current: str, *, fetcher: Fetcher | None = None) -> None:
        self._current = current
        self._fetcher = fetcher or _default_fetcher
        self._lock = threading.Lock()
        self._snapshot: dict | None = None

    def snapshot(self) -> dict:
        """Last result, or an 'unchecked' default (never None, never raises)."""
        with self._lock:
            if self._snapshot is not None:
                return dict(self._snapshot)
        return build_snapshot(
            None, current=self._current, checked_at=0.0, error="not checked yet"
        )

    def check(self, *, force: bool = False) -> dict:
        """Return a fresh snapshot, fetching from GitHub unless a recent cached
        result exists (and force is False)."""
        now = time.time()
        with self._lock:
            cached = self._snapshot
            if (
                not force
                and cached is not None
                and cached.get("error") is None
                and now - float(cached.get("checked_at", 0.0)) < _CACHE_TTL_SEC
            ):
                return dict(cached)
        try:
            payload = self._fetcher()
            snap = build_snapshot(payload, current=self._current, checked_at=now)
        except Exception as exc:  # noqa: BLE001
            log.info("Update check failed: %s", exc)
            snap = build_snapshot(
                None, current=self._current, checked_at=now, error=str(exc)
            )
        with self._lock:
            self._snapshot = snap
        return dict(snap)

    def refresh_async(self) -> None:
        """Kick off a background check; swallow all errors. Used at startup."""
        threading.Thread(
            target=lambda: self.check(force=True), daemon=True
        ).start()
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `./backend/venv/Scripts/python.exe -m pytest backend/tests/test_update_check.py -v`
Expected: PASS (all 6 tests).

- [ ] **Step 5: Commit**

```bash
git add backend/services/update_check.py backend/tests/test_update_check.py
git commit -m "feat(update): GitHub release update-detection service"
```

---

## Task 4: `studio.py update` subcommand + pure guard helpers

**Files:**
- Modify: `studio.py`
- Test: `backend/tests/test_setup_helpers.py`

- [ ] **Step 1: Write the failing tests for the pure helpers**

Append to `backend/tests/test_setup_helpers.py`:

```python
def test_remote_is_voice_studio():
    import studio
    assert studio.remote_is_voice_studio("https://github.com/msrbuilds/voice-studio.git")
    assert studio.remote_is_voice_studio("git@github.com:msrbuilds/voice-studio.git")
    assert not studio.remote_is_voice_studio("https://github.com/someoneelse/other.git")
    assert not studio.remote_is_voice_studio("")


def test_worktree_is_clean():
    import studio
    assert studio.worktree_is_clean("") is True
    assert studio.worktree_is_clean("   \n  ") is True
    assert studio.worktree_is_clean(" M backend/app.py\n") is False
    assert studio.worktree_is_clean("?? newfile\n") is False
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `./backend/venv/Scripts/python.exe -m pytest backend/tests/test_setup_helpers.py -k "remote_is_voice_studio or worktree_is_clean" -v`
Expected: FAIL — `AttributeError: module 'studio' has no attribute 'remote_is_voice_studio'`.

- [ ] **Step 3: Add the pure guard helpers to `studio.py`**

In `studio.py`, add these near the other small helpers (e.g. just below `_run`):

```python
def remote_is_voice_studio(url: str) -> bool:
    """True if a git remote URL points at the Voice Studio repo (any form)."""
    return "msrbuilds/voice-studio" in (url or "").lower()


def worktree_is_clean(porcelain: str) -> bool:
    """True if `git status --porcelain` output indicates no local changes."""
    return not (porcelain or "").strip()
```

- [ ] **Step 4: Run the helper tests to verify they pass**

Run: `./backend/venv/Scripts/python.exe -m pytest backend/tests/test_setup_helpers.py -k "remote_is_voice_studio or worktree_is_clean" -v`
Expected: PASS.

- [ ] **Step 5: Add the `cmd_update` command**

In `studio.py`, add this function near the other `cmd_*` functions (e.g. after `cmd_install_qwen`). It reuses the existing `_run`, `venv_python`, `_npm`, `BANNER`, `REPO_ROOT`, `BACKEND_DIR`, `FRONTEND_DIR`:

```python
def _git_out(args: list[str]) -> tuple[int, str]:
    """Run a git command in REPO_ROOT, returning (returncode, stdout)."""
    try:
        p = subprocess.run(
            ["git", *args],
            cwd=str(REPO_ROOT),
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
        )
        return p.returncode, p.stdout
    except FileNotFoundError:
        return 127, "git not found on PATH"


def cmd_update(args: argparse.Namespace) -> int:
    """Apply an update by checking out a release tag, then re-syncing deps and
    rebuilding the frontend. Guards refuse to touch a non-git / dirty checkout.
    Used by the in-app updater; --tag is the release tag to check out.
    """
    print(BANNER)
    tag = args.tag

    # --- Guards (the notify-only fallback path lives here) ---
    if not (REPO_ROOT / ".git").exists():
        print("ERROR: not a git checkout — auto-update is unavailable. "
              "Download the latest release from GitHub instead.")
        return 1
    rc, _ = _git_out(["rev-parse", "--is-inside-work-tree"])
    if rc != 0:
        print("ERROR: git is unavailable or this is not a git repo. "
              "Install git or update manually.")
        return 1
    rc, remote = _git_out(["remote", "get-url", "origin"])
    if rc != 0 or not remote_is_voice_studio(remote):
        print("ERROR: the 'origin' remote is not the Voice Studio repo. "
              "Refusing to auto-update.")
        return 1
    rc, porcelain = _git_out(["status", "--porcelain"])
    if rc != 0 or not worktree_is_clean(porcelain):
        print("ERROR: you have uncommitted local changes. Commit or discard "
              "them before updating, or update manually.")
        return 1

    # --- Apply ---
    print("\n[1/4] Fetching tags …")
    if _run(["git", "fetch", "origin", "--tags"], cwd=REPO_ROOT) != 0:
        print("ERROR: git fetch failed.")
        return 1
    print(f"[2/4] Checking out {tag} …")
    if _run(["git", "checkout", tag], cwd=REPO_ROOT) != 0:
        print(f"ERROR: could not check out {tag}.")
        return 1

    py = venv_python(REPO_ROOT)
    if py.is_file():
        print("[3/4] Syncing backend dependencies …")
        if _run([str(py), "-m", "pip", "install", "-r",
                 str(BACKEND_DIR / "requirements.txt")]) != 0:
            print("ERROR: dependency sync failed.")
            return 1
    else:
        print("[3/4] No backend venv found — skipping dependency sync. "
              "Run `python studio.py setup`.")

    npm = _npm()
    if npm:
        print("[4/4] Rebuilding frontend …")
        if _run([npm, "install"], cwd=FRONTEND_DIR) != 0:
            print("ERROR: npm install failed.")
            return 1
        if _run([npm, "run", "build"], cwd=FRONTEND_DIR) != 0:
            print("ERROR: frontend build failed.")
            return 1
    else:
        print("[4/4] npm not found — skipping frontend rebuild. "
              "Install Node.js 18+ and run `cd frontend && npm run build`.")

    print(f"\nUPDATE OK — now on {tag}. Restart Voice Studio to apply.")
    return 0
```

- [ ] **Step 6: Register the `update` subparser and dispatch it**

In `studio.py`, in the argument-parser setup (where the other `sub.add_parser(...)` calls are), add:

```python
    p_update = sub.add_parser("update", help="check out a release tag, sync deps, rebuild frontend")
    p_update.add_argument("--tag", required=True, help="release tag to check out (e.g. v0.3.0)")
```

In the command dispatch block (where `if args.command == "install-qwen": ...` lives), add:

```python
    if args.command == "update":
        return cmd_update(args)
```

- [ ] **Step 7: Smoke-check the CLI wiring (no real update)**

Run: `./backend/venv/Scripts/python.exe studio.py update --tag v0.0.0-test`
Expected: prints the banner then a guard message and exits non-zero (this repo's working tree is dirty during development and/or the tag won't exist) — it must NOT traceback. This confirms argparse wiring + guards run. Do not expect success here.

- [ ] **Step 8: Run the full setup-helpers suite**

Run: `./backend/venv/Scripts/python.exe -m pytest backend/tests/test_setup_helpers.py -v`
Expected: PASS (existing tests + the 2 new ones).

- [ ] **Step 9: Commit**

```bash
git add studio.py backend/tests/test_setup_helpers.py
git commit -m "feat(update): studio.py update subcommand + git guard helpers"
```

---

## Task 5: `UpdateRunner` service

**Files:**
- Create: `backend/services/update_run.py`
- Test: `backend/tests/test_update_run.py`

- [ ] **Step 1: Write the failing tests**

Create `backend/tests/test_update_run.py`:

```python
import sys
import time
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT))

from backend.services.update_run import UpdateRunner  # noqa: E402


def _wait(runner, state, timeout=2.0):
    end = time.time() + timeout
    while time.time() < end:
        if runner.status()["state"] == state:
            return
        time.sleep(0.01)
    raise AssertionError(f"runner never reached {state}: {runner.status()}")


def test_runner_success_streams_log_and_finishes():
    seen = {}

    def runner_fn(tag):
        seen["tag"] = tag
        yield "line one", None
        yield "line two", None
        yield None, 0

    r = UpdateRunner(runner_factory=lambda tag: runner_fn(tag))
    started = r.start("v0.3.0")
    assert started["state"] == "running"
    _wait(r, "done")
    s = r.status()
    assert s["returncode"] == 0
    assert "line one" in s["log"] and "line two" in s["log"]
    assert seen["tag"] == "v0.3.0"


def test_runner_nonzero_is_error():
    def runner_fn(tag):
        yield "boom", None
        yield None, 1

    r = UpdateRunner(runner_factory=lambda tag: runner_fn(tag))
    r.start("v0.3.0")
    _wait(r, "error")
    assert r.status()["returncode"] == 1


def test_runner_coalesces_concurrent_starts():
    def runner_fn(tag):
        time.sleep(0.2)
        yield None, 0

    r = UpdateRunner(runner_factory=lambda tag: runner_fn(tag))
    first = r.start("v0.3.0")
    second = r.start("v0.3.0")  # should NOT launch a second job
    assert first["state"] == "running"
    assert second["state"] == "running"
    _wait(r, "done", timeout=2.0)
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `./backend/venv/Scripts/python.exe -m pytest backend/tests/test_update_run.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'backend.services.update_run'`.

- [ ] **Step 3: Implement `update_run.py`**

Create `backend/services/update_run.py` (mirrors `EngineEnvInstaller`, with the `idle/running/done/error` vocabulary and a `--tag` argument):

```python
"""Background runner for `python studio.py update --tag <tag>`.

Mirrors services.chatterbox_install.EngineEnvInstaller but with the update
state vocabulary (idle -> running -> done | error) and a release tag passed to
the subprocess. The runner factory is injectable so tests don't run real git.
"""

from __future__ import annotations

import subprocess
import sys
import threading
from pathlib import Path
from typing import Callable, Iterator, Optional, Tuple

_REPO_ROOT = Path(__file__).resolve().parents[2]
_MAX_LOG_LINES = 2000

RunnerItem = Tuple[Optional[str], Optional[int]]
RunnerFactory = Callable[[str], Iterator[RunnerItem]]


def _default_runner(repo_root: Path, tag: str) -> Iterator[RunnerItem]:
    """Spawn `python studio.py update --tag <tag>` and stream merged output."""
    proc = subprocess.Popen(
        [sys.executable, "studio.py", "update", "--tag", tag],
        cwd=str(repo_root),
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        bufsize=1,
    )
    assert proc.stdout is not None
    for line in proc.stdout:
        yield line.rstrip("\n"), None
    proc.wait()
    yield None, proc.returncode


class UpdateRunner:
    """Thread-safe single-flight runner for the update subprocess."""

    def __init__(
        self,
        *,
        runner_factory: RunnerFactory | None = None,
        repo_root: Path | None = None,
    ) -> None:
        self._repo_root = repo_root or _REPO_ROOT
        self._runner_factory: RunnerFactory = runner_factory or (
            lambda tag: _default_runner(self._repo_root, tag)
        )
        self._lock = threading.Lock()
        self._state = "idle"
        self._log: list[str] = []
        self._returncode: int | None = None
        self._error: str | None = None
        self._thread: threading.Thread | None = None

    def status(self) -> dict:
        with self._lock:
            return {
                "state": self._state,
                "log": list(self._log),
                "returncode": self._returncode,
                "error": self._error,
            }

    def start(self, tag: str) -> dict:
        with self._lock:
            if self._state == "running":
                return {
                    "state": self._state,
                    "log": list(self._log),
                    "returncode": self._returncode,
                    "error": self._error,
                }
            self._state = "running"
            self._log = []
            self._returncode = None
            self._error = None
            self._thread = threading.Thread(target=self._run, args=(tag,), daemon=True)
            self._thread.start()
            return {"state": self._state, "log": [], "returncode": None, "error": None}

    def _run(self, tag: str) -> None:
        rc: int | None = None
        try:
            for line, code in self._runner_factory(tag):
                if line is not None:
                    with self._lock:
                        self._log.append(line)
                        if len(self._log) > _MAX_LOG_LINES:
                            del self._log[: len(self._log) - _MAX_LOG_LINES]
                if code is not None:
                    rc = code
        except Exception as exc:  # noqa: BLE001
            with self._lock:
                self._log.append(f"[update error] {exc}")
                self._state = "error"
                self._returncode = -1
                self._error = str(exc)
            return
        with self._lock:
            self._returncode = rc
            self._state = "done" if rc == 0 else "error"
            if rc != 0:
                self._error = f"update exited with code {rc}"
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `./backend/venv/Scripts/python.exe -m pytest backend/tests/test_update_run.py -v`
Expected: PASS (all 3 tests).

- [ ] **Step 5: Commit**

```bash
git add backend/services/update_run.py backend/tests/test_update_run.py
git commit -m "feat(update): UpdateRunner subprocess driver for studio.py update"
```

---

## Task 6: `/api/update` router + wiring + lifespan check

**Files:**
- Create: `backend/api/update.py`
- Modify: `backend/api/deps.py`
- Modify: `backend/app.py`
- Test: `backend/tests/test_update_api.py`

- [ ] **Step 1: Write the failing test**

Create `backend/tests/test_update_api.py`:

```python
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT))

from fastapi.testclient import TestClient  # noqa: E402

from backend.app import create_app  # noqa: E402
from backend.services.update_check import UpdateChecker  # noqa: E402


def _client_with_fake_release(tag: str) -> TestClient:
    app = create_app()
    # Replace the real (network) checker with one using a stub fetcher.
    app.state.update_checker = UpdateChecker(
        current="0.2.0",
        fetcher=lambda: {
            "tag_name": tag,
            "html_url": f"https://github.com/msrbuilds/voice-studio/releases/tag/{tag}",
            "published_at": "2026-07-01T00:00:00Z",
            "body": "notes",
        },
    )
    return TestClient(app)


def test_get_update_reports_available():
    client = _client_with_fake_release("v0.9.0")
    data = client.get("/api/update?force=1").json()
    assert data["current"] == "0.2.0"
    assert data["latest"] == "0.9.0"
    assert data["update_available"] is True
    assert data["html_url"].endswith("/v0.9.0")


def test_get_update_run_status_starts_idle():
    client = _client_with_fake_release("v0.9.0")
    data = client.get("/api/update/run").json()
    assert data["state"] in ("idle", "running", "done", "error")
    assert isinstance(data["log"], list)
```

- [ ] **Step 2: Run the test to verify it fails**

Run: `./backend/venv/Scripts/python.exe -m pytest backend/tests/test_update_api.py -v`
Expected: FAIL — 404s (router not mounted) / `app.state` has no `update_checker`.

- [ ] **Step 3: Add the dependency getters**

In `backend/api/deps.py`, add:

```python
def get_update_checker(request: Request):
    return request.app.state.update_checker  # type: ignore[no-any-return]


def get_update_runner(request: Request):
    return request.app.state.update_runner  # type: ignore[no-any-return]
```

- [ ] **Step 4: Implement the router**

Create `backend/api/update.py`:

```python
"""GET/POST /api/update — version check + one-click apply."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from .deps import get_update_checker, get_update_runner

router = APIRouter(prefix="/api/update", tags=["update"])


class UpdateInfoModel(BaseModel):
    current: str
    latest: str | None = None
    update_available: bool = False
    html_url: str | None = None
    published_at: str | None = None
    body: str | None = None
    checked_at: float = 0.0
    error: str | None = None


class UpdateRunStatusModel(BaseModel):
    state: str  # idle | running | done | error
    log: list[str]
    returncode: int | None = None
    error: str | None = None


@router.get("", response_model=UpdateInfoModel)
def update_info(force: bool = False, checker=Depends(get_update_checker)) -> UpdateInfoModel:
    """Latest-release comparison. `?force=1` bypasses the cache."""
    return UpdateInfoModel(**checker.check(force=force))


@router.post("", response_model=UpdateRunStatusModel)
def start_update(checker=Depends(get_update_checker), runner=Depends(get_update_runner)) -> UpdateRunStatusModel:
    """Start (or coalesce onto a running) update to the latest release tag."""
    snap = checker.check()
    if not snap.get("update_available") or not snap.get("latest"):
        raise HTTPException(status_code=400, detail="no update available")
    # studio.py expects the tag form (v-prefixed); the snapshot stores it bare.
    tag = f"v{snap['latest']}"
    return UpdateRunStatusModel(**runner.start(tag))


@router.get("/run", response_model=UpdateRunStatusModel)
def update_run_status(runner=Depends(get_update_runner)) -> UpdateRunStatusModel:
    """Live status + log of the in-progress (or last) update run."""
    return UpdateRunStatusModel(**runner.status())
```

- [ ] **Step 5: Wire state, lifespan refresh, and the router into `app.py`**

In `backend/app.py`, add imports near the other service imports:

```python
from .services.update_check import UpdateChecker
from .services.update_run import UpdateRunner
```

In the `create_app` body where other singletons are attached to `app.state`, add:

```python
    app.state.update_checker = UpdateChecker(get_version())
    app.state.update_runner = UpdateRunner()
```

In the `lifespan` function, after the active engine is eager-loaded, add a non-blocking startup check:

```python
        app.state.update_checker.refresh_async()
```

Add the router import with the others (`from .api.update import router as update_router`) and mount it alongside the rest:

```python
    app.include_router(update_router)
```

- [ ] **Step 6: Run the test to verify it passes**

Run: `./backend/venv/Scripts/python.exe -m pytest backend/tests/test_update_api.py -v`
Expected: PASS (both tests).

- [ ] **Step 7: Run the whole backend suite (no regressions)**

Run: `./backend/venv/Scripts/python.exe -m pytest backend/tests/ -q`
Expected: all tests pass.

- [ ] **Step 8: Commit**

```bash
git add backend/api/update.py backend/api/deps.py backend/app.py backend/tests/test_update_api.py
git commit -m "feat(update): /api/update router + app wiring + startup check"
```

---

## Task 7: Frontend types + API wrappers

**Files:**
- Modify: `frontend/src/types/models.ts`
- Modify: `frontend/src/lib/api.ts`

- [ ] **Step 1: Add the types**

In `frontend/src/types/models.ts`, add a `version` field to `ConfigResponse` (first field):

```typescript
export interface ConfigResponse {
  version: string;
  model_id: string;
  // ... existing fields unchanged ...
}
```

And add the two new interfaces at the end of the file:

```typescript
export interface UpdateInfo {
  current: string;
  latest: string | null;
  update_available: boolean;
  html_url: string | null;
  published_at: string | null;
  body: string | null;
  checked_at: number;
  error: string | null;
}

export interface UpdateRunStatus {
  state: "idle" | "running" | "done" | "error";
  log: string[];
  returncode: number | null;
  error: string | null;
}
```

- [ ] **Step 2: Add the API wrappers**

In `frontend/src/lib/api.ts`, add the imports to the existing type-import block:

```typescript
  UpdateInfo,
  UpdateRunStatus,
```

And add the wrappers (near the other engine/install wrappers):

```typescript
export async function getUpdateInfo(): Promise<UpdateInfo> {
  return jsonOrThrow<UpdateInfo>(await fetch(`${API_BASE}/update`));
}

export async function checkUpdate(): Promise<UpdateInfo> {
  return jsonOrThrow<UpdateInfo>(await fetch(`${API_BASE}/update?force=1`));
}

export async function startUpdate(): Promise<UpdateRunStatus> {
  return jsonOrThrow<UpdateRunStatus>(
    await fetch(`${API_BASE}/update`, { method: "POST" }),
  );
}

export async function getUpdateRunStatus(): Promise<UpdateRunStatus> {
  return jsonOrThrow<UpdateRunStatus>(await fetch(`${API_BASE}/update/run`));
}
```

- [ ] **Step 3: Typecheck**

Run (from `frontend/`): `npm run typecheck`
Expected: PASS (no type errors).

- [ ] **Step 4: Commit**

```bash
git add frontend/src/types/models.ts frontend/src/lib/api.ts
git commit -m "feat(update): frontend types + /api/update wrappers"
```

---

## Task 8: `useUpdate` hook

**Files:**
- Create: `frontend/src/hooks/useUpdate.ts`

- [ ] **Step 1: Implement the hook**

Create `frontend/src/hooks/useUpdate.ts` (mirrors the shape of `useConfig`):

```typescript
import { useCallback, useEffect, useState } from "react";
import { checkUpdate, getUpdateInfo } from "@/lib/api";
import type { UpdateInfo } from "@/types/models";

/**
 * Fetches the version/update snapshot from the backend on mount.
 * `check()` forces a fresh GitHub comparison (used by the manual button).
 */
export function useUpdate() {
  const [info, setInfo] = useState<UpdateInfo | null>(null);
  const [checking, setChecking] = useState(false);

  useEffect(() => {
    let alive = true;
    void getUpdateInfo()
      .then((i) => {
        if (alive) setInfo(i);
      })
      .catch(() => {
        /* update check is best-effort; ignore failures */
      });
    return () => {
      alive = false;
    };
  }, []);

  const check = useCallback(async () => {
    setChecking(true);
    try {
      setInfo(await checkUpdate());
    } catch {
      /* ignore — keep last known info */
    } finally {
      setChecking(false);
    }
  }, []);

  return { info, checking, check };
}
```

- [ ] **Step 2: Typecheck**

Run (from `frontend/`): `npm run typecheck`
Expected: PASS.

- [ ] **Step 3: Commit**

```bash
git add frontend/src/hooks/useUpdate.ts
git commit -m "feat(update): useUpdate hook"
```

---

## Task 9: `UpdateDialog` component

**Files:**
- Create: `frontend/src/components/UpdateDialog.tsx`

- [ ] **Step 1: Implement the dialog**

Create `frontend/src/components/UpdateDialog.tsx` (mirrors `InstallEngineDialog`'s poll loop, adds release notes + a guard/notify-only state):

```tsx
import { useEffect, useRef, useState } from "react";
import { ExternalLink, Loader2, X } from "lucide-react";
import { focusRing } from "@/lib/theme";
import { getUpdateRunStatus, startUpdate } from "@/lib/api";
import type { UpdateInfo, UpdateRunStatus } from "@/types/models";

interface Props {
  isDark: boolean;
  info: UpdateInfo;
  onClose: () => void;
}

export function UpdateDialog({ isDark, info, onClose }: Props) {
  const [status, setStatus] = useState<UpdateRunStatus>({
    state: "idle",
    log: [],
    returncode: null,
    error: null,
  });
  const logRef = useRef<HTMLPreElement>(null);
  const timerRef = useRef<number | null>(null);

  const poll = async () => {
    try {
      const s = await getUpdateRunStatus();
      setStatus(s);
      if (s.state === "running") {
        timerRef.current = window.setTimeout(() => void poll(), 1000);
      }
    } catch (err) {
      setStatus((prev) => ({
        ...prev,
        state: "error",
        log: [...prev.log, err instanceof Error ? err.message : String(err)],
      }));
    }
  };

  const begin = async () => {
    setStatus({ state: "running", log: [], returncode: null, error: null });
    try {
      await startUpdate();
    } catch (err) {
      setStatus({
        state: "error",
        log: [err instanceof Error ? err.message : String(err)],
        returncode: -1,
        error: "failed to start update",
      });
      return;
    }
    void poll();
  };

  useEffect(() => {
    return () => {
      if (timerRef.current) window.clearTimeout(timerRef.current);
    };
  }, []);

  useEffect(() => {
    if (logRef.current) logRef.current.scrollTop = logRef.current.scrollHeight;
  }, [status.log]);

  const running = status.state === "running";
  const done = status.state === "done";
  const failed = status.state === "error";
  const idle = status.state === "idle";

  const panel = isDark ? "bg-zinc-900 border-zinc-800" : "bg-white border-gray-200";
  const muted = isDark ? "text-zinc-400" : "text-gray-600";

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/60 p-4">
      <div className={`w-full max-w-2xl rounded-xl border shadow-xl ${panel}`}>
        <div
          className={`flex items-center justify-between px-5 py-3 border-b ${
            isDark ? "border-zinc-800" : "border-gray-200"
          }`}
        >
          <div className="flex items-center gap-2">
            {running && <Loader2 className="w-4 h-4 animate-spin text-orange-400" />}
            <span className={`font-semibold ${isDark ? "text-white" : "text-gray-900"}`}>
              {running
                ? "Updating Voice Studio…"
                : done
                  ? "Update complete"
                  : failed
                    ? "Update failed"
                    : `Update to v${info.latest ?? "?"}`}
            </span>
          </div>
          <button
            type="button"
            onClick={onClose}
            disabled={running}
            className={`p-1 rounded ${
              running
                ? "opacity-40 cursor-not-allowed"
                : isDark
                  ? "hover:bg-zinc-800 text-zinc-400"
                  : "hover:bg-gray-100 text-gray-600"
            } ${focusRing}`}
          >
            <X className="w-5 h-5" />
          </button>
        </div>

        <div className="p-5 space-y-3">
          {idle && (
            <>
              <p className={`text-sm ${muted}`}>
                A new release is available. "Update now" runs
                {" "}<span className="font-mono text-xs">git pull</span>, reinstalls
                dependencies, and rebuilds the UI. You'll restart Voice Studio when it
                finishes.
              </p>
              {info.body && (
                <pre
                  className={`max-h-40 overflow-auto rounded-lg p-3 text-[11px] leading-relaxed whitespace-pre-wrap ${
                    isDark ? "bg-black/40 text-zinc-300" : "bg-gray-50 text-gray-700"
                  }`}
                >
                  {info.body}
                </pre>
              )}
            </>
          )}

          {!idle && (
            <>
              <p className={`text-sm ${muted}`}>
                {running
                  ? "Pulling the release, syncing dependencies, and rebuilding. This takes a few minutes."
                  : done
                    ? "Done. Restart Voice Studio (close this terminal/app and run it again) to load the new version."
                    : "The update failed. Review the log, then retry or update manually."}
              </p>
              <pre
                ref={logRef}
                className={`h-64 overflow-auto rounded-lg p-3 text-[11px] leading-relaxed font-mono whitespace-pre-wrap ${
                  isDark ? "bg-black/40 text-zinc-300" : "bg-gray-50 text-gray-700"
                }`}
              >
                {status.log.length ? status.log.join("\n") : "Starting…"}
              </pre>
            </>
          )}

          <div className="flex items-center justify-between gap-2">
            {info.html_url ? (
              <a
                href={info.html_url}
                target="_blank"
                rel="noopener noreferrer"
                className={`inline-flex items-center gap-1 text-xs underline decoration-dotted underline-offset-2 ${
                  isDark ? "text-zinc-400 hover:text-orange-400" : "text-gray-500 hover:text-orange-600"
                } ${focusRing}`}
              >
                Release notes on GitHub <ExternalLink className="w-3 h-3" />
              </a>
            ) : (
              <span />
            )}
            <div className="flex gap-2">
              {idle && (
                <button
                  type="button"
                  onClick={() => void begin()}
                  className={`px-4 py-2 rounded-lg text-sm font-medium bg-orange-600 hover:bg-orange-500 text-white ${focusRing}`}
                >
                  Update now
                </button>
              )}
              {failed && (
                <button
                  type="button"
                  onClick={() => void begin()}
                  className={`px-4 py-2 rounded-lg text-sm font-medium bg-orange-600 hover:bg-orange-500 text-white ${focusRing}`}
                >
                  Retry
                </button>
              )}
              <button
                type="button"
                onClick={onClose}
                disabled={running}
                className={`px-4 py-2 rounded-lg text-sm font-medium ${
                  running
                    ? "opacity-40 cursor-not-allowed bg-zinc-700 text-zinc-300"
                    : isDark
                      ? "bg-zinc-800 hover:bg-zinc-700 text-zinc-200"
                      : "bg-gray-100 hover:bg-gray-200 text-gray-700"
                } ${focusRing}`}
              >
                {done ? "Done" : "Close"}
              </button>
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}
```

- [ ] **Step 2: Typecheck**

Run (from `frontend/`): `npm run typecheck`
Expected: PASS.

- [ ] **Step 3: Commit**

```bash
git add frontend/src/components/UpdateDialog.tsx
git commit -m "feat(update): UpdateDialog (release notes + one-click apply + live log)"
```

---

## Task 10: ControlPanel "About" section

**Files:**
- Modify: `frontend/src/components/ControlPanel.tsx`

- [ ] **Step 1: Add imports**

In `frontend/src/components/ControlPanel.tsx`, add to the existing imports:

```typescript
import { useUpdate } from "@/hooks/useUpdate";
import { UpdateDialog } from "./UpdateDialog";
```

- [ ] **Step 2: Use the hook + local dialog state**

Inside the `ControlPanel` component body, near the existing `useCacheData()` call, add:

```typescript
  const { info: updateInfo, checking, check } = useUpdate();
  const [updateOpen, setUpdateOpen] = useState(false);
```

(`useState` is already imported in this file.)

- [ ] **Step 3: Render the About section**

In the scrollable body (`<div className="flex-1 overflow-y-auto p-3 space-y-4">`), add a new section as the LAST child, after the "Recent generations" section's closing `</section>`:

```tsx
        {/* About / version */}
        <section className="p-3 dark:bg-zinc-900 dark:border-zinc-800 bg-gray-100/80 border border-gray-200 rounded-lg">
          <h3 className={`text-xs font-semibold uppercase tracking-wide mb-2 ${heading}`}>
            About
          </h3>
          <div className="flex items-center justify-between gap-2">
            <span className={`text-sm ${isDark ? "text-zinc-200" : "text-gray-800"}`}>
              Voice Studio{updateInfo ? ` v${updateInfo.current}` : ""}
            </span>
            <button
              type="button"
              onClick={() => void check()}
              disabled={checking}
              className={`text-xs ${
                isDark ? "text-zinc-400 hover:text-orange-400" : "text-gray-500 hover:text-orange-600"
              } ${focusRing} ${checking ? "opacity-50 cursor-wait" : ""}`}
              title="Check for updates"
            >
              {checking ? "Checking…" : "Check for updates"}
            </button>
          </div>
          {updateInfo?.update_available && (
            <button
              type="button"
              onClick={() => setUpdateOpen(true)}
              className={`mt-2 w-full text-xs px-3 py-1.5 rounded-md font-medium transition-colors ${
                isDark
                  ? "bg-orange-700/40 hover:bg-orange-700/60 text-orange-200"
                  : "bg-orange-50 hover:bg-orange-100 text-orange-700"
              } ${focusRing}`}
            >
              {`Update to v${updateInfo.latest} available`}
            </button>
          )}
          {updateInfo && !updateInfo.update_available && !updateInfo.error && updateInfo.latest && (
            <p className={`mt-1 text-[11px] ${isDark ? "text-zinc-500" : "text-gray-500"}`}>
              You're on the latest version.
            </p>
          )}
        </section>
```

- [ ] **Step 4: Render the dialog**

Just before the final closing `</aside>` of the expanded panel, add:

```tsx
      {updateOpen && updateInfo && (
        <UpdateDialog isDark={isDark} info={updateInfo} onClose={() => setUpdateOpen(false)} />
      )}
```

- [ ] **Step 5: Typecheck + build**

Run (from `frontend/`): `npm run typecheck && npm run build`
Expected: both PASS.

- [ ] **Step 6: Commit**

```bash
git add frontend/src/components/ControlPanel.tsx
git commit -m "feat(update): ControlPanel About section + update badge/dialog"
```

---

## Task 11: Full verification gate

**Files:** none (verification only)

- [ ] **Step 1: Run the entire backend suite**

Run (from repo root): `./backend/venv/Scripts/python.exe -m pytest backend/tests/ -q`
Expected: all tests pass.

- [ ] **Step 2: Run the frontend typecheck + build**

Run (from `frontend/`): `npm run typecheck && npm run build`
Expected: both PASS; `dist/` rebuilt.

- [ ] **Step 3: If anything fails, fix and re-run before proceeding.** No commit if nothing changed.

---

## Task 12: Document the version/update system in CLAUDE.md

**Files:**
- Modify: `CLAUDE.md`

- [ ] **Step 1: Add a paragraph to the Architecture section**

In `CLAUDE.md`, add a bullet to the architecture list describing the system. Use this exact text:

```markdown
- **Versioning + auto-update.** The repo-root `VERSION` file is the single source of truth (`backend/core/version.py::get_version()`), surfaced via `/api/health` + `/api/config`. `services/update_check.py::UpdateChecker` compares it to the latest GitHub release (`GET /repos/msrbuilds/voice-studio/releases/latest`, cached, failure-tolerant; refreshed on startup via `refresh_async`). Applying an update reuses the engine-install pattern: `services/update_run.py::UpdateRunner` (a clone of `EngineEnvInstaller`) runs `studio.py update --tag <tag>` — which guards for a clean git checkout on the right remote, then `git checkout <tag>` + `pip install -r` + `npm run build` — and streams its log through `POST/GET /api/update`. The frontend `useUpdate` hook + ControlPanel "About" section + `UpdateDialog` drive it; non-git/dirty installs get a notify-only path (link to the release page). **Release process:** bump `VERSION`, sync `pyproject.toml`/`package.json`, commit, tag `vX.Y.Z`, publish the Release.
```

- [ ] **Step 2: Commit**

```bash
git add CLAUDE.md
git commit -m "docs: document versioning + auto-update in CLAUDE.md"
```

---

## Done

All tasks complete: single version source of truth, GitHub-release update detection, one-click apply mirroring the engine-install flow, and a notify-only fallback — fully tested (backend) and type-checked/built (frontend).
