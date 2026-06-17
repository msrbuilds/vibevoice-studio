"""All Pydantic request/response models in one place."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field


# ---- health / config ----

class HealthResponse(BaseModel):
    status: Literal["ok", "loading", "error"]
    model_loaded: bool
    device: str
    version: str = "0.1.0"


class ConfigResponse(BaseModel):
    model_id: str
    device: str
    dtype: str
    attn_implementation: str
    sampling_rate: int
    default_cfg_scale: float
    max_text_chars: int
    voices_dir: str
    uploads_dir: str
    streaming: Literal["planned", "available", "unavailable"] = "planned"


# ---- voices ----

class VoiceInfoModel(BaseModel):
    id: str
    name: str
    gender: str | None = None
    language: str | None = None
    source: Literal["builtin", "upload"]
    size_bytes: int | None = None
    duration_sec: float | None = None
    sample_rate: int | None = None


class VoiceMetaUpdate(BaseModel):
    """Request body for editing name / gender / language. All fields optional."""
    name: str | None = None
    gender: str | None = None
    language: str | None = None


class VoiceListResponse(BaseModel):
    voices: list[VoiceInfoModel]


class UploadVoiceResponse(BaseModel):
    id: str
    name: str
    size_bytes: int
    duration_sec: float
    sample_rate: int


class ErrorResponse(BaseModel):
    detail: str
    code: str | None = None


# ---- synthesize ----

class SynthSpeakerModel(BaseModel):
    name: str = Field(..., min_length=1, max_length=64)
    voice: str = Field(..., min_length=1, description="Voice id (filename stem) to use for this speaker")


class SynthRequestBody(BaseModel):
    text: str = Field(..., min_length=1, description="Script text. If it doesn't contain 'Speaker N:' lines, it's wrapped as a single-speaker script using speakers[0].")
    speakers: list[SynthSpeakerModel] = Field(..., min_length=1, max_length=4, description="Speakers used in the script, in order of first appearance (1..N)")
    cfg_scale: float | None = None
    inference_steps: int | None = Field(default=None, ge=1, le=100)
    disable_prefill: bool = False
    # When True, bypass the per-segment cache and re-run the model.
    # Used by the UI's "regenerate" button to force a fresh take even when
    # text+voice+cfg haven't changed.
    force_regenerate: bool = False


class SynthBase64Response(BaseModel):
    audio_b64: str
    sample_rate: int
    duration_sec: float
    inference_ms: int
    voice_id: str
