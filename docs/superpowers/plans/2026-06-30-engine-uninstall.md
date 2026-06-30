# Engine Uninstall & Delete Weights Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Let users reclaim disk space from the frontend by deleting an engine's model weights (all 4 engines) and uninstalling the isolated venv (Chatterbox/OmniVoice), each with a live-progress dialog mirroring the existing Install/Download flows.

**Architecture:** Two new backend services (`ModelDeleter`, `EngineEnvUninstaller`) run `shutil.rmtree` on daemon threads with a thread-safe `idle → working → done | error` state machine, polled over four new endpoints on the existing `engines` router. The frontend adds two new dialogs (`DeleteWeightsDialog`, `UninstallEngineDialog`) and two secondary destructive buttons in `EngineSelector`, wired through `ControlPanel` → `App`. A Chatterbox `downloaded()` override is added so the UI can gate the delete button correctly.

**Tech Stack:** Python 3.11 + FastAPI + pytest (backend); React 18 + TypeScript + Vite + Tailwind v3 (frontend).

**Spec:** `docs/superpowers/specs/2026-06-29-engine-uninstall-design.md`

**Branch:** Implement on `feat/engine-uninstall`, not `main`.

**Commands:**
- Backend tests: `cd "f:/Vibe Projects/vibe-podcast" && python -m pytest backend/tests/<file> -v`
- Frontend gate: `cd "f:/Vibe Projects/vibe-podcast/frontend" && npm run typecheck && npm test && npm run build`

**Subagent git rule:** ONLY `git add` / `git commit`. NEVER checkout/switch/reset/rebase/stash/merge/push.

---

## File Structure

**New backend files:**
- `backend/services/model_delete.py` — `ModelDeleter` + `DELETABLE` + repo-dir resolver
- `backend/services/engine_uninstall.py` — `EngineEnvUninstaller` + `UNINSTALLABLE`
- `backend/tests/test_engine_uninstall.py` — unit + endpoint tests

**Modified backend files:**
- `backend/core/engines/chatterbox_engine.py` — add `downloaded()` override
- `backend/api/engines.py` — 2 status models + 4 endpoints
- `backend/api/deps.py` — 2 dependency providers
- `backend/app.py` — wire 2 new singletons

**New frontend files:**
- `frontend/src/components/DeleteWeightsDialog.tsx`
- `frontend/src/components/UninstallEngineDialog.tsx`

**Modified frontend files:**
- `frontend/src/types/models.ts` — 2 status interfaces
- `frontend/src/lib/api.ts` — 4 wrappers
- `frontend/src/components/EngineSelector.tsx` — 2 secondary buttons + 2 props
- `frontend/src/components/ControlPanel.tsx` — 2 props pass-through
- `frontend/src/App.tsx` — 2 state vars + 2 dialogs + callbacks

---

# PHASE 1 — Backend

## Task 1: Chatterbox `downloaded()` override

Without this, `ChatterboxEngine` inherits `Engine.downloaded() == True`, so the UI always thinks Chatterbox weights exist and can't gate the Delete-weights button. Mirror `OmniVoiceEngine.downloaded()` exactly.

**Files:**
- Modify: `backend/core/engines/chatterbox_engine.py`
- Test: `backend/tests/test_engine_uninstall.py` (created here, expanded in Task 4)

- [ ] **Step 1: Write the failing test**

Create `backend/tests/test_engine_uninstall.py`:
```python
"""Tests for engine uninstall / delete-weights services + Chatterbox downloaded()."""

import sys
import time
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT))


def test_chatterbox_downloaded_probes_cache(monkeypatch):
    from backend.core.engines import chatterbox_engine as ce

    eng = ce.ChatterboxEngine()
    # Patch the model_cache probe the override delegates to.
    import backend.core.model_cache as mc
    monkeypatch.setattr(mc, "model_downloaded", lambda repo_id: repo_id == "ResembleAI/chatterbox")
    assert eng.downloaded() is True

    monkeypatch.setattr(mc, "model_downloaded", lambda repo_id: False)
    assert eng.downloaded() is False
```

- [ ] **Step 2: Run the test to verify it fails**

Run: `cd "f:/Vibe Projects/vibe-podcast" && python -m pytest backend/tests/test_engine_uninstall.py::test_chatterbox_downloaded_probes_cache -v`
Expected: FAIL — `downloaded()` returns `True` for both (inherited base), so the second assertion fails.

- [ ] **Step 3: Add the override**

In `backend/core/engines/chatterbox_engine.py`, immediately after the `_ready_marker` method (around line 168, before `engine_info`), add:
```python
    def downloaded(self) -> bool:
        # Chatterbox weights live in the shared HF cache (backend/models/), which
        # both the main process and the isolated worker read. Probe it so the UI
        # can gate the Delete-weights button. Mirrors OmniVoiceEngine.downloaded().
        from ..model_cache import model_downloaded

        return model_downloaded(self._model_id)
```

- [ ] **Step 4: Run the test to verify it passes**

Run: `cd "f:/Vibe Projects/vibe-podcast" && python -m pytest backend/tests/test_engine_uninstall.py::test_chatterbox_downloaded_probes_cache -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add backend/core/engines/chatterbox_engine.py backend/tests/test_engine_uninstall.py
git commit -m "feat(chatterbox): downloaded() probes HF cache so UI can gate delete-weights"
```

---

## Task 2: `ModelDeleter` service (TDD)

Deletes the HF-cache snapshot dir for an engine's weights on a daemon thread. State machine: `idle → deleting → deleted | error`. Unloads the engine first to release file handles. All dependencies (engine manager, dir resolver, remover) are injectable so tests never touch HF or the filesystem.

**Files:**
- Create: `backend/services/model_delete.py`
- Test: `backend/tests/test_engine_uninstall.py`

- [ ] **Step 1: Write the failing tests**

Append to `backend/tests/test_engine_uninstall.py`:
```python
# ---------------------------------------------------------------------------
# ModelDeleter
# ---------------------------------------------------------------------------

def _wait_deleter(d, timeout=5.0):
    deadline = time.time() + timeout
    while time.time() < deadline and d.status()["state"] == "deleting":
        time.sleep(0.02)


def test_model_deleter_initial_idle():
    from backend.services.model_delete import ModelDeleter
    d = ModelDeleter(em=None, repo_dir_resolver=lambda r: None, remover=lambda p: None)
    assert d.status()["state"] == "idle"


def test_model_deleter_deletes_existing_dir(tmp_path):
    from backend.services.model_delete import ModelDeleter
    target = tmp_path / "models--vibevoice--VibeVoice-1.5B"
    target.mkdir()
    removed = []
    d = ModelDeleter(
        em=None,
        repo_dir_resolver=lambda repo_id: target,
        remover=lambda p: removed.append(p),
    )
    d.start("vibevoice")
    _wait_deleter(d)
    s = d.status()
    assert s["state"] == "deleted"
    assert removed == [target]
    assert s["error"] is None


def test_model_deleter_missing_dir_is_idempotent():
    from backend.services.model_delete import ModelDeleter
    removed = []
    d = ModelDeleter(
        em=None,
        repo_dir_resolver=lambda repo_id: None,  # not cached
        remover=lambda p: removed.append(p),
    )
    d.start("kokoro")
    _wait_deleter(d)
    assert d.status()["state"] == "deleted"
    assert removed == []  # nothing to remove


def test_model_deleter_error_state():
    from backend.services.model_delete import ModelDeleter

    def boom(p):
        raise OSError("permission denied")

    d = ModelDeleter(
        em=None,
        repo_dir_resolver=lambda repo_id: Path("/fake/dir"),
        remover=boom,
    )
    d.start("omnivoice")
    _wait_deleter(d)
    s = d.status()
    assert s["state"] == "error"
    assert "permission denied" in (s["error"] or "")


def test_model_deleter_rejects_unknown_engine():
    from backend.services.model_delete import ModelDeleter
    import pytest
    d = ModelDeleter(em=None, repo_dir_resolver=lambda r: None, remover=lambda p: None)
    with pytest.raises(ValueError):
        d.start("not-an-engine")


def test_model_deleter_unloads_loaded_engine():
    from backend.services.model_delete import ModelDeleter

    class FakeEngine:
        def __init__(self):
            self.unloaded = False
        def is_loaded(self):
            return True
        def unload(self):
            self.unloaded = True

    fake = FakeEngine()

    class FakeEM:
        def get_engine(self, name):
            return fake

    d = ModelDeleter(
        em=FakeEM(),
        repo_dir_resolver=lambda r: None,
        remover=lambda p: None,
    )
    d.start("vibevoice")
    _wait_deleter(d)
    assert fake.unloaded is True
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `cd "f:/Vibe Projects/vibe-podcast" && python -m pytest backend/tests/test_engine_uninstall.py -k model_deleter -v`
Expected: FAIL — `No module named 'backend.services.model_delete'`.

- [ ] **Step 3: Implement `ModelDeleter`**

Create `backend/services/model_delete.py`:
```python
"""Delete an engine's model weights from the local HF cache, with progress.

Runs `shutil.rmtree` on a daemon thread (large dirs take a moment). State
machine: idle -> deleting -> deleted | error. The engine is unloaded first
to release file handles (on Windows you cannot remove files held open by a
loaded model / running worker). All side-effecting collaborators are
injectable so tests never touch HF or the real filesystem.
"""

from __future__ import annotations

import shutil
import threading
from pathlib import Path
from typing import Callable, Optional

from backend.scripts.download_models import MODEL_CATALOG

#: Every engine has weights in the shared HF cache and can have them deleted.
#: (Superset of model_download.DOWNLOADABLE — chatterbox's weights arrive via
#: its worker's install but still land in the shared cache.)
DELETABLE: frozenset[str] = frozenset({"vibevoice", "kokoro", "omnivoice", "chatterbox"})

_MAX_LOG_LINES = 500

# (repo_id) -> the `models--org--repo` dir in the HF cache, or None if absent.
RepoDirResolver = Callable[[str], Optional[Path]]
# (Path) -> None; deletes the directory tree.
Remover = Callable[[Path], None]


def _default_repo_dir(repo_id: str) -> Optional[Path]:
    """Locate the repo's cache dir robustly via the snapshot resolver."""
    try:
        from huggingface_hub import snapshot_download

        snap = Path(snapshot_download(repo_id, local_files_only=True))
        return snap.parent.parent  # snapshots/<rev> -> snapshots -> repo root
    except Exception:  # noqa: BLE001 — not cached, or partial
        try:
            from huggingface_hub.constants import HF_HUB_CACHE

            cand = Path(HF_HUB_CACHE) / f"models--{repo_id.replace('/', '--')}"
            return cand if cand.exists() else None
        except Exception:  # noqa: BLE001
            return None


class ModelDeleter:
    """Thread-safe, single-flight model-weight deletion with a status snapshot."""

    def __init__(
        self,
        *,
        em=None,
        repo_dir_resolver: RepoDirResolver | None = None,
        remover: Remover | None = None,
    ) -> None:
        self._em = em
        self._resolve = repo_dir_resolver or _default_repo_dir
        self._remove = remover or shutil.rmtree
        self._lock = threading.Lock()
        self._state = "idle"
        self._log: list[str] = []
        self._error: str | None = None
        self._thread: threading.Thread | None = None

    def status(self) -> dict:
        with self._lock:
            return {"state": self._state, "log": list(self._log), "error": self._error}

    def start(self, engine_name: str) -> dict:
        if engine_name not in DELETABLE:
            raise ValueError(f"{engine_name} weights are not deletable")
        with self._lock:
            if self._state == "deleting":
                return {"state": self._state, "log": list(self._log), "error": self._error}
            self._state = "deleting"
            self._log = []
            self._error = None
            self._thread = threading.Thread(target=self._run, args=(engine_name,), daemon=True)
            self._thread.start()
            return {"state": self._state, "log": [], "error": None}

    def _append(self, line: str) -> None:
        with self._lock:
            self._log.append(line)
            if len(self._log) > _MAX_LOG_LINES:
                del self._log[: len(self._log) - _MAX_LOG_LINES]

    def _run(self, engine_name: str) -> None:
        try:
            repo_id = MODEL_CATALOG[engine_name]["repo_id"]
            if self._em is not None:
                engine = self._em.get_engine(engine_name)
                if engine.is_loaded():
                    self._append(f"Unloading {engine_name} to release file handles…")
                    engine.unload()
            target = self._resolve(repo_id)
            if target is None or not Path(target).exists():
                self._append("No cached weights found — nothing to delete.")
            else:
                self._append(f"Deleting weights at {target} …")
                self._remove(Path(target))
                self._append("Done. Disk space reclaimed.")
            with self._lock:
                self._state = "deleted"
        except Exception as exc:  # noqa: BLE001
            with self._lock:
                self._error = str(exc)
                self._log.append(f"[delete error] {exc}")
                self._state = "error"
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `cd "f:/Vibe Projects/vibe-podcast" && python -m pytest backend/tests/test_engine_uninstall.py -k model_deleter -v`
Expected: PASS (6 tests).

- [ ] **Step 5: Commit**

```bash
git add backend/services/model_delete.py backend/tests/test_engine_uninstall.py
git commit -m "feat(backend): ModelDeleter service for freeing model weights"
```

---

## Task 3: `EngineEnvUninstaller` service (TDD)

Removes the isolated venv directory for Chatterbox/OmniVoice (the `.{engine}-ready` marker lives inside, so it's removed too). Unloads the worker first (Windows can't `rmtree` a dir with a running `python.exe`). State machine: `idle → uninstalling → uninstalled | error`. A retrying remover handles transient Windows file locks.

**Files:**
- Create: `backend/services/engine_uninstall.py`
- Test: `backend/tests/test_engine_uninstall.py`

- [ ] **Step 1: Write the failing tests**

Append to `backend/tests/test_engine_uninstall.py`:
```python
# ---------------------------------------------------------------------------
# EngineEnvUninstaller
# ---------------------------------------------------------------------------

def _wait_uninstaller(u, timeout=5.0):
    deadline = time.time() + timeout
    while time.time() < deadline and u.status()["state"] == "uninstalling":
        time.sleep(0.02)


def test_uninstaller_initial_idle():
    from backend.services.engine_uninstall import EngineEnvUninstaller
    u = EngineEnvUninstaller("chatterbox", em=None, venv_dir=Path("/nope"), remover=lambda p: None)
    assert u.status()["state"] == "idle"


def test_uninstaller_removes_existing_venv(tmp_path):
    from backend.services.engine_uninstall import EngineEnvUninstaller
    venv = tmp_path / "venv-chatterbox"
    venv.mkdir()
    removed = []
    u = EngineEnvUninstaller(
        "chatterbox", em=None, venv_dir=venv, remover=lambda p: removed.append(p)
    )
    u.start()
    _wait_uninstaller(u)
    s = u.status()
    assert s["state"] == "uninstalled"
    assert removed == [venv]


def test_uninstaller_missing_venv_is_idempotent(tmp_path):
    from backend.services.engine_uninstall import EngineEnvUninstaller
    removed = []
    u = EngineEnvUninstaller(
        "omnivoice", em=None, venv_dir=tmp_path / "absent", remover=lambda p: removed.append(p)
    )
    u.start()
    _wait_uninstaller(u)
    assert u.status()["state"] == "uninstalled"
    assert removed == []


def test_uninstaller_error_state(tmp_path):
    from backend.services.engine_uninstall import EngineEnvUninstaller
    venv = tmp_path / "venv-chatterbox"
    venv.mkdir()

    def boom(p):
        raise OSError("file in use")

    u = EngineEnvUninstaller("chatterbox", em=None, venv_dir=venv, remover=boom)
    u.start()
    _wait_uninstaller(u)
    s = u.status()
    assert s["state"] == "error"
    assert "file in use" in (s["error"] or "")


def test_uninstaller_unloads_loaded_engine(tmp_path):
    from backend.services.engine_uninstall import EngineEnvUninstaller

    class FakeEngine:
        def __init__(self):
            self.unloaded = False
        def is_loaded(self):
            return True
        def unload(self):
            self.unloaded = True

    fake = FakeEngine()

    class FakeEM:
        def get_engine(self, name):
            return fake

    venv = tmp_path / "venv-chatterbox"
    venv.mkdir()
    u = EngineEnvUninstaller("chatterbox", em=FakeEM(), venv_dir=venv, remover=lambda p: None)
    u.start()
    _wait_uninstaller(u)
    assert fake.unloaded is True
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `cd "f:/Vibe Projects/vibe-podcast" && python -m pytest backend/tests/test_engine_uninstall.py -k uninstaller -v`
Expected: FAIL — `No module named 'backend.services.engine_uninstall'`.

- [ ] **Step 3: Implement `EngineEnvUninstaller`**

Create `backend/services/engine_uninstall.py`:
```python
"""Remove an isolated engine venv (Chatterbox/OmniVoice), with progress.

Runs `shutil.rmtree` on a daemon thread. State machine:
    idle -> uninstalling -> uninstalled | error

The `.{engine}-ready` marker lives INSIDE the venv dir, so removing the dir
removes the marker too — `engine.installed()` then reports False. The worker
subprocess is unloaded first: on Windows a running venv python.exe holds a
file lock that blocks rmtree, so a retrying remover smooths over the brief
window between unload() and the OS releasing the handle.
"""

from __future__ import annotations

import shutil
import threading
import time
from pathlib import Path
from typing import Callable

_BACKEND_ROOT = Path(__file__).resolve().parents[1]  # backend/services/.. -> backend/

#: Only these two engines have an isolated venv to remove.
UNINSTALLABLE: frozenset[str] = frozenset({"chatterbox", "omnivoice"})

_MAX_LOG_LINES = 500

Remover = Callable[[Path], None]


def _rmtree_with_retry(path: Path, *, attempts: int = 5, delay: float = 0.4) -> None:
    """rmtree, retrying transient Windows file locks after worker shutdown."""
    last: Exception | None = None
    for _ in range(attempts):
        try:
            shutil.rmtree(path)
            return
        except FileNotFoundError:
            return
        except (PermissionError, OSError) as exc:  # noqa: PERF203
            last = exc
            time.sleep(delay)
    if last is not None:
        raise last


class EngineEnvUninstaller:
    """Thread-safe removal of one engine's isolated venv directory."""

    def __init__(
        self,
        engine_name: str,
        *,
        em=None,
        venv_dir: Path | None = None,
        remover: Remover | None = None,
    ) -> None:
        self._engine_name = engine_name
        self._em = em
        self._venv_dir = Path(venv_dir) if venv_dir else _BACKEND_ROOT / f"venv-{engine_name}"
        self._remove = remover or _rmtree_with_retry
        self._lock = threading.Lock()
        self._state = "idle"
        self._log: list[str] = []
        self._error: str | None = None
        self._thread: threading.Thread | None = None

    def status(self) -> dict:
        with self._lock:
            return {"state": self._state, "log": list(self._log), "error": self._error}

    def start(self) -> dict:
        with self._lock:
            if self._state == "uninstalling":
                return {"state": self._state, "log": list(self._log), "error": self._error}
            self._state = "uninstalling"
            self._log = []
            self._error = None
            self._thread = threading.Thread(target=self._run, daemon=True)
            self._thread.start()
            return {"state": self._state, "log": [], "error": None}

    def _append(self, line: str) -> None:
        with self._lock:
            self._log.append(line)
            if len(self._log) > _MAX_LOG_LINES:
                del self._log[: len(self._log) - _MAX_LOG_LINES]

    def _run(self) -> None:
        try:
            if self._em is not None:
                engine = self._em.get_engine(self._engine_name)
                if engine.is_loaded():
                    self._append(f"Stopping the {self._engine_name} worker…")
                    engine.unload()
            if not self._venv_dir.exists():
                self._append("Environment already removed — nothing to do.")
            else:
                self._append(f"Removing {self._venv_dir} (this can take a few seconds)…")
                self._remove(self._venv_dir)
                self._append("Done. Environment removed.")
            with self._lock:
                self._state = "uninstalled"
        except Exception as exc:  # noqa: BLE001
            with self._lock:
                self._error = str(exc)
                self._log.append(f"[uninstall error] {exc}")
                self._state = "error"
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `cd "f:/Vibe Projects/vibe-podcast" && python -m pytest backend/tests/test_engine_uninstall.py -k uninstaller -v`
Expected: PASS (5 tests).

- [ ] **Step 5: Commit**

```bash
git add backend/services/engine_uninstall.py backend/tests/test_engine_uninstall.py
git commit -m "feat(backend): EngineEnvUninstaller for removing isolated engine venvs"
```

---

## Task 4: API endpoints + deps + app wiring (TDD on endpoints)

**Files:**
- Modify: `backend/api/deps.py`
- Modify: `backend/api/engines.py`
- Modify: `backend/app.py`
- Test: `backend/tests/test_engine_uninstall.py`

- [ ] **Step 1: Write the failing endpoint tests**

Append to `backend/tests/test_engine_uninstall.py`:
```python
# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------

def _make_app(deleter=None, uninstallers=None):
    from fastapi import FastAPI
    from backend.api.engines import router
    app = FastAPI()
    app.include_router(router)
    if deleter is not None:
        app.state.model_deleter = deleter
    if uninstallers is not None:
        app.state.engine_uninstallers = uninstallers
    return app


def test_delete_weights_endpoints():
    from fastapi.testclient import TestClient
    from backend.services.model_delete import ModelDeleter
    d = ModelDeleter(em=None, repo_dir_resolver=lambda r: None, remover=lambda p: None)
    client = TestClient(_make_app(deleter=d))

    assert client.get("/api/engines/vibevoice/delete-weights").json()["state"] == "idle"
    r = client.post("/api/engines/vibevoice/delete-weights")
    assert r.status_code == 200
    _wait_deleter(d)
    assert client.get("/api/engines/vibevoice/delete-weights").json()["state"] == "deleted"


def test_delete_weights_rejects_unknown_engine():
    from fastapi.testclient import TestClient
    from backend.services.model_delete import ModelDeleter
    d = ModelDeleter(em=None, repo_dir_resolver=lambda r: None, remover=lambda p: None)
    client = TestClient(_make_app(deleter=d))
    assert client.get("/api/engines/bogus/delete-weights").status_code == 400
    assert client.post("/api/engines/bogus/delete-weights").status_code == 400


def test_uninstall_endpoints(tmp_path):
    from fastapi.testclient import TestClient
    from backend.services.engine_uninstall import EngineEnvUninstaller
    venv = tmp_path / "venv-chatterbox"
    venv.mkdir()
    u = EngineEnvUninstaller("chatterbox", em=None, venv_dir=venv, remover=lambda p: None)
    client = TestClient(_make_app(uninstallers={"chatterbox": u}))

    assert client.get("/api/engines/chatterbox/uninstall").json()["state"] == "idle"
    assert client.post("/api/engines/chatterbox/uninstall").status_code == 200
    _wait_uninstaller(u)
    assert client.get("/api/engines/chatterbox/uninstall").json()["state"] == "uninstalled"


def test_uninstall_rejects_non_isolated_engine(tmp_path):
    from fastapi.testclient import TestClient
    from backend.services.engine_uninstall import EngineEnvUninstaller
    u = EngineEnvUninstaller("chatterbox", em=None, venv_dir=tmp_path / "v", remover=lambda p: None)
    client = TestClient(_make_app(uninstallers={"chatterbox": u}))
    # vibevoice has no isolated env → 400
    assert client.get("/api/engines/vibevoice/uninstall").status_code == 400
    assert client.post("/api/engines/vibevoice/uninstall").status_code == 400
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `cd "f:/Vibe Projects/vibe-podcast" && python -m pytest backend/tests/test_engine_uninstall.py -k "delete_weights or uninstall_endpoints or non_isolated" -v`
Expected: FAIL — endpoints return 404/405 (routes don't exist yet).

- [ ] **Step 3: Add dependency providers**

In `backend/api/deps.py`, after `get_model_downloader` (line 28), add:
```python
def get_model_deleter(request: Request):
    return request.app.state.model_deleter  # type: ignore[no-any-return]


def get_engine_uninstallers(request: Request) -> dict:
    return request.app.state.engine_uninstallers  # type: ignore[no-any-return]
```

- [ ] **Step 4: Add status models + endpoints to `engines.py`**

In `backend/api/engines.py`, update the imports near the top:
```python
from ..services.model_download import DOWNLOADABLE as _DOWNLOADABLE
from ..services.model_delete import DELETABLE as _DELETABLE
from .deps import (
    get_engine_installers,
    get_engine_manager,
    get_engine_uninstallers,
    get_model_deleter,
    get_model_downloader,
)
```

Add two status models after `DownloadStatusModel` (around line 62):
```python
class DeleteWeightsStatusModel(BaseModel):
    state: str  # idle | deleting | deleted | error
    log: list[str]
    error: str | None


class UninstallStatusModel(BaseModel):
    state: str  # idle | uninstalling | uninstalled | error
    log: list[str]
    error: str | None
```

Add four endpoints at the end of the file (after `start_download`):
```python
@router.get("/{name}/delete-weights", response_model=DeleteWeightsStatusModel)
def delete_weights_status(name: str, deleter=Depends(get_model_deleter)) -> DeleteWeightsStatusModel:
    """Current weight-deletion state."""
    if name not in _DELETABLE:
        raise HTTPException(status_code=400, detail=f"{name} weights are not deletable")
    return DeleteWeightsStatusModel(**deleter.status())


@router.post("/{name}/delete-weights", response_model=DeleteWeightsStatusModel)
def start_delete_weights(name: str, deleter=Depends(get_model_deleter)) -> DeleteWeightsStatusModel:
    """Start (or coalesce onto a running) weight deletion."""
    if name not in _DELETABLE:
        raise HTTPException(status_code=400, detail=f"{name} weights are not deletable")
    try:
        return DeleteWeightsStatusModel(**deleter.start(name))
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))


@router.get("/{name}/uninstall", response_model=UninstallStatusModel)
def uninstall_status(name: str, uninstallers=Depends(get_engine_uninstallers)) -> UninstallStatusModel:
    """Current env-removal state for an isolated engine (Chatterbox / OmniVoice)."""
    u = uninstallers.get(name)
    if u is None:
        raise HTTPException(status_code=400, detail=f"{name} has no isolated environment to uninstall")
    return UninstallStatusModel(**u.status())


@router.post("/{name}/uninstall", response_model=UninstallStatusModel)
def start_uninstall(name: str, uninstallers=Depends(get_engine_uninstallers)) -> UninstallStatusModel:
    """Start (or coalesce onto a running) removal of an isolated engine env."""
    u = uninstallers.get(name)
    if u is None:
        raise HTTPException(status_code=400, detail=f"{name} has no isolated environment to uninstall")
    return UninstallStatusModel(**u.start())
```

- [ ] **Step 5: Wire the singletons in `app.py`**

In `backend/app.py`, update the imports (near line 41-42):
```python
from .services.chatterbox_install import ChatterboxInstaller, EngineEnvInstaller
from .services.model_download import ModelDownloader
from .services.model_delete import ModelDeleter
from .services.engine_uninstall import EngineEnvUninstaller
```

After `app.state.model_downloader = ModelDownloader()` (line 210), add:
```python
    app.state.model_deleter = ModelDeleter(em=engine_manager)
    app.state.engine_uninstallers = {
        "chatterbox": EngineEnvUninstaller("chatterbox", em=engine_manager),
        "omnivoice": EngineEnvUninstaller("omnivoice", em=engine_manager),
    }
```

- [ ] **Step 6: Run the endpoint tests + full file**

Run: `cd "f:/Vibe Projects/vibe-podcast" && python -m pytest backend/tests/test_engine_uninstall.py -v`
Expected: PASS (all tasks 1-4 tests green).

- [ ] **Step 7: Run the whole backend suite (no regressions)**

Run: `cd "f:/Vibe Projects/vibe-podcast" && python -m pytest backend/tests/ -q`
Expected: all pass.

- [ ] **Step 8: Commit**

```bash
git add backend/api/deps.py backend/api/engines.py backend/app.py backend/tests/test_engine_uninstall.py
git commit -m "feat(api): delete-weights + uninstall endpoints, deps, and app wiring"
```

---

# PHASE 2 — Frontend

## Task 5: API types + wrappers

**Files:**
- Modify: `frontend/src/types/models.ts`
- Modify: `frontend/src/lib/api.ts`

- [ ] **Step 1: Add the status interfaces**

In `frontend/src/types/models.ts`, after the `DownloadStatus` interface (line 88), add:
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
```

- [ ] **Step 2: Add the API wrappers**

In `frontend/src/lib/api.ts`, after `getModelDownloadStatus` (around line 176), add:
```ts
export async function startDeleteWeights(name: string): Promise<DeleteWeightsStatus> {
  return jsonOrThrow<DeleteWeightsStatus>(
    await fetch(`${API_BASE}/engines/${encodeURIComponent(name)}/delete-weights`, {
      method: "POST",
    }),
  );
}

export async function getDeleteWeightsStatus(name: string): Promise<DeleteWeightsStatus> {
  return jsonOrThrow<DeleteWeightsStatus>(
    await fetch(`${API_BASE}/engines/${encodeURIComponent(name)}/delete-weights`),
  );
}

export async function startUninstallEngine(name: string): Promise<UninstallStatus> {
  return jsonOrThrow<UninstallStatus>(
    await fetch(`${API_BASE}/engines/${encodeURIComponent(name)}/uninstall`, {
      method: "POST",
    }),
  );
}

export async function getUninstallStatus(name: string): Promise<UninstallStatus> {
  return jsonOrThrow<UninstallStatus>(
    await fetch(`${API_BASE}/engines/${encodeURIComponent(name)}/uninstall`),
  );
}
```

Add the two new types to the existing `@/types/models` import block at the top of `api.ts` (it already imports `DownloadStatus`, `EngineInfo`, `InstallStatus`, etc. — add `DeleteWeightsStatus` and `UninstallStatus` to that list).

- [ ] **Step 3: Typecheck**

Run: `cd "f:/Vibe Projects/vibe-podcast/frontend" && npm run typecheck`
Expected: PASS.

- [ ] **Step 4: Commit**

```bash
git add frontend/src/types/models.ts frontend/src/lib/api.ts
git commit -m "feat(frontend): API types + wrappers for delete-weights and uninstall"
```

---

## Task 6: `DeleteWeightsDialog` component

Mirrors `DownloadModelDialog` but for deletion: a confirmation step (destructive, requires explicit click), then a streaming log polled until `deleted | error`. No percent/bytes bar (deletion has no byte progress). Danger-red confirm button.

**Files:**
- Create: `frontend/src/components/DeleteWeightsDialog.tsx`

- [ ] **Step 1: Create the component**

Create `frontend/src/components/DeleteWeightsDialog.tsx`:
```tsx
import { useEffect, useRef, useState } from "react";
import { Loader2, Trash2, X } from "lucide-react";
import { focusRing } from "@/lib/theme";
import { getDeleteWeightsStatus, startDeleteWeights } from "@/lib/api";
import type { DeleteWeightsStatus } from "@/types/models";

interface Props {
  isDark: boolean;
  engineName: string;
  displayName: string;
  onClose: () => void;
  onDone: () => void;
}

// Mirrors the catalog sizes in backend/scripts/download_models.py (all 4 engines).
const MODEL_SIZES: Record<string, string> = {
  vibevoice: "~5.4 GB",
  kokoro: "~350 MB",
  chatterbox: "~500 MB",
  omnivoice: "~3.3 GB",
};

export function DeleteWeightsDialog({
  isDark,
  engineName,
  displayName,
  onClose,
  onDone,
}: Props) {
  const [started, setStarted] = useState(false);
  const [status, setStatus] = useState<DeleteWeightsStatus>({
    state: "idle",
    log: [],
    error: null,
  });
  const logRef = useRef<HTMLPreElement>(null);
  const timerRef = useRef<number | null>(null);
  const sizeLabel = MODEL_SIZES[engineName] ?? "";

  const poll = async () => {
    try {
      const s = await getDeleteWeightsStatus(engineName);
      setStatus(s);
      if (s.state === "deleting") {
        timerRef.current = window.setTimeout(() => void poll(), 800);
      } else if (s.state === "deleted") {
        onDone();
      }
    } catch (err) {
      setStatus((prev) => ({
        ...prev,
        state: "error",
        error: err instanceof Error ? err.message : String(err),
        log: [...prev.log, err instanceof Error ? err.message : String(err)],
      }));
    }
  };

  const begin = async () => {
    setStarted(true);
    setStatus({ state: "deleting", log: [], error: null });
    try {
      await startDeleteWeights(engineName);
    } catch (err) {
      setStatus({
        state: "error",
        log: [err instanceof Error ? err.message : String(err)],
        error: err instanceof Error ? err.message : String(err),
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

  const deleting = status.state === "deleting";
  const failed = status.state === "error";

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/60 p-4">
      <div
        className={`w-full max-w-2xl rounded-xl border shadow-xl ${
          isDark ? "bg-zinc-900 border-zinc-800" : "bg-white border-gray-200"
        }`}
      >
        <div
          className={`flex items-center justify-between px-5 py-3 border-b ${
            isDark ? "border-zinc-800" : "border-gray-200"
          }`}
        >
          <div className="flex items-center gap-2">
            {deleting ? (
              <Loader2 className="w-4 h-4 animate-spin text-red-400" />
            ) : (
              <Trash2 className="w-4 h-4 text-red-400" />
            )}
            <span className={`font-semibold ${isDark ? "text-white" : "text-gray-900"}`}>
              {deleting
                ? `Deleting ${displayName} weights…`
                : failed
                  ? `${displayName} delete failed`
                  : `Delete ${displayName} weights`}
            </span>
          </div>
          <button
            type="button"
            onClick={onClose}
            disabled={deleting}
            className={`p-1 rounded ${
              deleting
                ? "opacity-40 cursor-not-allowed"
                : isDark
                  ? "hover:bg-zinc-800 text-zinc-400"
                  : "hover:bg-gray-100 text-gray-600"
            } ${focusRing}`}
          >
            <X className="w-5 h-5" />
          </button>
        </div>

        <div className="p-5 space-y-4">
          {!started ? (
            <p className={`text-sm ${isDark ? "text-zinc-300" : "text-gray-700"}`}>
              This permanently deletes {displayName}'s cached model weights
              ({sizeLabel}) from disk. You can re-download them later from the
              engine menu. Continue?
            </p>
          ) : (
            <pre
              ref={logRef}
              className={`h-48 overflow-auto rounded-lg p-3 text-[11px] leading-relaxed font-mono whitespace-pre-wrap ${
                isDark ? "bg-black/40 text-zinc-300" : "bg-gray-50 text-gray-700"
              }`}
            >
              {status.log.length ? status.log.join("\n") : "Starting…"}
            </pre>
          )}

          <div className="flex justify-end gap-2">
            {!started && (
              <button
                type="button"
                onClick={() => void begin()}
                className={`px-4 py-2 rounded-lg text-sm font-medium bg-red-600 hover:bg-red-500 text-white ${focusRing}`}
              >
                {`Delete weights (${sizeLabel})`}
              </button>
            )}
            {failed && (
              <button
                type="button"
                onClick={() => void begin()}
                className={`px-4 py-2 rounded-lg text-sm font-medium bg-red-600 hover:bg-red-500 text-white ${focusRing}`}
              >
                Retry
              </button>
            )}
            <button
              type="button"
              onClick={onClose}
              disabled={deleting}
              className={`px-4 py-2 rounded-lg text-sm font-medium ${
                deleting
                  ? "opacity-40 cursor-not-allowed bg-zinc-700 text-zinc-300"
                  : isDark
                    ? "bg-zinc-800 hover:bg-zinc-700 text-zinc-200"
                    : "bg-gray-100 hover:bg-gray-200 text-gray-700"
              } ${focusRing}`}
            >
              {started ? "Close" : "Cancel"}
            </button>
          </div>
        </div>
      </div>
    </div>
  );
}
```

- [ ] **Step 2: Typecheck**

Run: `cd "f:/Vibe Projects/vibe-podcast/frontend" && npm run typecheck`
Expected: PASS.

- [ ] **Step 3: Commit**

```bash
git add frontend/src/components/DeleteWeightsDialog.tsx
git commit -m "feat(frontend): DeleteWeightsDialog with confirm + progress log"
```

---

## Task 7: `UninstallEngineDialog` component

Mirrors `InstallEngineDialog` but destructive: requires a confirm click (does NOT auto-start on mount), streams the removal log until `uninstalled | error`. Danger-red confirm button.

**Files:**
- Create: `frontend/src/components/UninstallEngineDialog.tsx`

- [ ] **Step 1: Create the component**

Create `frontend/src/components/UninstallEngineDialog.tsx`:
```tsx
import { useEffect, useRef, useState } from "react";
import { Loader2, Trash2, X } from "lucide-react";
import { focusRing } from "@/lib/theme";
import { getUninstallStatus, startUninstallEngine } from "@/lib/api";
import type { UninstallStatus } from "@/types/models";

interface Props {
  isDark: boolean;
  engineName: string;
  displayName: string;
  onClose: () => void;
  onUninstalled: () => void;
}

export function UninstallEngineDialog({
  isDark,
  engineName,
  displayName,
  onClose,
  onUninstalled,
}: Props) {
  const [started, setStarted] = useState(false);
  const [status, setStatus] = useState<UninstallStatus>({
    state: "idle",
    log: [],
    error: null,
  });
  const logRef = useRef<HTMLPreElement>(null);
  const timerRef = useRef<number | null>(null);

  const poll = async () => {
    try {
      const s = await getUninstallStatus(engineName);
      setStatus(s);
      if (s.state === "uninstalling") {
        timerRef.current = window.setTimeout(() => void poll(), 800);
      } else if (s.state === "uninstalled") {
        onUninstalled();
      }
    } catch (err) {
      setStatus((prev) => ({
        ...prev,
        state: "error",
        error: err instanceof Error ? err.message : String(err),
        log: [...prev.log, err instanceof Error ? err.message : String(err)],
      }));
    }
  };

  const begin = async () => {
    setStarted(true);
    setStatus({ state: "uninstalling", log: [], error: null });
    try {
      await startUninstallEngine(engineName);
    } catch (err) {
      setStatus({
        state: "error",
        log: [err instanceof Error ? err.message : String(err)],
        error: err instanceof Error ? err.message : String(err),
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

  const uninstalling = status.state === "uninstalling";
  const failed = status.state === "error";

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/60 p-4">
      <div
        className={`w-full max-w-2xl rounded-xl border shadow-xl ${
          isDark ? "bg-zinc-900 border-zinc-800" : "bg-white border-gray-200"
        }`}
      >
        <div
          className={`flex items-center justify-between px-5 py-3 border-b ${
            isDark ? "border-zinc-800" : "border-gray-200"
          }`}
        >
          <div className="flex items-center gap-2">
            {uninstalling ? (
              <Loader2 className="w-4 h-4 animate-spin text-red-400" />
            ) : (
              <Trash2 className="w-4 h-4 text-red-400" />
            )}
            <span className={`font-semibold ${isDark ? "text-white" : "text-gray-900"}`}>
              {uninstalling
                ? `Uninstalling ${displayName}…`
                : failed
                  ? `${displayName} uninstall failed`
                  : `Uninstall ${displayName} environment`}
            </span>
          </div>
          <button
            type="button"
            onClick={onClose}
            disabled={uninstalling}
            className={`p-1 rounded ${
              uninstalling
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
          {!started ? (
            <p className={`text-sm ${isDark ? "text-zinc-300" : "text-gray-700"}`}>
              This removes {displayName}'s isolated environment (its dedicated
              Python venv and packages) to free disk space. The model weights are
              not touched. You can reinstall it later from the engine menu. Continue?
            </p>
          ) : (
            <pre
              ref={logRef}
              className={`h-48 overflow-auto rounded-lg p-3 text-[11px] leading-relaxed font-mono whitespace-pre-wrap ${
                isDark ? "bg-black/40 text-zinc-300" : "bg-gray-50 text-gray-700"
              }`}
            >
              {status.log.length ? status.log.join("\n") : "Starting…"}
            </pre>
          )}

          <div className="flex justify-end gap-2">
            {!started && (
              <button
                type="button"
                onClick={() => void begin()}
                className={`px-4 py-2 rounded-lg text-sm font-medium bg-red-600 hover:bg-red-500 text-white ${focusRing}`}
              >
                Uninstall
              </button>
            )}
            {failed && (
              <button
                type="button"
                onClick={() => void begin()}
                className={`px-4 py-2 rounded-lg text-sm font-medium bg-red-600 hover:bg-red-500 text-white ${focusRing}`}
              >
                Retry
              </button>
            )}
            <button
              type="button"
              onClick={onClose}
              disabled={uninstalling}
              className={`px-4 py-2 rounded-lg text-sm font-medium ${
                uninstalling
                  ? "opacity-40 cursor-not-allowed bg-zinc-700 text-zinc-300"
                  : isDark
                    ? "bg-zinc-800 hover:bg-zinc-700 text-zinc-200"
                    : "bg-gray-100 hover:bg-gray-200 text-gray-700"
              } ${focusRing}`}
            >
              {started ? "Close" : "Cancel"}
            </button>
          </div>
        </div>
      </div>
    </div>
  );
}
```

- [ ] **Step 2: Typecheck**

Run: `cd "f:/Vibe Projects/vibe-podcast/frontend" && npm run typecheck`
Expected: PASS.

- [ ] **Step 3: Commit**

```bash
git add frontend/src/components/UninstallEngineDialog.tsx
git commit -m "feat(frontend): UninstallEngineDialog with confirm + progress log"
```

---

## Task 8: Wire secondary buttons through EngineSelector → ControlPanel → App

**Files:**
- Modify: `frontend/src/components/EngineSelector.tsx`
- Modify: `frontend/src/components/ControlPanel.tsx`
- Modify: `frontend/src/App.tsx`

- [ ] **Step 1: Add props to `EngineSelector`**

In `frontend/src/components/EngineSelector.tsx`, extend the `Props` interface:
```tsx
interface Props {
  isDark: boolean;
  engines: EngineInfo[];
  activeName: string | null;
  onSelect: (name: string) => Promise<void>;
  onLoad: (name: string) => Promise<void>;
  onInstall: (name: string) => void;
  onDownload: (name: string) => void;
  onDeleteWeights: (name: string) => void;
  onUninstall: (name: string) => void;
}
```
And add `onDeleteWeights` and `onUninstall` to the destructured params in `export function EngineSelector({ ... })`.

- [ ] **Step 2: Render the secondary destructive buttons**

In `EngineSelector.tsx`, the primary-action block ends at `</button>` then `)}` (line 258) followed by `</div>` (line 259). Insert a secondary-actions block between the primary button's closing `)}` and the `</div>` at line 259:

```tsx
                      )}

                      {/* Secondary destructive actions — hidden for the active
                          engine (switching away first is required). */}
                      {!isActive && (e.downloaded || (e.installed && (e.name === "chatterbox" || e.name === "omnivoice"))) && (
                        <div className="mt-1.5 flex items-center gap-3">
                          {e.downloaded && (
                            <button
                              type="button"
                              onClick={() => {
                                onDeleteWeights(e.name);
                                setOpen(false);
                              }}
                              className={`text-[11px] font-medium transition-colors ${
                                isDark
                                  ? "text-zinc-400 hover:text-red-400"
                                  : "text-gray-600 hover:text-red-700"
                              } ${focusRing}`}
                            >
                              Delete weights
                            </button>
                          )}
                          {e.installed && (e.name === "chatterbox" || e.name === "omnivoice") && (
                            <button
                              type="button"
                              onClick={() => {
                                onUninstall(e.name);
                                setOpen(false);
                              }}
                              className={`text-[11px] font-medium transition-colors ${
                                isDark
                                  ? "text-zinc-400 hover:text-red-400"
                                  : "text-gray-600 hover:text-red-700"
                              } ${focusRing}`}
                            >
                              Uninstall environment
                            </button>
                          )}
                        </div>
                      )}
```

(Place it so it renders inside the `<div className="flex-1 min-w-0">` that wraps the card body, right after the primary-action conditional. The `isActive` variable is already in scope from `const isActive = e.name === activeName;`.)

- [ ] **Step 3: Pass props through `ControlPanel`**

In `frontend/src/components/ControlPanel.tsx`, add to the `Props` interface (next to `onInstallEngine`/`onDownloadEngine`):
```tsx
  onDeleteWeights: (name: string) => void;
  onUninstallEngine: (name: string) => void;
```
Destructure them in the component params, then pass to `<EngineSelector>`:
```tsx
          <EngineSelector
            isDark={isDark}
            engines={engines}
            activeName={activeEngine}
            onSelect={onSelectEngine}
            onLoad={onLoadEngine}
            onInstall={onInstallEngine}
            onDownload={onDownloadEngine}
            onDeleteWeights={onDeleteWeights}
            onUninstall={onUninstallEngine}
          />
```

- [ ] **Step 4: Add state + dialogs + callbacks in `App.tsx`**

In `frontend/src/App.tsx`:

Add imports near the other dialog imports (top of file):
```tsx
import { DeleteWeightsDialog } from "@/components/DeleteWeightsDialog";
import { UninstallEngineDialog } from "@/components/UninstallEngineDialog";
```

Add state next to `installEngine`/`downloadEngine` (around line 113-114):
```tsx
  const [deleteWeightsEngine, setDeleteWeightsEngine] = useState<string | null>(null);
  const [uninstallEngine, setUninstallEngine] = useState<string | null>(null);
```

Pass callbacks to `<ControlPanel>` (next to `onInstallEngine`/`onDownloadEngine`):
```tsx
        onDeleteWeights={(name) => setDeleteWeightsEngine(name)}
        onUninstallEngine={(name) => setUninstallEngine(name)}
```

Add the dialogs right after the existing `{downloadEngine && (...)}` block (near the end of the main return, around line 905):
```tsx
      {deleteWeightsEngine && (
        <DeleteWeightsDialog
          isDark={isDark}
          engineName={deleteWeightsEngine}
          displayName={
            engines.find((e) => e.name === deleteWeightsEngine)?.display_name ??
            deleteWeightsEngine
          }
          onClose={() => setDeleteWeightsEngine(null)}
          onDone={async () => {
            await refreshEngines();
            setDeleteWeightsEngine(null);
          }}
        />
      )}
      {uninstallEngine && (
        <UninstallEngineDialog
          isDark={isDark}
          engineName={uninstallEngine}
          displayName={
            engines.find((e) => e.name === uninstallEngine)?.display_name ??
            uninstallEngine
          }
          onClose={() => setUninstallEngine(null)}
          onUninstalled={async () => {
            await refreshEngines();
            setUninstallEngine(null);
          }}
        />
      )}
```

- [ ] **Step 5: Typecheck + build**

Run: `cd "f:/Vibe Projects/vibe-podcast/frontend" && npm run typecheck && npm test && npm run build`
Expected: all PASS (existing 25 frontend tests still green; no new frontend unit tests added in this task).

- [ ] **Step 6: Commit**

```bash
git add frontend/src/components/EngineSelector.tsx frontend/src/components/ControlPanel.tsx frontend/src/App.tsx
git commit -m "feat(frontend): wire delete-weights + uninstall buttons into engine menu"
```

---

## Task 9: Verification

**Files:** none (verification only).

- [ ] **Step 1: Restart the dev environment**

The backend changed, so restart it (dev mode has no `--reload`). Kill any running `studio.py start`/`backend.cli`/`vite` processes, then relaunch `python studio.py start --dev`. Wait for vite (:5173) and api (:8880) to return 200.

- [ ] **Step 2: Backend smoke via curl**

```bash
curl -s http://localhost:8880/api/engines/vibevoice/delete-weights
curl -s http://localhost:8880/api/engines/chatterbox/uninstall
curl -s -o /dev/null -w "%{http_code}\n" http://localhost:8880/api/engines/kokoro/uninstall   # expect 400
```
Expected: first two return JSON `{"state":"idle",...}`; the third returns `400` (kokoro has no isolated env).

- [ ] **Step 3: Playwright UI check**

In the running app, open the engine selector. For a downloaded, non-active engine confirm a "Delete weights" link appears; for Chatterbox/OmniVoice (when installed) confirm "Uninstall environment" appears; confirm NEITHER appears on the currently-active engine's card. Open the Delete weights dialog, verify the confirmation copy + red "Delete weights (size)" button, click Cancel to dismiss without deleting. (Do not actually delete the active model's weights during the check unless you intend to re-download.)

- [ ] **Step 4: Commit any fixes**

```bash
git add -A
git commit -m "fix(engine-uninstall): adjustments from verification"
```

---

## Final verification (all phases)

- [ ] **Step 1: Backend suite**

Run: `cd "f:/Vibe Projects/vibe-podcast" && python -m pytest backend/tests/ -q`
Expected: all pass (existing + new `test_engine_uninstall.py`).

- [ ] **Step 2: Frontend gate**

Run: `cd "f:/Vibe Projects/vibe-podcast/frontend" && npm run typecheck && npm test && npm run build`
Expected: all pass.

- [ ] **Step 3: Final code review**

Dispatch a final code-reviewer over the whole branch.

- [ ] **Step 4: Finish the branch**

Use superpowers:finishing-a-development-branch.

---

## Self-Review notes (plan author)

- **Spec coverage:** ModelDeleter → Task 2; EngineEnvUninstaller → Task 3; Chatterbox `downloaded()` override → Task 1; endpoints + deps + app wiring → Task 4; API types + wrappers → Task 5; DeleteWeightsDialog → Task 6; UninstallEngineDialog → Task 7; EngineSelector buttons + active-engine gating + ControlPanel + App wiring → Task 8; backend tests → Tasks 1-4; verification → Task 9. All spec sections mapped.
- **Type consistency:** `DeleteWeightsStatus`/`UninstallStatus` fields (`state`/`log`/`error`) match across backend models, TS interfaces, and dialogs. `DELETABLE` (model_delete.py) used in engines.py as `_DELETABLE`. `UNINSTALLABLE` exists in engine_uninstall.py but the endpoint gates on `uninstallers.get(name) is None` (dict membership) — consistent with how the installer endpoints gate, and the app only registers chatterbox/omnivoice uninstallers. `onDeleteWeights`/`onUninstall` (EngineSelector) ← `onDeleteWeights`/`onUninstallEngine` (ControlPanel) ← `setDeleteWeightsEngine`/`setUninstallEngine` (App) — names traced end to end.
- **Destructive UX:** both dialogs require an explicit confirm click (neither auto-starts), use red danger buttons, and disable Close while the operation runs. Active-engine cards hide both actions (spec's definitive gating).
- **No placeholders:** every code step has complete content.
