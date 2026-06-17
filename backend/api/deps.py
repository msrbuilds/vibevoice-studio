"""FastAPI dependency providers for app.state singletons."""

from __future__ import annotations

from fastapi import Request

from ..core.model import ModelManager
from ..services.join_cache import JoinCache
from ..services.synth_cache import SynthCache
from ..services.synthesize import SynthService
from ..services.voices import VoiceRegistry


def get_model_manager(request: Request) -> ModelManager:
    return request.app.state.model_manager  # type: ignore[no-any-return]


def get_voice_registry(request: Request) -> VoiceRegistry:
    return request.app.state.voice_registry  # type: ignore[no-any-return]


def get_synth_service(request: Request) -> SynthService:
    return request.app.state.synth_service  # type: ignore[no-any-return]


def get_synth_cache(request: Request) -> SynthCache:
    return request.app.state.synth_cache  # type: ignore[no-any-return]


def get_join_cache(request: Request) -> JoinCache:
    return request.app.state.join_cache  # type: ignore[no-any-return]
