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
DOWNLOADABLE: frozenset[str] = frozenset({"vibevoice", "kokoro", "omnivoice"})

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
                if self._engine == engine:
                    return self._snapshot_locked()  # coalesce onto the same job
                raise ValueError(
                    f"a download for {self._engine} is already in progress"
                )
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

        info = HfApi().model_info(repo_id, files_metadata=True, timeout=10)
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


def _default_runner(repo_id: str, progress: Progress) -> None:
    """Download `repo_id` into the local HF cache with live byte progress.

    huggingface_hub ≥0.36 does NOT propagate ``tqdm_class`` to individual
    file downloads (only to the outer file-count bar), so a tqdm subclass
    cannot intercept byte-level progress. Instead we poll the local blobs
    directory every 0.5 s and push size deltas so the UI bar advances.
    """
    import threading
    from pathlib import Path as _Path

    from huggingface_hub import snapshot_download
    from huggingface_hub.constants import HF_HUB_CACHE

    progress.log(f"Resolving {repo_id} …")
    total = _repo_total_bytes(repo_id)
    if total:
        progress.set_total(total)
        progress.log(f"Total download size: {total / (1024 * 1024):.0f} MB")
    else:
        progress.log("Total size unknown; reporting bytes downloaded.")

    # HF stores blobs (complete + *.incomplete in-progress) at:
    # {HF_HUB_CACHE}/models--{org}--{name}/blobs/
    blobs_dir = (
        _Path(HF_HUB_CACHE)
        / f"models--{repo_id.replace('/', '--')}"
        / "blobs"
    )

    def _dir_bytes(path: _Path) -> int:
        try:
            return sum(f.stat().st_size for f in path.iterdir() if f.is_file())
        except OSError:
            return 0

    # Bytes already cached before this download started (resume scenario).
    baseline = _dir_bytes(blobs_dir)
    if baseline > 0:
        progress.add_bytes(baseline)  # show pre-cached bytes immediately

    _polled: list[int] = [0]  # bytes reported so far via polling (delta from baseline)
    _stop = threading.Event()

    def _poll() -> None:
        while not _stop.is_set():
            _stop.wait(0.5)
            written = _dir_bytes(blobs_dir) - baseline
            delta = written - _polled[0]
            if delta > 0:
                progress.add_bytes(delta)
                _polled[0] = written

    poll_thread = threading.Thread(target=_poll, daemon=True, name="dl-poll")
    poll_thread.start()
    try:
        snapshot_download(repo_id)
        progress.log("Download complete.")
    finally:
        _stop.set()
        poll_thread.join(timeout=2.0)
