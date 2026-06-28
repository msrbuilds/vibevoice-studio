# Non-Blocking Startup Engine Warm-up — Design

**Date:** 2026-06-28
**Status:** Approved (pending spec review)

## Problem

On startup, `app.py`'s `lifespan` calls `EngineManager.ensure_active_loaded()` **synchronously on the event loop** before yielding, so uvicorn doesn't serve until the active engine finishes loading. It already catches load *failures* (logs "degraded mode"), but a load that **hangs** never returns — so the server never reaches "ready."

This bit hard with OmniVoice: it runs in an out-of-process worker, and on restart (with OmniVoice as the persisted active engine) the worker load blocked startup. Worse, because the first backend stalled in `lifespan` *before* binding/serving the port, a second `studio.py start` slipped past the port guard, and the two OmniVoice workers deadlocked over the GPU — a full wedge.

## Goal

Make the active-engine warm-up **non-blocking**: the server serves immediately, the engine pre-warms in the background, and a slow or hanging load can never wedge startup. A concurrent first request must not be able to double-spawn the out-of-process worker.

## Scope

**In scope:**
- `lifespan` warms the active engine on a daemon thread instead of blocking the event loop.
- A per-engine load lock on the out-of-process proxy engines (OmniVoice, Chatterbox) so the warm-up thread and a concurrent first request can't double-spawn the worker.

**Out of scope:**
- Hardening the duplicate-start guard (the original "fix B" — PID/lock file). The wedge's *enabler* (startup stalling before the port binds) is removed by this change, so the cascade can't recur from this path; a separate lock-file guard can be its own task if desired.
- A load guard for in-process engines (VibeVoice/Kokoro). Their `load()` double-call risk is lower (no subprocess to leak) and pre-existing; not addressed here.
- Changing whether the engine pre-warms at all (we keep eager warm-up — just off the startup path).

## Components

### 1. `backend/app.py` — background warm-up

Extract a small, testable module-level helper:

```python
def _warmup_active_engine(em: "EngineManager") -> None:
    """Load the active engine; swallow + log any failure (incl. a hang that
    later errors). Runs on a background thread so startup never blocks on it."""
    try:
        em.ensure_active_loaded()
    except Exception:  # noqa: BLE001
        log.exception("Active engine failed to warm up; first use will retry.")


def _start_background_warmup(em: "EngineManager") -> threading.Thread:
    """Start `_warmup_active_engine` on a daemon thread and return it."""
    t = threading.Thread(target=_warmup_active_engine, args=(em,),
                         name="engine-warmup", daemon=True)
    t.start()
    return t
```

`lifespan` changes from a blocking call to:

```python
    async def lifespan(app: FastAPI):
        em: EngineManager = app.state.engine_manager
        warmup = _start_background_warmup(em)   # returns immediately
        try:
            yield
        finally:
            # Let an in-flight warm-up settle briefly so we don't unload
            # mid-load; if it's hung, proceed anyway (daemon thread).
            warmup.join(timeout=2.0)
            for engine in em.list_engines():
                try:
                    engine.unload()
                except Exception:  # noqa: BLE001
                    log.exception("Engine unload failed for %s", engine.name)
```

(The current inline `try/except em.ensure_active_loaded()` is replaced by the helper call.)

### 2. Proxy engines — load lock

`backend/core/engines/omnivoice_engine.py` and `backend/core/engines/chatterbox_engine.py` are out-of-process proxies whose `load()` spawns a worker subprocess. Today `load()` starts with `if self.is_loaded(): return`, but two threads can both pass that check and each spawn a worker (the double-spawn that caused the GPU deadlock). Fix with a dedicated load lock:

- In `__init__`, add `self._load_lock = threading.Lock()` (separate from the existing `self._lock` used by `_exchange`, so no re-entrancy/deadlock).
- Wrap the body of `load()` in `with self._load_lock:` and keep the `if self.is_loaded(): return` check **inside** the lock, so the second caller short-circuits after the first finishes.

`unload()` is unchanged; on shutdown the `lifespan` `join(timeout)` makes unloading-mid-load rare, and if it does occur the proxy's existing `_kill`/`_exchange` locking + the worker-closed handling already cope (the warm thread's `load()` just errors and is logged).

## Data flow

1. Restart → `lifespan` starts the warm-up thread and yields → uvicorn binds + serves immediately ("Application startup complete").
2. The warm-up thread calls `ensure_active_loaded()` → for OmniVoice, the worker spawns **once** (under the load lock) and warms.
3. A generation arriving before warm-up finishes calls `engine.load()`; it blocks on the load lock until the warm-up's load completes, then sees `is_loaded()` true and returns — no second worker.
4. A hung load stays inside the daemon thread; the server keeps serving (health, engine switch, etc.).

## Error handling

- **Hanging load:** confined to the daemon thread; server unaffected (wedge removed).
- **Failed load:** logged; engine stays unloaded; first real use retries via the normal lazy-load path (unchanged behavior).
- **Shutdown during warm-up:** `join(timeout=2.0)` then unload; the proxy tolerates a kill mid-load.

## Testing

- **`_start_background_warmup` / `_warmup_active_engine`** (new `backend/tests/test_app_warmup.py`):
  - With a fake `em` whose `ensure_active_loaded` blocks on a `threading.Event`: `_start_background_warmup` returns promptly with the thread still alive (not joined); set the event and the thread completes, having called `ensure_active_loaded` once.
  - With a fake `em` whose `ensure_active_loaded` raises: `_warmup_active_engine` swallows it (no exception propagates); the thread completes.
- **Proxy load lock** (append to `backend/tests/test_omnivoice_proxy.py`, and the Chatterbox equivalent in `test_chatterbox_proxy.py`):
  - Two threads, released by a `threading.Barrier`, both call `eng.load()`; assert the worker `subprocess.Popen` was invoked **exactly once** (monkeypatch-count `…engines.omnivoice_engine.subprocess.Popen`) and `eng.is_loaded()` is true afterward; then `eng.unload()`.
  - A simpler idempotency check: a second sequential `load()` does not replace `eng._proc`.

## Out of scope / non-goals

- Lock-file/PID duplicate-start guard (separate optional task).
- In-process-engine load locking.
- Removing eager warm-up (we keep it, just non-blocking).
