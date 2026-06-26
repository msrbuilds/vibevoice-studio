"""Background installer for the isolated Chatterbox environment.

Runs `python studio.py install-chatterbox` in a daemon thread, streaming its
merged stdout/stderr into a capped log buffer. State machine:
    not_installed -> installing -> installed | error

The subprocess runner is injectable (`runner`) so tests don't run real pip.
A runner is a zero-arg callable returning an iterator of (line, returncode):
each output line is yielded as (line, None); the final item is (None, rc).
"""

from __future__ import annotations

import subprocess
import sys
import threading
from pathlib import Path
from typing import Callable, Iterator, Optional, Tuple

_REPO_ROOT = Path(__file__).resolve().parents[2]  # backend/services/.. -> repo root
_MAX_LOG_LINES = 2000

RunnerItem = Tuple[Optional[str], Optional[int]]
Runner = Callable[[], Iterator[RunnerItem]]


def _default_runner(repo_root: Path) -> Iterator[RunnerItem]:
    """Spawn `python studio.py install-chatterbox` and stream its output."""
    proc = subprocess.Popen(
        [sys.executable, "studio.py", "install-chatterbox"],
        cwd=str(repo_root),
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,  # merge so a single stream is drained to EOF
        text=True,
        bufsize=1,
    )
    assert proc.stdout is not None
    for line in proc.stdout:
        yield line.rstrip("\n"), None
    proc.wait()
    yield None, proc.returncode


class ChatterboxInstaller:
    """Thread-safe install state machine for the isolated Chatterbox env."""

    def __init__(self, *, runner: Runner | None = None, repo_root: Path | None = None) -> None:
        self._repo_root = repo_root or _REPO_ROOT
        self._runner: Runner = runner or (lambda: _default_runner(self._repo_root))
        self._lock = threading.Lock()
        self._state = "not_installed"
        self._log: list[str] = []
        self._returncode: int | None = None
        self._thread: threading.Thread | None = None

    def status(self) -> dict:
        with self._lock:
            return {
                "state": self._state,
                "log": list(self._log),
                "returncode": self._returncode,
            }

    def start(self) -> dict:
        with self._lock:
            if self._state == "installing":
                # Already running — coalesce; don't launch a second process.
                return {
                    "state": self._state,
                    "log": list(self._log),
                    "returncode": self._returncode,
                }
            self._state = "installing"
            self._log = []
            self._returncode = None
            self._thread = threading.Thread(target=self._run, daemon=True)
            self._thread.start()
            return {"state": self._state, "log": [], "returncode": None}

    def _run(self) -> None:
        rc: int | None = None
        try:
            for line, code in self._runner():
                if line is not None:
                    with self._lock:
                        self._log.append(line)
                        if len(self._log) > _MAX_LOG_LINES:
                            del self._log[: len(self._log) - _MAX_LOG_LINES]
                if code is not None:
                    rc = code
        except Exception as exc:  # noqa: BLE001
            with self._lock:
                self._log.append(f"[installer error] {exc}")
                self._state = "error"
                self._returncode = -1
            return
        with self._lock:
            self._returncode = rc
            self._state = "installed" if rc == 0 else "error"
