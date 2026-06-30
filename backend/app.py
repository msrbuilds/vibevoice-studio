"""FastAPI application entrypoint."""

from __future__ import annotations

# Configure the HuggingFace cache BEFORE importing anything that
# touches transformers / kokoro / huggingface_hub. Settings() reads
# models_dir from env / .env, so HF_HOME is set from the configured
# value before the engines load.
import os as _os
from pathlib import Path as _Path

_BACKEND_ROOT = _Path(__file__).resolve().parent
_DEFAULT_MODELS_DIR = _BACKEND_ROOT / "models"
_models_dir = _Path(
    _os.environ.get("MODELS_DIR", str(_DEFAULT_MODELS_DIR))
).expanduser().resolve()

from .core.hf_paths import configure_hf_cache as _configure_hf_cache
_configure_hf_cache(_models_dir)

import logging
import threading
from contextlib import asynccontextmanager
from pathlib import Path
from typing import AsyncIterator

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from .api.cache import router as cache_router
from .api.download import router as download_router
from .api.engines import router as engines_router
from .api.health import router as health_router
from .api.stream import router as stream_router
from .api.synthesize import router as synthesize_router
from .api.voices import router as voices_router
from .config import Settings, get_settings
from .core.engine_manager import EngineManager
from .core.exceptions import BackendError
from .services.chatterbox_install import ChatterboxInstaller, EngineEnvInstaller
from .services.model_download import ModelDownloader
from .services.model_delete import ModelDeleter
from .services.engine_uninstall import EngineEnvUninstaller
from .services.join_cache import JoinCache
from .services.synth_cache import SynthCache
from .services.synthesize import SynthService
from .services.voices import VoiceRegistry

log = logging.getLogger(__name__)


def _configure_logging(level: str) -> None:
    logging.basicConfig(
        level=level.upper(),
        format="%(asctime)s %(levelname)-7s [%(name)s] %(message)s",
    )


def _mount_frontend(app: FastAPI, dist_dir: Path) -> None:
    """Serve the built frontend at / when a Vite build exists.

    No-op in dev mode (no dist). Must be called AFTER the API routers so
    the catch-all static mount never shadows /api/*.
    """
    if not (dist_dir / "index.html").is_file():
        return
    from fastapi.staticfiles import StaticFiles

    app.mount("/", StaticFiles(directory=dist_dir, html=True), name="frontend")


def _warmup_active_engine(em: EngineManager) -> None:
    """Load the active engine; swallow + log any failure.

    Skips engines whose weights aren't downloaded yet so the user sees the
    Download button in the UI rather than a silent background download with
    no progress. Runs on a background thread so startup never blocks on it.
    """
    try:
        engine = em.active_engine
        if not engine.downloaded():
            log.info(
                "Skipping warm-up for %r: weights not in local cache. "
                "Use the Download button in the UI to pre-fetch them.",
                engine.name,
            )
            return
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


def create_app(settings: Settings | None = None) -> FastAPI:
    settings = settings or get_settings()
    # Re-configure HF cache from the resolved settings.models_dir so a
    # .env override (MODELS_DIR=...) or a test override actually wins.
    # Idempotent: safe to call twice.
    _configure_hf_cache(settings.models_dir)
    _configure_logging(settings.log_level)

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

    app = FastAPI(
        title="Multi-engine TTS API",
        version="0.2.0",
        lifespan=lifespan,
    )

    # CORS — permissive for local dev. Tighten in production.
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_credentials=False,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    # ---- state singletons
    voice_registry = VoiceRegistry(
        voices_dir=settings.voices_dir,
        uploads_dir=settings.uploads_dir,
    )
    synth_cache = SynthCache(
        cache_dir=settings.cache_dir,
        enabled=settings.cache_enabled,
        max_entries=settings.cache_max_entries,
    )
    join_cache = JoinCache(synth_cache)

    engine_manager = EngineManager(
        default_engine=settings.default_engine,
        voices_dir=settings.voices_dir,
        uploads_dir=settings.uploads_dir,
        model_id=settings.model_id,
        device_request=settings.device if settings.device != "auto" else "cuda",
        max_text_chars=settings.max_text_chars,
        default_cfg_scale=settings.default_cfg_scale,
        kokoro_lang_code=settings.kokoro_lang_code,
        chatterbox_model_id=settings.chatterbox_model_id,
        chatterbox_default_language_id=settings.chatterbox_default_language_id,
        chatterbox_default_cfg_weight=settings.chatterbox_default_cfg_weight,
        chatterbox_default_exaggeration=settings.chatterbox_default_exaggeration,
        chatterbox_watermark=settings.chatterbox_watermark,
        omnivoice_model_id=settings.omnivoice_model_id,
        omnivoice_num_step=settings.omnivoice_num_step,
        voxcpm_model_id=settings.voxcpm_model_id,
        voxcpm_inference_timesteps=settings.voxcpm_inference_timesteps,
        qwen_model_id=settings.qwen_model_id,
    )

    # Wire each engine's built-in voice catalog into the registry so
    # /api/voices returns a single merged list tagged with `engine`.
    for engine in engine_manager.list_engines():
        try:
            voices = engine.available_voices()
        except Exception:  # noqa: BLE001
            log.exception("Engine %s failed to list built-in voices", engine.name)
            voices = []
        if voices:
            voice_registry.register_engine_voices(engine.name, voices)

    synth_service = SynthService(
        engine_manager=engine_manager,
        voice_registry=voice_registry,
        max_text_chars=settings.max_text_chars,
        synth_timeout_s=settings.synth_timeout_s,
        default_cfg_scale=settings.default_cfg_scale,
        cache=synth_cache,
    )

    # Keep the ModelManager around for direct introspection (the
    # VibeVoiceEngine owns one). It's also exposed via /api/health
    # for the device/dtype fields.
    vibevoice_engine = engine_manager.get_engine("vibevoice")
    model_manager = getattr(vibevoice_engine, "_model_manager", None)

    app.state.settings = settings
    app.state.engine_manager = engine_manager
    app.state.model_manager = model_manager  # legacy field, may be None
    app.state.voice_registry = voice_registry
    app.state.synth_cache = synth_cache
    app.state.join_cache = join_cache
    app.state.synth_service = synth_service
    app.state.engine_installers = {
        "chatterbox": ChatterboxInstaller(),
        "omnivoice": EngineEnvInstaller("install-omnivoice"),
        "voxcpm": EngineEnvInstaller("install-voxcpm"),
        "qwen": EngineEnvInstaller("install-qwen"),
    }
    app.state.model_downloader = ModelDownloader()
    app.state.model_deleter = ModelDeleter(em=engine_manager)
    app.state.engine_uninstallers = {
        "chatterbox": EngineEnvUninstaller("chatterbox", em=engine_manager),
        "omnivoice": EngineEnvUninstaller("omnivoice", em=engine_manager),
        "voxcpm": EngineEnvUninstaller("voxcpm", em=engine_manager),
        "qwen": EngineEnvUninstaller("qwen", em=engine_manager),
    }

    # ---- routers
    app.include_router(health_router)
    app.include_router(engines_router)
    app.include_router(voices_router)
    app.include_router(synthesize_router)
    app.include_router(download_router)
    app.include_router(cache_router)
    app.include_router(stream_router)

    # ---- static frontend (prod mode only; no-op if frontend/dist is absent)
    _frontend_dist = Path(__file__).resolve().parent.parent / "frontend" / "dist"
    _mount_frontend(app, _frontend_dist)

    # ---- exception handlers
    @app.exception_handler(BackendError)
    async def backend_error_handler(_: Request, exc: BackendError) -> JSONResponse:
        return JSONResponse(
            status_code=exc.http_status,
            content={"detail": exc.message, "code": exc.code},
        )

    @app.exception_handler(Exception)
    async def unhandled_exception_handler(request: Request, exc: Exception) -> JSONResponse:
        import traceback
        log.error(
            "Unhandled exception in %s %s:\n%s",
            request.method,
            request.url.path,
            traceback.format_exc(),
        )
        return JSONResponse(
            status_code=500,
            content={
                "detail": f"{type(exc).__name__}: {exc}",
                "code": "internal_error",
            },
        )

    return app


# Module-level instance for `uvicorn backend.app:app`
app = create_app()
