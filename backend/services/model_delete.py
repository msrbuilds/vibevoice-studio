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
DELETABLE: frozenset[str] = frozenset({"vibevoice", "kokoro", "omnivoice", "chatterbox", "voxcpm"})

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
        self._engine: str | None = None
        self._state = "idle"
        self._log: list[str] = []
        self._error: str | None = None
        self._thread: threading.Thread | None = None

    def status(self) -> dict:
        with self._lock:
            return {"engine": self._engine, "state": self._state, "log": list(self._log), "error": self._error}

    def start(self, engine_name: str) -> dict:
        if engine_name not in DELETABLE:
            raise ValueError(f"{engine_name} weights are not deletable")
        with self._lock:
            if self._state == "deleting":
                if self._engine == engine_name:
                    return {"engine": self._engine, "state": self._state, "log": list(self._log), "error": self._error}
                raise ValueError(f"a delete for {self._engine} is already in progress")
            self._engine = engine_name
            self._state = "deleting"
            self._log = []
            self._error = None
            self._thread = threading.Thread(target=self._run, args=(engine_name,), daemon=True)
            self._thread.start()
            return {"engine": self._engine, "state": self._state, "log": [], "error": None}

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
            if target is None:
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
