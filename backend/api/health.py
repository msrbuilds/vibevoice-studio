"""Health and config endpoints."""

from __future__ import annotations

from fastapi import APIRouter, Depends

from ..config import Settings, get_settings
from ..core.model import ModelManager
from .deps import get_model_manager
from .schemas import ConfigResponse, HealthResponse

router = APIRouter(tags=["health"])


@router.get("/api/health", response_model=HealthResponse)
def health(mm: ModelManager = Depends(get_model_manager)) -> HealthResponse:
    return HealthResponse(
        status="ok" if mm.is_loaded else "loading",
        model_loaded=mm.is_loaded,
        device=mm.device_name,
    )


@router.get("/api/config", response_model=ConfigResponse)
def config(
    mm: ModelManager = Depends(get_model_manager),
    settings: Settings = Depends(get_settings),
) -> ConfigResponse:
    return ConfigResponse(
        model_id=mm.model_id if mm.is_loaded else settings.model_id,
        device=mm.device_name if mm.is_loaded else settings.device,
        # dtype / sampling_rate only meaningful after load; fall back to None-safe values
        dtype=mm.dtype_name if mm.is_loaded else "unknown",
        attn_implementation=mm.attn_impl if mm.is_loaded else "unknown",
        sampling_rate=mm.sampling_rate if mm.is_loaded else 24000,
        default_cfg_scale=settings.default_cfg_scale,
        max_text_chars=settings.max_text_chars,
        voices_dir=str(settings.voices_dir),
        uploads_dir=str(settings.uploads_dir),
    )
