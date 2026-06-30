"""Health and config endpoints."""

from __future__ import annotations

from fastapi import APIRouter, Depends

from ..config import Settings, get_settings
from ..core.engine_manager import EngineManager
from ..core.model import ModelManager
from ..core.version import get_version
from .deps import get_engine_manager, get_model_manager
from .schemas import ConfigResponse, EngineInfoModel, HealthResponse

router = APIRouter(tags=["health"])


@router.get("/api/health", response_model=HealthResponse)
def health(
    em: EngineManager = Depends(get_engine_manager),
) -> HealthResponse:
    """Liveness probe. Returns 200 when the active engine is loaded."""
    engine = em.active_engine
    info = engine.engine_info()
    return HealthResponse(
        status="ok" if engine.is_loaded() else "loading",
        model_loaded=engine.is_loaded(),
        device=info.get("device", "unknown"),
        version=get_version(),
    )


@router.get("/api/config", response_model=ConfigResponse)
def config(
    em: EngineManager = Depends(get_engine_manager),
    mm: ModelManager | None = Depends(get_model_manager),
    settings: Settings = Depends(get_settings),
) -> ConfigResponse:
    """Server-wide configuration + active engine's runtime details.

    `model_id`, `device`, `dtype`, `attn_implementation`, and
    `sampling_rate` reflect the *active* engine. When the active engine
    is VibeVoice, we source those from its ModelManager directly (the
    most accurate values). For other engines, we delegate to the
    engine's `engine_info()` method, which each engine overrides with
    its own honest values (or "unknown" if it doesn't track them).
    """
    engine = em.active_engine
    if engine.name == "vibevoice" and mm is not None and mm.is_loaded:
        device_name = mm.device_name
        dtype_name = mm.dtype_name
        attn_impl = mm.attn_impl
        sample_rate = mm.sampling_rate
        model_id = mm.model_id
    else:
        info = engine.engine_info()
        device_name = info["device"]
        dtype_name = info["dtype"]
        attn_impl = info["attn_implementation"]
        sample_rate = engine.sample_rate() if engine.is_loaded() else 0
        model_id = info["model_id"]

    return ConfigResponse(
        version=get_version(),
        model_id=model_id,
        device=device_name,
        dtype=dtype_name,
        attn_implementation=attn_impl,
        sampling_rate=sample_rate,
        default_cfg_scale=settings.default_cfg_scale,
        max_text_chars=settings.max_text_chars,
        voices_dir=str(settings.voices_dir),
        uploads_dir=str(settings.uploads_dir),
        active_engine=em.active_name,
        engines=[
            EngineInfoModel(
                name=info["name"],
                display_name=info["display_name"],
                description=info["description"],
                license=info.get("license", "unknown"),
                model_url=info.get("model_url", ""),
                loaded=info["loaded"],
                supports_voice_cloning=info["supports_voice_cloning"],
                supports_streaming=info.get("supports_streaming", False),
                sample_rate=info.get("sample_rate"),
                max_speakers=info["max_speakers"],
                default_cfg_scale=info["default_cfg_scale"],
                active=info.get("active", False),
                supports_voice_modes=info.get("supports_voice_modes", False),
                supports_style_clone=info.get("supports_style_clone", False),
                supports_style_prompt=info.get("supports_style_prompt", False),
            )
            for info in em.info()
        ],
    )