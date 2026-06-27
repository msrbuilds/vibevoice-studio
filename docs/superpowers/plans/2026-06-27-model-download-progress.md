# Model Download Progress Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** When the user switches to VibeVoice or Kokoro and its weights aren't on disk, show a confirm-then-progress modal (progress bar + %/speed/ETA + live log) instead of a silent "Loading…" spinner.

**Architecture:** A new `ModelDownloader` service runs `snapshot_download` on a daemon thread inside the FastAPI process, folding byte deltas from a custom `tqdm` subclass into a shared progress snapshot. The frontend polls `GET /api/engines/{name}/download`. Engine `info()` gains a `downloaded` flag (real check for VibeVoice/Kokoro, `True` for everything else) so the selector knows when to offer "Download" instead of "Switch". Chatterbox is untouched.

**Tech Stack:** Python / FastAPI / `huggingface_hub` / `tqdm` (backend); React + TypeScript + Vite + Tailwind (frontend). Tests: `pytest` (backend), `tsc` typecheck (frontend).

**Reference spec:** `docs/superpowers/specs/2026-06-27-model-download-progress-design.md`

---

## File Structure

- **Create** `backend/core/model_cache.py` — `model_downloaded(repo_id)` cache-presence check.
- **Create** `backend/services/model_download.py` — `ModelDownloader`, `Progress`, `_default_runner`, `_ProgressTqdm`.
- **Create** `backend/tests/test_model_download.py` — service + helper + API tests.
- **Modify** `backend/core/engines/__init__.py` — add `Engine.downloaded()` + `downloaded` in `info()`.
- **Modify** `backend/core/engines/vibevoice_engine.py` — override `downloaded()`.
- **Modify** `backend/core/engines/kokoro_engine.py` — override `downloaded()`.
- **Modify** `backend/api/engines.py` — `DownloadStatusModel`, `EngineInfoModel.downloaded`, GET/POST `/{name}/download`.
- **Modify** `backend/api/deps.py` — `get_model_downloader`.
- **Modify** `backend/app.py` — `app.state.model_downloader = ModelDownloader()`.
- **Create** `frontend/src/components/DownloadModelDialog.tsx` — confirm + progress modal.
- **Modify** `frontend/src/types/models.ts` — `EngineInfo.downloaded`, `DownloadStatus`.
- **Modify** `frontend/src/lib/api.ts` — `getModelDownloadStatus`, `startModelDownload`.
- **Modify** `frontend/src/components/EngineSelector.tsx` — Download branch + `onDownload` prop.
- **Modify** `frontend/src/components/ActionBar.tsx` — `onDownloadEngine` passthrough.
- **Modify** `frontend/src/App.tsx` — download dialog state + wiring.

All backend test commands run from `backend/`: `cd backend && python -m pytest …`. All frontend commands run from `frontend/`.

---

## Task 1: `model_downloaded` cache-presence helper

**Files:**
- Create: `backend/core/model_cache.py`
- Test: `backend/tests/test_model_download.py`

- [ ] **Step 1: Write the failing test**

Create `backend/tests/test_model_download.py` with:

```python
"""Tests for model-download cache detection, the ModelDownloader service,
and the /download API. Uses injected fakes — no network, no real weights."""

import sys
import time
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT))

import huggingface_hub  # noqa: E402

from backend.core import model_cache  # noqa: E402


def test_model_downloaded_true_when_snapshot_resolves(monkeypatch):
    monkeypatch.setattr(huggingface_hub, "snapshot_download", lambda *a, **k: "/cache/x")
    assert model_cache.model_downloaded("org/repo") is True


def test_model_downloaded_false_when_snapshot_raises(monkeypatch):
    def _boom(*a, **k):
        raise RuntimeError("not cached")
    monkeypatch.setattr(huggingface_hub, "snapshot_download", _boom)
    assert model_cache.model_downloaded("org/repo") is False
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd backend && python -m pytest tests/test_model_download.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'backend.core.model_cache'`

- [ ] **Step 3: Write minimal implementation**

Create `backend/core/model_cache.py`:

```python
"""Detect whether a model repo's weights are present in the local HF cache.

`snapshot_download(..., local_files_only=True)` returns the snapshot path when
every file of the repo's current revision is already cached, and raises
otherwise — so it doubles as a "fully downloaded?" probe with no network call.
"""

from __future__ import annotations


def model_downloaded(repo_id: str) -> bool:
    """True if every file of `repo_id`'s current revision is cached locally."""
    try:
        # Imported lazily so this module is import-safe before the HF cache
        # dir is configured (see backend/core/hf_paths.py).
        from huggingface_hub import snapshot_download

        snapshot_download(repo_id, local_files_only=True)
        return True
    except Exception:  # noqa: BLE001 — any failure means "not fully cached"
        return False
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd backend && python -m pytest tests/test_model_download.py -v`
Expected: PASS (2 passed)

- [ ] **Step 5: Commit**

```bash
git add backend/core/model_cache.py backend/tests/test_model_download.py
git commit -m "feat: model_downloaded cache-presence helper"
```

---

## Task 2: `downloaded` flag on the engine interface

**Files:**
- Modify: `backend/core/engines/__init__.py` (add `downloaded()` near `installed()` at line ~121; add to `info()` at line ~170)
- Modify: `backend/core/engines/vibevoice_engine.py` (add method after `is_loaded` at line ~109)
- Modify: `backend/core/engines/kokoro_engine.py` (add method near other lifecycle methods)
- Test: `backend/tests/test_model_download.py`

- [ ] **Step 1: Write the failing test**

Append to `backend/tests/test_model_download.py`:

```python
from backend.core.engines import Engine, EngineResult, EngineSynthRequest  # noqa: E402


class _StubEngine(Engine):
    """Minimal concrete Engine for exercising base-class behavior."""

    name = "stub"

    def __init__(self, downloaded=True):
        self._downloaded = downloaded

    def load(self): ...
    def unload(self): ...
    def is_loaded(self): return False
    def synthesize(self, req): raise NotImplementedError
    def sample_rate(self): return 24000
    def max_speakers(self): return 1
    def supports_voice_cloning(self): return False
    def default_cfg_scale(self): return None
    def available_voices(self): return []
    def downloaded(self): return self._downloaded


def test_engine_info_includes_downloaded_default_true():
    info = _StubEngine().info()
    assert info["downloaded"] is True


def test_engine_info_reflects_overridden_downloaded():
    assert _StubEngine(downloaded=False).info()["downloaded"] is False
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd backend && python -m pytest tests/test_model_download.py::test_engine_info_includes_downloaded_default_true -v`
Expected: FAIL with `KeyError: 'downloaded'`

- [ ] **Step 3: Write minimal implementation**

In `backend/core/engines/__init__.py`, add this method directly below `installed()` (after line 125):

```python
    def downloaded(self) -> bool:
        """True if the engine's model weights are present in the local cache.

        Engines that fetch large weights lazily (VibeVoice, Kokoro) override
        this so the UI can offer a download-with-progress flow before the
        first load. Default True: engines without a separate weight download
        (or that manage it elsewhere, like Chatterbox) never trigger that UI.
        """
        return True
```

In the same file, add `"downloaded"` to the `info()` dict (inside the dict returned at line ~172, after the `"installed"` entry):

```python
            "installed": self.installed(),
            "downloaded": self.downloaded(),
```

In `backend/core/engines/vibevoice_engine.py`, add after `is_loaded()` (line ~109):

```python
    def downloaded(self) -> bool:
        from ..model_cache import model_downloaded

        return model_downloaded(self._model_manager.model_id)
```

In `backend/core/engines/kokoro_engine.py`, add a `downloaded()` method alongside the other lifecycle methods (e.g. right after the class's `is_loaded`/`unload`); it uses the existing `self._model_id` (`"hexgrad/Kokoro-82M"`):

```python
    def downloaded(self) -> bool:
        from ..model_cache import model_downloaded

        return model_downloaded(self._model_id)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd backend && python -m pytest tests/test_model_download.py -v`
Expected: PASS (4 passed)

- [ ] **Step 5: Commit**

```bash
git add backend/core/engines/__init__.py backend/core/engines/vibevoice_engine.py backend/core/engines/kokoro_engine.py backend/tests/test_model_download.py
git commit -m "feat: expose a downloaded flag on engines"
```

---

## Task 3: `ModelDownloader` service core (state machine + progress math)

**Files:**
- Create: `backend/services/model_download.py`
- Test: `backend/tests/test_model_download.py`

- [ ] **Step 1: Write the failing test**

Append to `backend/tests/test_model_download.py`:

```python
import pytest  # noqa: E402

from backend.services.model_download import ModelDownloader, Progress  # noqa: E402


def _wait(dl, timeout=5.0):
    deadline = time.time() + timeout
    while time.time() < deadline and dl.status()["state"] == "downloading":
        time.sleep(0.02)


def test_download_success_sets_done_and_percent():
    def runner(repo_id, prog):
        prog.set_total(100)
        prog.add_bytes(50, "model.safetensors")
        prog.add_bytes(50, "model.safetensors")
    dl = ModelDownloader(runner=runner)
    dl.start("vibevoice")
    _wait(dl)
    s = dl.status()
    assert s["state"] == "done"
    assert s["returncode"] == 0
    assert s["engine"] == "vibevoice"
    assert s["downloaded_bytes"] == 100
    assert s["percent"] == 100.0


def test_download_error_sets_error_state():
    def runner(repo_id, prog):
        raise RuntimeError("network down")
    dl = ModelDownloader(runner=runner)
    dl.start("kokoro")
    _wait(dl)
    s = dl.status()
    assert s["state"] == "error"
    assert s["returncode"] == -1
    assert "network down" in s["error"]


def test_start_rejects_non_downloadable_engine():
    dl = ModelDownloader(runner=lambda r, p: None)
    with pytest.raises(ValueError):
        dl.start("chatterbox")


def test_start_coalesces_while_downloading():
    started = {"n": 0}
    def runner(repo_id, prog):
        started["n"] += 1
        time.sleep(0.2)
    dl = ModelDownloader(runner=runner)
    dl.start("vibevoice")
    dl.start("vibevoice")  # must NOT launch a second download
    _wait(dl)
    assert started["n"] == 1
    assert dl.status()["state"] == "done"


def test_speed_and_eta_from_injected_clock():
    seq = iter([10.0, 11.0])  # two add_bytes calls → two timestamped samples
    dl = ModelDownloader(runner=lambda r, p: None, clock=lambda: next(seq))
    prog = Progress(dl)
    prog.set_total(800)
    prog.add_bytes(200, "f")  # t=10, total dl=200
    prog.add_bytes(200, "f")  # t=11, total dl=400
    s = dl.status()
    assert s["downloaded_bytes"] == 400
    assert s["percent"] == 50.0
    assert s["speed_bps"] == 200.0           # (400-200)/(11-10)
    assert s["eta_sec"] == 2.0               # remaining 400 / 200 bps
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd backend && python -m pytest tests/test_model_download.py -k download -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'backend.services.model_download'`

- [ ] **Step 3: Write minimal implementation**

Create `backend/services/model_download.py`:

```python
"""Background model-weight downloader with live progress.

Runs `snapshot_download` on a daemon thread inside the backend, folding byte
deltas into a shared progress snapshot that the UI polls. One download at a
time (weights are large). State machine: idle -> downloading -> done | error.

The downloader logic here is engine-agnostic; the network parts live in the
injectable `runner` (default `_default_runner`) so tests drive a fake.
"""

from __future__ import annotations

import threading
import time
from collections import deque
from typing import Callable, Deque, Optional, Tuple

from backend.scripts.download_models import MODEL_CATALOG

#: Engines whose weights this downloader can fetch (in-process engines).
DOWNLOADABLE: frozenset[str] = frozenset({"vibevoice", "kokoro"})

_MAX_LOG_LINES = 500
_SPEED_WINDOW = 30  # number of (ts, bytes) samples kept for speed/ETA

# A runner downloads `repo_id`, reporting progress via the given Progress.
Runner = Callable[[str, "Progress"], None]


class Progress:
    """The callback surface a runner uses to report download progress."""

    def __init__(self, downloader: "ModelDownloader") -> None:
        self._d = downloader

    def set_total(self, total: int) -> None:
        self._d._set_total(total)

    def add_bytes(self, n: int, current_file: Optional[str] = None) -> None:
        self._d._add_bytes(n, current_file)

    def log(self, line: str) -> None:
        self._d._log(line)


class ModelDownloader:
    """Thread-safe, single-flight model download with a progress snapshot."""

    def __init__(
        self,
        *,
        runner: Runner | None = None,
        clock: Callable[[], float] | None = None,
    ) -> None:
        from backend.services.model_download import _default_runner  # late bind
        self._runner: Runner = runner or _default_runner
        self._clock = clock or time.monotonic
        self._lock = threading.Lock()
        self._thread: threading.Thread | None = None
        self._engine: str | None = None
        self._state = "idle"
        self._downloaded = 0
        self._total: int | None = None
        self._current_file: str | None = None
        self._log_lines: list[str] = []
        self._error: str | None = None
        self._returncode: int | None = None
        self._samples: Deque[Tuple[float, int]] = deque(maxlen=_SPEED_WINDOW)

    # -- public API
    def status(self) -> dict:
        with self._lock:
            return self._snapshot_locked()

    def start(self, engine: str) -> dict:
        if engine not in DOWNLOADABLE:
            raise ValueError(f"{engine} is not downloadable")
        with self._lock:
            if self._state == "downloading":
                return self._snapshot_locked()  # coalesce onto the running job
            repo_id = MODEL_CATALOG[engine]["repo_id"]
            self._engine = engine
            self._state = "downloading"
            self._downloaded = 0
            self._total = None
            self._current_file = None
            self._log_lines = []
            self._error = None
            self._returncode = None
            self._samples.clear()
            self._samples.append((self._clock(), 0))
            self._thread = threading.Thread(
                target=self._run, args=(repo_id,), daemon=True
            )
            self._thread.start()
            return self._snapshot_locked()

    # -- internals
    def _run(self, repo_id: str) -> None:
        try:
            self._runner(repo_id, Progress(self))
        except Exception as exc:  # noqa: BLE001
            with self._lock:
                self._error = str(exc)
                self._log_lines.append(f"[download error] {exc}")
                self._state = "error"
                self._returncode = -1
            return
        with self._lock:
            if self._total is not None:
                self._downloaded = self._total
            self._state = "done"
            self._returncode = 0

    def _set_total(self, total: int) -> None:
        with self._lock:
            self._total = int(total) if total and total > 0 else None

    def _add_bytes(self, n: int, current_file: Optional[str]) -> None:
        with self._lock:
            self._downloaded += int(n)
            if current_file:
                self._current_file = current_file
            self._samples.append((self._clock(), self._downloaded))

    def _log(self, line: str) -> None:
        with self._lock:
            self._log_lines.append(line)
            if len(self._log_lines) > _MAX_LOG_LINES:
                del self._log_lines[: len(self._log_lines) - _MAX_LOG_LINES]

    def _speed_bps_locked(self) -> float | None:
        if len(self._samples) < 2:
            return None
        t0, b0 = self._samples[0]
        t1, b1 = self._samples[-1]
        dt = t1 - t0
        if dt <= 0:
            return None
        return max(0.0, (b1 - b0) / dt)

    def _snapshot_locked(self) -> dict:
        speed = self._speed_bps_locked()
        percent: float | None = None
        if self._total:
            percent = min(100.0, self._downloaded * 100.0 / self._total)
        eta: float | None = None
        if speed and speed > 0 and self._total:
            eta = max(0, self._total - self._downloaded) / speed
        return {
            "engine": self._engine,
            "state": self._state,
            "percent": percent,
            "downloaded_bytes": self._downloaded,
            "total_bytes": self._total,
            "speed_bps": speed,
            "eta_sec": eta,
            "current_file": self._current_file,
            "log": list(self._log_lines),
            "error": self._error,
            "returncode": self._returncode,
        }


def _repo_total_bytes(repo_id: str) -> int | None:
    """Best-effort total download size for a repo's current revision."""
    try:
        from huggingface_hub import HfApi

        info = HfApi().model_info(repo_id, files_metadata=True)
        total = 0
        for sib in info.siblings or []:
            size = getattr(sib, "size", None)
            if size is None:
                lfs = getattr(sib, "lfs", None)
                size = getattr(lfs, "size", None) if lfs else None
            if size:
                total += int(size)
        return total or None
    except Exception:  # noqa: BLE001
        return None


def _make_progress_tqdm(progress: Progress):
    """A tqdm subclass that folds per-file byte deltas into `progress`.

    huggingface_hub creates one byte-unit bar per downloading file plus a
    "Fetching N files" item-unit bar. We count only byte bars (`unit == "B"`)
    so the item bar never double-counts.
    """
    from tqdm.auto import tqdm as _tqdm

    class _ProgressTqdm(_tqdm):
        def update(self, n=1):
            if n and getattr(self, "unit", None) == "B":
                progress.add_bytes(int(n), getattr(self, "desc", None) or None)
            return super().update(n)

    return _ProgressTqdm


def _default_runner(repo_id: str, progress: Progress) -> None:
    """Download `repo_id` into the local HF cache with live byte progress."""
    from huggingface_hub import snapshot_download

    progress.log(f"Resolving {repo_id} …")
    total = _repo_total_bytes(repo_id)
    if total:
        progress.set_total(total)
        progress.log(f"Total download size: {total / (1024 * 1024):.0f} MB")
    else:
        progress.log("Total size unknown; reporting bytes downloaded.")
    snapshot_download(repo_id, tqdm_class=_make_progress_tqdm(progress))
    progress.log("Download complete.")
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd backend && python -m pytest tests/test_model_download.py -v`
Expected: PASS (all `test_download_*`, `test_start_*`, `test_speed_*` green)

- [ ] **Step 5: Commit**

```bash
git add backend/services/model_download.py backend/tests/test_model_download.py
git commit -m "feat: ModelDownloader service with live byte progress"
```

---

## Task 4: `_ProgressTqdm` byte-only filtering test

**Files:**
- Test: `backend/tests/test_model_download.py` (no production change — locks in Task 3 behavior)

- [ ] **Step 1: Write the failing test**

Append to `backend/tests/test_model_download.py`:

```python
from backend.services.model_download import _make_progress_tqdm  # noqa: E402


def test_progress_tqdm_counts_only_byte_unit_bars():
    dl = ModelDownloader(runner=lambda r, p: None)
    cls = _make_progress_tqdm(Progress(dl))

    byte_bar = cls(total=100, unit="B", disable=True)
    byte_bar.update(40)
    assert dl.status()["downloaded_bytes"] == 40

    item_bar = cls(total=5, unit="it", disable=True)  # "Fetching N files" bar
    item_bar.update(3)
    assert dl.status()["downloaded_bytes"] == 40  # unchanged — item bar ignored
```

- [ ] **Step 2: Run test to verify it passes (behavior already implemented in Task 3)**

Run: `cd backend && python -m pytest tests/test_model_download.py::test_progress_tqdm_counts_only_byte_unit_bars -v`
Expected: PASS

(If it fails, the `unit == "B"` guard in `_make_progress_tqdm` is wrong — fix it in `backend/services/model_download.py`.)

- [ ] **Step 3: Commit**

```bash
git add backend/tests/test_model_download.py
git commit -m "test: ProgressTqdm counts only byte-unit bars"
```

---

## Task 5: `/download` API endpoints + wiring

**Files:**
- Modify: `backend/api/deps.py` (add provider after `get_chatterbox_installer`, line ~24)
- Modify: `backend/api/engines.py` (import, `EngineInfoModel.downloaded`, `_to_model`, `DownloadStatusModel`, two routes)
- Modify: `backend/app.py` (instantiate on `app.state`, line ~173)
- Test: `backend/tests/test_model_download.py`

- [ ] **Step 1: Write the failing test**

Append to `backend/tests/test_model_download.py`:

```python
def _make_client(downloader):
    from fastapi import FastAPI
    from fastapi.testclient import TestClient
    from backend.api.engines import router
    from backend.api.deps import get_model_downloader

    app = FastAPI()
    app.include_router(router)
    app.state.model_downloader = downloader
    app.dependency_overrides[get_model_downloader] = lambda: downloader
    return TestClient(app)


def test_download_endpoint_rejects_non_downloadable():
    client = _make_client(ModelDownloader(runner=lambda r, p: None))
    assert client.get("/api/engines/chatterbox/download").status_code == 400
    assert client.post("/api/engines/chatterbox/download").status_code == 400


def test_download_endpoint_start_and_status():
    def runner(repo_id, prog):
        prog.set_total(10)
        prog.add_bytes(10, "f")
    dl = ModelDownloader(runner=runner)
    client = _make_client(dl)

    assert client.get("/api/engines/vibevoice/download").json()["state"] == "idle"
    r = client.post("/api/engines/vibevoice/download")
    assert r.status_code == 200
    _wait(dl)
    s = client.get("/api/engines/vibevoice/download").json()
    assert s["state"] == "done"
    assert s["downloaded_bytes"] == 10
    assert s["percent"] == 100.0
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd backend && python -m pytest tests/test_model_download.py -k endpoint -v`
Expected: FAIL with `ImportError: cannot import name 'get_model_downloader'`

- [ ] **Step 3: Write minimal implementation**

In `backend/api/deps.py`, add after `get_chatterbox_installer` (line ~24):

```python
def get_model_downloader(request: Request):
    return request.app.state.model_downloader  # type: ignore[no-any-return]
```

In `backend/api/engines.py`, update the deps import (line 12):

```python
from .deps import get_chatterbox_installer, get_engine_manager, get_model_downloader
```

Add `downloaded` to `EngineInfoModel` (after the `installed` field, line ~24):

```python
    installed: bool
    downloaded: bool
```

Add `downloaded` in `_to_model` (after the `installed=` line, ~54):

```python
        installed=info.get("installed", True),
        downloaded=info.get("downloaded", True),
```

Add the new schema after `InstallStatusModel` (line ~41):

```python
class DownloadStatusModel(BaseModel):
    engine: str | None
    state: str
    percent: float | None
    downloaded_bytes: int
    total_bytes: int | None
    speed_bps: float | None
    eta_sec: float | None
    current_file: str | None
    log: list[str]
    error: str | None
    returncode: int | None


_DOWNLOADABLE = {"vibevoice", "kokoro"}
```

Add the two routes at the end of `backend/api/engines.py`:

```python
@router.get("/{name}/download", response_model=DownloadStatusModel)
def download_status(name: str, downloader=Depends(get_model_downloader)) -> DownloadStatusModel:
    """Current weight-download state for an in-process engine."""
    if name not in _DOWNLOADABLE:
        raise HTTPException(status_code=400, detail=f"{name} is not downloadable")
    return DownloadStatusModel(**downloader.status())


@router.post("/{name}/download", response_model=DownloadStatusModel)
def start_download(name: str, downloader=Depends(get_model_downloader)) -> DownloadStatusModel:
    """Start (or coalesce onto a running) weight download for the engine."""
    if name not in _DOWNLOADABLE:
        raise HTTPException(status_code=400, detail=f"{name} is not downloadable")
    try:
        return DownloadStatusModel(**downloader.start(name))
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
```

In `backend/app.py`, add the import near the other service imports (find where `ChatterboxInstaller` is imported and add beside it):

```python
from .services.model_download import ModelDownloader
```

And instantiate it on `app.state` right after the `chatterbox_installer` line (~173):

```python
    app.state.chatterbox_installer = ChatterboxInstaller()
    app.state.model_downloader = ModelDownloader()
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd backend && python -m pytest tests/test_model_download.py -v`
Expected: PASS (whole file green)

- [ ] **Step 5: Run the full backend suite (no regressions)**

Run: `cd backend && python -m pytest tests/ -q`
Expected: PASS — previous count + the new `test_model_download.py` tests, 0 failures.

- [ ] **Step 6: Commit**

```bash
git add backend/api/deps.py backend/api/engines.py backend/app.py backend/tests/test_model_download.py
git commit -m "feat: add /api/engines/{name}/download endpoints"
```

---

## Task 6: Frontend types + API client

**Files:**
- Modify: `frontend/src/types/models.ts` (add field at line ~48; add `DownloadStatus` after `InstallStatus`, line ~55)
- Modify: `frontend/src/lib/api.ts` (import type; add two functions after `getChatterboxInstallStatus`, line ~146)

- [ ] **Step 1: Add the `downloaded` field and `DownloadStatus` type**

In `frontend/src/types/models.ts`, add to `EngineInfo` (after `installed: boolean;`, line ~44):

```typescript
  installed: boolean;
  downloaded: boolean;
```

And add after the `InstallStatus` interface (line ~55):

```typescript
export interface DownloadStatus {
  engine: string | null;
  state: "idle" | "downloading" | "done" | "error";
  percent: number | null;
  downloaded_bytes: number;
  total_bytes: number | null;
  speed_bps: number | null;
  eta_sec: number | null;
  current_file: string | null;
  log: string[];
  error: string | null;
  returncode: number | null;
}
```

- [ ] **Step 2: Add the API wrappers**

In `frontend/src/lib/api.ts`, add `DownloadStatus` to the type import block (lines 3–12):

```typescript
  ConfigResponse,
  DownloadStatus,
  EngineInfo,
```

And add after `getChatterboxInstallStatus` (line ~146):

```typescript
export async function startModelDownload(name: string): Promise<DownloadStatus> {
  return jsonOrThrow<DownloadStatus>(
    await fetch(`${API_BASE}/engines/${encodeURIComponent(name)}/download`, {
      method: "POST",
    }),
  );
}

export async function getModelDownloadStatus(name: string): Promise<DownloadStatus> {
  return jsonOrThrow<DownloadStatus>(
    await fetch(`${API_BASE}/engines/${encodeURIComponent(name)}/download`),
  );
}
```

- [ ] **Step 3: Typecheck**

Run: `cd frontend && npm run typecheck`
Expected: PASS (no errors). New `downloaded` field on `EngineInfo` may surface errors only once consumers use it — Tasks 7–8 add those.

- [ ] **Step 4: Commit**

```bash
git add frontend/src/types/models.ts frontend/src/lib/api.ts
git commit -m "feat: frontend types and api for model download"
```

---

## Task 7: `DownloadModelDialog` component

**Files:**
- Create: `frontend/src/components/DownloadModelDialog.tsx`

- [ ] **Step 1: Write the component**

Create `frontend/src/components/DownloadModelDialog.tsx`:

```tsx
import { useEffect, useRef, useState } from "react";
import { Download, Loader2, X } from "lucide-react";
import { getModelDownloadStatus, startModelDownload } from "@/lib/api";
import type { DownloadStatus } from "@/types/models";

interface Props {
  isDark: boolean;
  engineName: string;
  displayName: string;
  onClose: () => void;
  onDone: () => void;
}

// Mirrors the catalog sizes in backend/scripts/download_models.py.
const MODEL_SIZES: Record<string, string> = {
  vibevoice: "~5.4 GB",
  kokoro: "~350 MB",
};

const fmtBytes = (b: number): string =>
  b >= 1e9 ? `${(b / 1e9).toFixed(2)} GB` : `${(b / 1e6).toFixed(0)} MB`;

const fmtSpeed = (bps: number | null): string =>
  bps && bps > 0 ? `${(bps / 1e6).toFixed(1)} MB/s` : "—";

const fmtEta = (s: number | null): string => {
  if (s == null) return "—";
  const m = Math.floor(s / 60);
  const sec = Math.floor(s % 60);
  return `${m}:${String(sec).padStart(2, "0")}`;
};

export function DownloadModelDialog({
  isDark,
  engineName,
  displayName,
  onClose,
  onDone,
}: Props) {
  const [started, setStarted] = useState(false);
  const [status, setStatus] = useState<DownloadStatus>({
    engine: engineName,
    state: "idle",
    percent: null,
    downloaded_bytes: 0,
    total_bytes: null,
    speed_bps: null,
    eta_sec: null,
    current_file: null,
    log: [],
    error: null,
    returncode: null,
  });
  const logRef = useRef<HTMLPreElement>(null);
  const timerRef = useRef<number | null>(null);
  const sizeLabel = MODEL_SIZES[engineName] ?? "";

  const poll = async () => {
    try {
      const s = await getModelDownloadStatus(engineName);
      setStatus(s);
      if (s.state === "downloading") {
        timerRef.current = window.setTimeout(() => void poll(), 1000);
      } else if (s.state === "done") {
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
    setStatus((prev) => ({ ...prev, state: "downloading", log: [] }));
    try {
      await startModelDownload(engineName);
    } catch (err) {
      setStatus((prev) => ({
        ...prev,
        state: "error",
        error: err instanceof Error ? err.message : String(err),
        log: [err instanceof Error ? err.message : String(err)],
      }));
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

  const downloading = status.state === "downloading";
  const failed = status.state === "error";
  const pct = status.percent ?? 0;

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
            {downloading ? (
              <Loader2 className="w-4 h-4 animate-spin text-teal-400" />
            ) : (
              <Download className="w-4 h-4 text-teal-400" />
            )}
            <span className={`font-semibold ${isDark ? "text-white" : "text-gray-900"}`}>
              {downloading
                ? `Downloading ${displayName}…`
                : failed
                  ? `${displayName} download failed`
                  : `Download ${displayName}`}
            </span>
          </div>
          <button
            type="button"
            onClick={onClose}
            disabled={downloading}
            className={`p-1 rounded ${
              downloading
                ? "opacity-40 cursor-not-allowed"
                : isDark
                  ? "hover:bg-zinc-800 text-zinc-400"
                  : "hover:bg-gray-100 text-gray-500"
            }`}
          >
            <X className="w-5 h-5" />
          </button>
        </div>

        <div className="p-5 space-y-4">
          {!started ? (
            <p className={`text-sm ${isDark ? "text-zinc-400" : "text-gray-600"}`}>
              {displayName} needs a {sizeLabel} model download before it can run.
              This happens once; the weights are cached locally afterward.
            </p>
          ) : (
            <>
              <div className="space-y-1">
                <div
                  className={`h-2.5 w-full rounded-full overflow-hidden ${
                    isDark ? "bg-zinc-800" : "bg-gray-200"
                  }`}
                >
                  <div
                    className="h-full bg-teal-500 transition-[width] duration-500"
                    style={{ width: `${status.total_bytes ? pct : 100}%` }}
                  />
                </div>
                <div
                  className={`flex justify-between text-[11px] ${
                    isDark ? "text-zinc-400" : "text-gray-500"
                  }`}
                >
                  <span>
                    {status.total_bytes
                      ? `${pct.toFixed(0)}% · ${fmtBytes(status.downloaded_bytes)} / ${fmtBytes(status.total_bytes)}`
                      : `${fmtBytes(status.downloaded_bytes)} downloaded`}
                  </span>
                  <span>
                    {fmtSpeed(status.speed_bps)}
                    {downloading && status.eta_sec != null
                      ? ` · ETA ${fmtEta(status.eta_sec)}`
                      : ""}
                  </span>
                </div>
              </div>
              <pre
                ref={logRef}
                className={`h-48 overflow-auto rounded-lg p-3 text-[11px] leading-relaxed font-mono whitespace-pre-wrap ${
                  isDark ? "bg-black/40 text-zinc-300" : "bg-gray-50 text-gray-700"
                }`}
              >
                {status.log.length ? status.log.join("\n") : "Starting…"}
              </pre>
            </>
          )}

          <div className="flex justify-end gap-2">
            {!started && (
              <button
                type="button"
                onClick={() => void begin()}
                className="px-4 py-2 rounded-lg text-sm font-medium bg-teal-600 hover:bg-teal-500 text-white"
              >
                {`Download (${sizeLabel})`}
              </button>
            )}
            {failed && (
              <button
                type="button"
                onClick={() => void begin()}
                className="px-4 py-2 rounded-lg text-sm font-medium bg-teal-600 hover:bg-teal-500 text-white"
              >
                Retry
              </button>
            )}
            <button
              type="button"
              onClick={onClose}
              disabled={downloading}
              className={`px-4 py-2 rounded-lg text-sm font-medium ${
                downloading
                  ? "opacity-40 cursor-not-allowed bg-zinc-700 text-zinc-300"
                  : isDark
                    ? "bg-zinc-800 hover:bg-zinc-700 text-zinc-200"
                    : "bg-gray-100 hover:bg-gray-200 text-gray-700"
              }`}
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

Run: `cd frontend && npm run typecheck`
Expected: PASS (component compiles; it's not yet rendered anywhere — Task 8 wires it).

- [ ] **Step 3: Commit**

```bash
git add frontend/src/components/DownloadModelDialog.tsx
git commit -m "feat: DownloadModelDialog with progress bar and live log"
```

---

## Task 8: Wire the Download branch through the UI

**Files:**
- Modify: `frontend/src/components/EngineSelector.tsx` (add `onDownload` prop; add Download branch in the button block, lines ~177–211)
- Modify: `frontend/src/components/ActionBar.tsx` (add `onDownloadEngine` prop + passthrough)
- Modify: `frontend/src/App.tsx` (import dialog; add state; pass `onDownloadEngine`; render dialog)

- [ ] **Step 1: Add the Download branch to `EngineSelector`**

In `frontend/src/components/EngineSelector.tsx`, add to `Props` (after `onInstall`, line ~11):

```typescript
  onInstall: (name: string) => void;
  onDownload: (name: string) => void;
```

Add `onDownload` to the destructured params (after `onInstall`, line ~20):

```typescript
  onInstall,
  onDownload,
```

Replace the button block (the `{e.installed === false ? (...) : (...)}` ternary at lines ~177–211) with a three-way branch:

```tsx
                      {e.installed === false ? (
                        <button
                          type="button"
                          onClick={() => {
                            onInstall(e.name);
                            setOpen(false);
                          }}
                          className={`mt-2 w-full text-xs px-3 py-1.5 rounded-md font-medium transition-colors ${
                            isDark
                              ? "bg-teal-700/40 hover:bg-teal-700/60 text-teal-200"
                              : "bg-teal-50 hover:bg-teal-100 text-teal-700"
                          }`}
                        >
                          {`Install ${e.display_name}`}
                        </button>
                      ) : e.downloaded === false ? (
                        <button
                          type="button"
                          onClick={() => {
                            onDownload(e.name);
                            setOpen(false);
                          }}
                          className={`mt-2 w-full text-xs px-3 py-1.5 rounded-md font-medium transition-colors ${
                            isDark
                              ? "bg-teal-700/40 hover:bg-teal-700/60 text-teal-200"
                              : "bg-teal-50 hover:bg-teal-100 text-teal-700"
                          }`}
                        >
                          {`Download ${e.display_name}`}
                        </button>
                      ) : (
                        <button
                          type="button"
                          onClick={() => void handleSelect(e.name)}
                          disabled={isActive}
                          className={`mt-2 w-full text-xs px-3 py-1.5 rounded-md font-medium transition-colors ${
                            isActive
                              ? "bg-teal-600/20 text-teal-300 cursor-default"
                              : isDark
                                ? "bg-zinc-800 hover:bg-zinc-700 text-zinc-200"
                                : "bg-gray-100 hover:bg-gray-200 text-gray-700"
                          }`}
                        >
                          {isActive
                            ? "Currently active"
                            : switching
                              ? "Loading…"
                              : `Switch to ${e.display_name}`}
                        </button>
                      )}
```

- [ ] **Step 2: Thread `onDownloadEngine` through `ActionBar`**

In `frontend/src/components/ActionBar.tsx`, add to `Props` (after `onInstallEngine`, line ~27):

```typescript
  onInstallEngine: (name: string) => void;
  onDownloadEngine: (name: string) => void;
```

Add to the destructured params (after `onInstallEngine`, line ~54):

```typescript
  onInstallEngine,
  onDownloadEngine,
```

Pass it to `EngineSelector` (in the JSX, after `onInstall={onInstallEngine}`, line ~164):

```tsx
          onInstall={onInstallEngine}
          onDownload={onDownloadEngine}
```

- [ ] **Step 3: Wire state + dialog in `App.tsx`**

In `frontend/src/App.tsx`, add the import beside the install dialog import (line ~5):

```typescript
import { InstallChatterboxDialog } from "@/components/InstallChatterboxDialog";
import { DownloadModelDialog } from "@/components/DownloadModelDialog";
```

Add state next to `installEngineOpen` (line ~70):

```typescript
  const [installEngineOpen, setInstallEngineOpen] = useState(false);
  const [downloadEngine, setDownloadEngine] = useState<string | null>(null);
```

Pass the handler to `ActionBar` (after `onInstallEngine={...}`, line ~573):

```tsx
          onInstallEngine={() => setInstallEngineOpen(true)}
          onDownloadEngine={(name) => setDownloadEngine(name)}
```

Render the dialog beside the install dialog (after the `installEngineOpen` block, line ~676):

```tsx
        {downloadEngine && (
          <DownloadModelDialog
            isDark={isDark}
            engineName={downloadEngine}
            displayName={
              engines.find((e) => e.name === downloadEngine)?.display_name ??
              downloadEngine
            }
            onClose={() => setDownloadEngine(null)}
            onDone={async () => {
              const name = downloadEngine;
              await refreshEngines();
              try {
                await setActiveEngine(name);
                await ensureEngineLoaded(name);
              } catch (err) {
                showError(err, "Engine load failed");
              }
              setDownloadEngine(null);
            }}
          />
        )}
```

- [ ] **Step 4: Typecheck the whole frontend**

Run: `cd frontend && npm run typecheck`
Expected: PASS (no errors). If `setActiveEngine`/`ensureEngineLoaded`/`refreshEngines`/`engines`/`showError` are reported undefined, confirm their exact in-scope names in `App.tsx` (they are the same identifiers used by `onSelectEngine`, `onLoadEngine`, and the existing `InstallChatterboxDialog onInstalled` handler) and match them.

- [ ] **Step 5: Build to confirm a clean production bundle**

Run: `cd frontend && npm run build`
Expected: PASS (tsc + vite build succeed).

- [ ] **Step 6: Commit**

```bash
git add frontend/src/components/EngineSelector.tsx frontend/src/components/ActionBar.tsx frontend/src/App.tsx
git commit -m "feat: wire model-download dialog into the engine selector"
```

---

## Final verification

- [ ] **Backend suite green:** `cd backend && python -m pytest tests/ -q` → all pass.
- [ ] **Frontend typecheck + build green:** `cd frontend && npm run typecheck && npm run build` → both pass.
- [ ] **Manual smoke (optional, needs a machine without VibeVoice weights):** start `python studio.py start --dev`, open the engine menu — VibeVoice shows **Download VibeVoice**; clicking it opens the confirm step ("~5.4 GB"), Download starts the progress bar with %/speed/ETA + log, and on completion the engine switches and loads. Kokoro behaves the same with "~350 MB". Chatterbox still shows its **Install** flow unchanged.
- [ ] **Update `CLAUDE.md`** if the engine-abstraction or API section needs the new `downloaded` flag / `/download` endpoints noted (per the maintain-CLAUDE.md memory).

---

## Self-Review (completed by plan author)

**Spec coverage:**
- In-process background download w/ tqdm callback → Task 3 (`_default_runner`, `_ProgressTqdm`). ✓
- `downloaded` flag + `model_cache.py` detection → Tasks 1–2. ✓
- GET/POST `/download` guarded to vibevoice/kokoro → Task 5. ✓
- `DownloadModelDialog` (confirm → progress bar + %/speed/ETA + log) → Task 7. ✓
- EngineSelector branch + proceed-to-switch-on-done → Task 8. ✓
- Types/api client → Task 6. ✓
- Tests: state machine, progress math, tqdm filtering, detection, API guard → Tasks 1,3,4,5; frontend via typecheck/build → Tasks 6–8. ✓
- Chatterbox untouched (downloaded defaults True) → Task 2 default + Task 5 guard. ✓

**Placeholder scan:** none — every step carries full code/commands.

**Type consistency:** snapshot keys (`engine/state/percent/downloaded_bytes/total_bytes/speed_bps/eta_sec/current_file/log/error/returncode`) are identical across `ModelDownloader._snapshot_locked` (Task 3), `DownloadStatusModel` (Task 5), and the TS `DownloadStatus` (Task 6). `downloaded` is consistent across engine `info()` (Task 2), `EngineInfoModel` (Task 5), and TS `EngineInfo` (Task 6). Prop names `onDownload`/`onDownloadEngine` consistent across EngineSelector/ActionBar/App (Task 8).
