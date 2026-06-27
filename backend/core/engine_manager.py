"""EngineManager: registry of available TTS engines and the active one.

Only one engine is loaded at a time to keep memory footprint low
(VibeVoice 1.5B is ~6 GB VRAM; Kokoro is ~350 MB; both at once is
wasteful for a local dev tool).

The active engine name is persisted in `backend/.last_engine` so the
backend re-activates the user's last choice on restart. A missing file
falls back to the default (VibeVoice).
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any

from .engines import Engine
from .engines.chatterbox_engine import ChatterboxEngine
from .engines.kokoro_engine import KokoroEngine
from .engines.omnivoice_engine import OmniVoiceEngine
from .engines.vibevoice_engine import VibeVoiceEngine

log = logging.getLogger(__name__)


class EngineNotFound(KeyError):
    """Raised when an unknown engine name is requested."""

    def __init__(self, name: str) -> None:
        super().__init__(name)
        self.name = name


class EngineLoadError(RuntimeError):
    """Raised when an engine fails to load (e.g. missing dep, OOM)."""


class EngineManager:
    """Owns the set of available engines and tracks the active one.

    Constructor signature mirrors what the previous app.py needed; the
    actual load() of the active engine is lazy (deferred to first
    synthesize call) so the server starts fast and only pays the model
    load cost when actually used.
    """

    _STATE_FILENAME = ".last_engine"

    def __init__(
        self,
        *,
        default_engine: str,
        voices_dir: Path,
        uploads_dir: Path,
        model_id: str,
        device_request: str,
        max_text_chars: int = 5000,
        default_cfg_scale: float = 1.3,
        kokoro_lang_code: str = "a",
        chatterbox_model_id: str = "ResembleAI/chatterbox",
        chatterbox_default_language_id: str = "en",
        chatterbox_default_cfg_weight: float = 0.5,
        chatterbox_default_exaggeration: float = 0.5,
        chatterbox_watermark: bool = True,
        omnivoice_model_id: str = "k2-fsa/OmniVoice",
        omnivoice_num_step: int = 32,
        state_dir: Path | None = None,
    ) -> None:
        self._voices_dir = Path(voices_dir)
        self._uploads_dir = Path(uploads_dir)
        self._state_dir = Path(state_dir) if state_dir else self._voices_dir.parent
        self._state_path = self._state_dir / self._STATE_FILENAME

        # Build the engine registry. Add new engines here as we support
        # them. Order matters for the UI selector.
        self._engines: dict[str, Engine] = {
            "vibevoice": VibeVoiceEngine(
                model_id=model_id,
                device_request=device_request,
                max_text_chars=max_text_chars,
                default_cfg_scale=default_cfg_scale,
            ),
            "kokoro": KokoroEngine(default_lang_code=kokoro_lang_code),
            "chatterbox": ChatterboxEngine(
                model_id=chatterbox_model_id,
                default_language_id=chatterbox_default_language_id,
                default_cfg_weight=chatterbox_default_cfg_weight,
                default_exaggeration=chatterbox_default_exaggeration,
                watermark=chatterbox_watermark,
                device_request=device_request,
            ),
            "omnivoice": OmniVoiceEngine(
                model_id=omnivoice_model_id,
                device_request=device_request,
                num_step=omnivoice_num_step,
            ),
        }

        # Decide which engine to activate. Priority:
        #   1. Persisted last-engine file (if present and the engine exists)
        #   2. default_engine argument
        chosen = self._read_persisted_engine() or default_engine
        if chosen not in self._engines:
            log.warning(
                "Persisted engine %r is not registered; falling back to %r",
                chosen,
                default_engine,
            )
            chosen = default_engine
        self._active_name: str = chosen
        log.info("EngineManager active engine: %s (default %s)", self._active_name, default_engine)

    # -- public API
    @property
    def active_engine(self) -> Engine:
        return self._engines[self._active_name]

    @property
    def active_name(self) -> str:
        return self._active_name

    def list_engines(self) -> list[Engine]:
        return list(self._engines.values())

    def get_engine(self, name: str) -> Engine:
        if name not in self._engines:
            raise EngineNotFound(name)
        return self._engines[name]

    def activate(self, name: str) -> Engine:
        """Switch the active engine. Unloads the current one.

        The new engine is NOT loaded here — that happens lazily on the
        next synthesize call. If you want eager loading, call
        `engine_manager.active_engine.load()` afterwards.
        """
        if name not in self._engines:
            raise EngineNotFound(name)
        if name == self._active_name:
            return self._engines[name]
        log.info("Switching active engine: %s -> %s", self._active_name, name)
        # Free the old engine's resources.
        try:
            self._engines[self._active_name].unload()
        except Exception:  # noqa: BLE001
            log.exception("Engine unload failed for %s", self._active_name)
        self._active_name = name
        self._persist_engine(name)
        return self._engines[name]

    def ensure_active_loaded(self) -> None:
        """Eagerly load the active engine. Catches and wraps exceptions."""
        engine = self.active_engine
        if engine.is_loaded():
            return
        try:
            engine.load()
        except Exception as exc:  # noqa: BLE001
            raise EngineLoadError(
                f"Failed to load engine {engine.name!r}: {exc}"
            ) from exc

    def info(self) -> list[dict[str, Any]]:
        """Public info for the /api/engines endpoint."""
        engines_info: list[dict[str, Any]] = []
        for eng in self._engines.values():
            engines_info.append({**eng.info(), "name": eng.name, "active": eng.name == self._active_name})
        return engines_info

    # -- internal helpers
    def _read_persisted_engine(self) -> str | None:
        try:
            if not self._state_path.is_file():
                return None
            name = self._state_path.read_text(encoding="utf-8").strip()
            return name or None
        except OSError as exc:
            log.warning("Could not read %s: %s", self._state_path, exc)
            return None

    def _persist_engine(self, name: str) -> None:
        try:
            self._state_dir.mkdir(parents=True, exist_ok=True)
            self._state_path.write_text(name + "\n", encoding="utf-8")
        except OSError as exc:
            log.warning("Could not persist engine choice to %s: %s", self._state_path, exc)
