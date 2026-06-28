# Non-Blocking Startup Engine Warm-up Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace the blocking engine eager-load in `lifespan` with a daemon-thread background warm-up, and add a per-engine load lock to the two out-of-process proxy engines so a concurrent first request can never double-spawn their worker.

**Architecture:** Two module-level helpers (`_warmup_active_engine`, `_start_background_warmup`) are extracted from the lifespan; `lifespan` starts the warm-up thread and yields immediately. Each proxy engine (`OmniVoiceEngine`, `ChatterboxEngine`) gains a `_load_lock` (separate from the existing `_lock` used by `_exchange`) so that two callers entering `load()` simultaneously only spawn one worker subprocess — the second caller blocks until the first finishes, then sees `is_loaded()` true and returns.

**Tech Stack:** Python stdlib (`threading`), FastAPI lifespan, existing pytest fixtures (stub worker scripts).

---

## File Map

| Action | File | What changes |
|--------|------|--------------|
| Modify | `backend/core/engines/omnivoice_engine.py` | Add `self._load_lock` in `__init__`; wrap `load()` body in `with self._load_lock:` |
| Modify | `backend/core/engines/chatterbox_engine.py` | Same pattern as OmniVoice |
| Modify | `backend/app.py` | Add `import threading`; extract `_warmup_active_engine` + `_start_background_warmup` at module level; replace blocking call in `lifespan` with background thread + bounded shutdown join |
| Create | `backend/tests/test_app_warmup.py` | 3 tests: warmup returns promptly, exception swallowed, ensure_active_loaded called once |
| Modify | `backend/tests/test_omnivoice_proxy.py` | Add 2 tests: concurrent load calls Popen once, sequential load idempotent |
| Modify | `backend/tests/test_chatterbox_proxy.py` | Add 2 tests: same as OmniVoice equivalents |

---

## Task 1: OmniVoice proxy load lock

**Files:**
- Modify: `backend/core/engines/omnivoice_engine.py` (lines 58–106)
- Modify: `backend/tests/test_omnivoice_proxy.py` (append)

- [ ] **Step 1: Write two failing tests** — append to `backend/tests/test_omnivoice_proxy.py`

```python
def test_concurrent_load_calls_popen_once(tmp_path, monkeypatch):
    """Two threads calling load() simultaneously must spawn exactly one worker."""
    import threading
    import subprocess as _subprocess

    popen_count = [0]
    real_popen = _subprocess.Popen

    def counting_popen(*args, **kwargs):
        popen_count[0] += 1
        return real_popen(*args, **kwargs)

    monkeypatch.setattr(
        "backend.core.engines.omnivoice_engine.subprocess.Popen",
        counting_popen,
    )

    eng = _make_stub_engine(tmp_path)
    barrier = threading.Barrier(2)

    def load_with_barrier():
        barrier.wait()
        eng.load()

    threads = [threading.Thread(target=load_with_barrier) for _ in range(2)]
    for t in threads:
        t.start()
    for t in threads:
        t.join(timeout=15.0)

    assert popen_count[0] == 1
    assert eng.is_loaded() is True
    eng.unload()


def test_sequential_load_idempotent(tmp_path):
    """A second sequential load() reuses the existing worker proc."""
    eng = _make_stub_engine(tmp_path)
    eng.load()
    first_proc = eng._proc
    eng.load()
    assert eng._proc is first_proc
    eng.unload()
```

- [ ] **Step 2: Run tests to verify they fail**

Run from repo root:
```bash
cd backend && ./venv/Scripts/python.exe -m pytest tests/test_omnivoice_proxy.py::test_concurrent_load_calls_popen_once tests/test_omnivoice_proxy.py::test_sequential_load_idempotent -v
```
Expected: Both FAILs. `test_concurrent_load_calls_popen_once` fails because popen_count is 2 (no lock yet). `test_sequential_load_idempotent` may pass already (the early-return `if self.is_loaded(): return` is not inside a lock, but sequential calls may accidentally pass); both need to pass with the lock in place.

- [ ] **Step 3: Add `_load_lock` in `OmniVoiceEngine.__init__`**

In `backend/core/engines/omnivoice_engine.py`, in `__init__` (around line 72), add `self._load_lock` directly after `self._lock`:

```python
        self._proc: subprocess.Popen | None = None
        self._lock = threading.Lock()
        self._load_lock = threading.Lock()          # ← ADD THIS LINE
        self._stderr_tail: collections.deque[str] = collections.deque(maxlen=200)
        self._stderr_thread: threading.Thread | None = None
```

- [ ] **Step 4: Wrap `load()` body in `with self._load_lock:`**

Replace the existing `load()` method body (lines 77–106). The `if self.is_loaded(): return` guard moves **inside** the lock:

```python
    def load(self) -> None:
        with self._load_lock:
            if self.is_loaded():
                return
            if not self._worker_python.is_file():
                raise RuntimeError(
                    "OmniVoice isn't installed in its isolated environment. "
                    "Run `python studio.py install-omnivoice` (or click Install in the UI)."
                )
            device = self._device_request
            if device == "auto":
                device = "cuda"
            env = dict(os.environ)
            models_dir = _BACKEND_ROOT / "models"
            env["HF_HOME"] = str(models_dir)
            env["HUGGINGFACE_HUB_CACHE"] = str(models_dir / "hub")
            log.info("Spawning OmniVoice worker: %s %s", self._worker_python, self._worker_script)
            self._proc = subprocess.Popen(
                [str(self._worker_python), str(self._worker_script)],
                stdin=subprocess.PIPE,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                env=env,
            )
            self._start_stderr_drain()
            resp = self._exchange({"op": "load", "device": device, "model_id": self._model_id})
            if not resp.get("ok"):
                err = resp.get("error", "unknown error")
                self._kill()
                raise RuntimeError(f"OmniVoice worker failed to load: {err}")
```

- [ ] **Step 5: Run tests to verify they pass**

```bash
cd backend && ./venv/Scripts/python.exe -m pytest tests/test_omnivoice_proxy.py -v
```
Expected: ALL PASS (including the two new tests and all previously-passing tests).

- [ ] **Step 6: Commit**

```bash
git add backend/core/engines/omnivoice_engine.py backend/tests/test_omnivoice_proxy.py
git commit -m "feat: add _load_lock to OmniVoiceEngine to prevent double worker spawn"
```

---

## Task 2: Chatterbox proxy load lock

**Files:**
- Modify: `backend/core/engines/chatterbox_engine.py` (lines 84–132)
- Modify: `backend/tests/test_chatterbox_proxy.py` (append)

- [ ] **Step 1: Write two failing tests** — append to `backend/tests/test_chatterbox_proxy.py`

```python
def test_concurrent_load_calls_popen_once(tmp_path, monkeypatch):
    """Two threads calling load() simultaneously must spawn exactly one worker."""
    import threading
    import subprocess as _subprocess

    popen_count = [0]
    real_popen = _subprocess.Popen

    def counting_popen(*args, **kwargs):
        popen_count[0] += 1
        return real_popen(*args, **kwargs)

    monkeypatch.setattr(
        "backend.core.engines.chatterbox_engine.subprocess.Popen",
        counting_popen,
    )

    eng = _make_stub_engine(tmp_path)
    barrier = threading.Barrier(2)

    def load_with_barrier():
        barrier.wait()
        eng.load()

    threads = [threading.Thread(target=load_with_barrier) for _ in range(2)]
    for t in threads:
        t.start()
    for t in threads:
        t.join(timeout=15.0)

    assert popen_count[0] == 1
    assert eng.is_loaded() is True
    eng.unload()


def test_sequential_load_idempotent(tmp_path):
    """A second sequential load() reuses the existing worker proc."""
    eng = _make_stub_engine(tmp_path)
    eng.load()
    first_proc = eng._proc
    eng.load()
    assert eng._proc is first_proc
    eng.unload()
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
cd backend && ./venv/Scripts/python.exe -m pytest tests/test_chatterbox_proxy.py::test_concurrent_load_calls_popen_once tests/test_chatterbox_proxy.py::test_sequential_load_idempotent -v
```
Expected: Both FAILs (no lock yet).

- [ ] **Step 3: Add `_load_lock` in `ChatterboxEngine.__init__`**

In `backend/core/engines/chatterbox_engine.py`, in `__init__` (around line 93), add `self._load_lock` directly after `self._lock`:

```python
        self._proc: subprocess.Popen | None = None
        self._lock = threading.Lock()
        self._load_lock = threading.Lock()          # ← ADD THIS LINE
        # stderr is drained on a background thread so a chatty worker
```

- [ ] **Step 4: Wrap `load()` body in `with self._load_lock:`**

Replace the existing `load()` method (lines 103–132):

```python
    def load(self) -> None:
        with self._load_lock:
            if self.is_loaded():
                return
            if not self._worker_python.is_file():
                raise RuntimeError(
                    "Chatterbox isn't installed in its isolated environment. "
                    "Run `python studio.py models` and select Chatterbox."
                )
            device = self._device_request
            if device == "auto":
                device = "cuda"
            env = dict(os.environ)
            models_dir = _BACKEND_ROOT / "models"
            env["HF_HOME"] = str(models_dir)
            env["HUGGINGFACE_HUB_CACHE"] = str(models_dir / "hub")
            log.info("Spawning Chatterbox worker: %s %s", self._worker_python, self._worker_script)
            self._proc = subprocess.Popen(
                [str(self._worker_python), str(self._worker_script)],
                stdin=subprocess.PIPE,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                env=env,
            )
            self._start_stderr_drain()
            resp = self._exchange({"op": "load", "device": device})
            if not resp.get("ok"):
                err = resp.get("error", "unknown error")
                self._kill()
                raise RuntimeError(f"Chatterbox worker failed to load: {err}")
```

- [ ] **Step 5: Run tests to verify they pass**

```bash
cd backend && ./venv/Scripts/python.exe -m pytest tests/test_chatterbox_proxy.py -v
```
Expected: ALL PASS.

- [ ] **Step 6: Commit**

```bash
git add backend/core/engines/chatterbox_engine.py backend/tests/test_chatterbox_proxy.py
git commit -m "feat: add _load_lock to ChatterboxEngine to prevent double worker spawn"
```

---

## Task 3: Background warm-up in app.py

**Files:**
- Modify: `backend/app.py`
- Create: `backend/tests/test_app_warmup.py`

- [ ] **Step 1: Write three failing tests** — create `backend/tests/test_app_warmup.py`

```python
"""Tests for the non-blocking startup engine warm-up helpers in app.py."""

import sys
import threading
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT))

import pytest  # noqa: E402

from backend.app import _start_background_warmup, _warmup_active_engine  # noqa: E402


class _BlockingEM:
    """Fake EngineManager whose ensure_active_loaded blocks until an Event."""

    def __init__(self):
        self._event = threading.Event()
        self.call_count = 0

    def ensure_active_loaded(self):
        self.call_count += 1
        self._event.wait()

    def release(self):
        self._event.set()


class _RaisingEM:
    """Fake EngineManager whose ensure_active_loaded always raises."""

    def ensure_active_loaded(self):
        raise RuntimeError("simulated load failure")


class _CountingEM:
    """Fake EngineManager that counts ensure_active_loaded calls."""

    def __init__(self):
        self.call_count = 0

    def ensure_active_loaded(self):
        self.call_count += 1


def test_start_background_warmup_returns_promptly():
    """_start_background_warmup returns while the warm-up thread is still alive."""
    em = _BlockingEM()
    thread = _start_background_warmup(em)

    # Thread started but its ensure_active_loaded is still blocking
    assert thread.is_alive() is True

    # Release the block; thread should complete
    em.release()
    thread.join(timeout=5.0)
    assert thread.is_alive() is False
    assert em.call_count == 1


def test_warmup_swallows_exception():
    """_warmup_active_engine swallows load failures without propagating."""
    # Must not raise
    _warmup_active_engine(_RaisingEM())


def test_warmup_calls_ensure_active_loaded_once():
    """_warmup_active_engine calls ensure_active_loaded exactly once."""
    em = _CountingEM()
    _warmup_active_engine(em)
    assert em.call_count == 1
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
cd backend && ./venv/Scripts/python.exe -m pytest tests/test_app_warmup.py -v
```
Expected: FAIL with `ImportError: cannot import name '_start_background_warmup' from 'backend.app'`.

- [ ] **Step 3: Add `import threading` to `backend/app.py`**

In `backend/app.py`, add `import threading` in the stdlib imports block (after `import logging`, before `from contextlib`):

```python
import logging
import threading
from contextlib import asynccontextmanager
from pathlib import Path
from typing import AsyncIterator
```

- [ ] **Step 4: Add `_warmup_active_engine` and `_start_background_warmup` at module level in `backend/app.py`**

Insert these two functions immediately before the `create_app` function (after the `log = logging.getLogger(__name__)` line, before `def _configure_logging`). Or more precisely, place them right before `def create_app(settings: Settings | None = None) -> FastAPI:` so `log` and `EngineManager` are both already in scope:

```python
def _warmup_active_engine(em: EngineManager) -> None:
    """Load the active engine; swallow + log any failure.

    Runs on a background thread so startup never blocks on it.
    """
    try:
        em.ensure_active_loaded()
    except Exception:  # noqa: BLE001
        log.exception("Active engine failed to warm up; first use will retry.")


def _start_background_warmup(em: EngineManager) -> threading.Thread:
    """Start _warmup_active_engine on a daemon thread and return it."""
    t = threading.Thread(
        target=_warmup_active_engine,
        args=(em,),
        name="engine-warmup",
        daemon=True,
    )
    t.start()
    return t
```

- [ ] **Step 5: Replace the blocking call in `lifespan` with the background warm-up**

In `backend/app.py`, inside `create_app`, replace the existing `lifespan` function:

**Before:**
```python
    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        # Eager load the active engine so /api/health is honest on first hit.
        em: EngineManager = app.state.engine_manager
        try:
            em.ensure_active_loaded()
        except Exception:  # noqa: BLE001
            log.exception(
                "Active engine failed to load at startup; serving in degraded mode."
            )
        try:
            yield
        finally:
            # Unload every engine to free VRAM/RAM.
            for engine in em.list_engines():
                try:
                    engine.unload()
                except Exception:  # noqa: BLE001
                    log.exception("Engine unload failed for %s", engine.name)
```

**After:**
```python
    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        em: EngineManager = app.state.engine_manager
        warmup = _start_background_warmup(em)
        try:
            yield
        finally:
            # Give an in-flight warm-up a moment to settle so we don't unload
            # mid-load; if it's hung, proceed anyway (daemon thread).
            warmup.join(timeout=2.0)
            for engine in em.list_engines():
                try:
                    engine.unload()
                except Exception:  # noqa: BLE001
                    log.exception("Engine unload failed for %s", engine.name)
```

- [ ] **Step 6: Run the new tests to verify they pass**

```bash
cd backend && ./venv/Scripts/python.exe -m pytest tests/test_app_warmup.py -v
```
Expected: ALL 3 PASS.

- [ ] **Step 7: Run the full test suite to verify nothing regressed**

```bash
cd backend && ./venv/Scripts/python.exe -m pytest tests/ -v
```
Expected: ALL PASS (previously 91 tests + 7 new = 98 tests). If smoke tests fail because they import `backend.app` at module level and the lifespan now spawns a thread, verify that `TestClient` still handles startup correctly — it should, because `TestClient` with `with` triggers the lifespan normally.

- [ ] **Step 8: Commit**

```bash
git add backend/app.py backend/tests/test_app_warmup.py
git commit -m "feat: non-blocking startup engine warm-up (daemon thread + shutdown join)"
```
