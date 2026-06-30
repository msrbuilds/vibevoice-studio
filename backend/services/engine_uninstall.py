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

#: Only these three engines have an isolated venv to remove.
UNINSTALLABLE: frozenset[str] = frozenset({"chatterbox", "omnivoice", "voxcpm"})

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
