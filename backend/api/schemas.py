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
    # Active TTS engine and the full list of available engines.
    active_engine: str | None = None
    engines: list["EngineInfoModel"] = []


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
    # Which TTS engine owns this voice. Optional for backward compat with
    # older clients that don't know about engines.
    engine: str | None = None
    reference_transcript: str | None = None


class VoiceMetaUpdate(BaseModel):
    """Request body for editing name / gender / language. All fields optional."""
    name: str | None = None
    gender: str | None = None
    language: str | None = None
    reference_transcript: str | None = None


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


# ---- engines ----

class EngineLanguageModel(BaseModel):
    code: str
    label: str


class EngineInfoModel(BaseModel):
    name: str
    display_name: str
    description: str = ""
    loaded: bool
    supports_voice_cloning: bool
    supports_streaming: bool = False
    sample_rate: int | None = None
    max_speakers: int
    default_cfg_scale: float | None = None
    languages: list[EngineLanguageModel] = []
    active: bool = False
    supports_voice_modes: bool = False
    supports_style_clone: bool = False


# Forward-ref: ConfigResponse references EngineInfoModel.
ConfigResponse.model_rebuild()


# ---- synthesize ----

class SynthSpeakerModel(BaseModel):
    name: str = Field(..., min_length=1, max_length=64)
    # Voice id (filename stem). Empty is allowed for OmniVoice design/auto
    # modes, which carry no reference voice; clone-mode "voice required" is
    # enforced downstream by voice resolution.
    voice: str = Field("", max_length=256, description="Voice id; may be empty for OmniVoice design/auto")
    # OmniVoice only: "clone" | "design" | "auto". None for other engines.
    voice_mode: Literal["clone", "design", "auto"] | None = None
    # OmniVoice design-mode attribute prompt.
    instruct: str | None = None


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
    # Optional TTS engine override (e.g. "kokoro"). When omitted, the
    # server's active engine is used. Ignored if the engine name is not
    # registered.
    engine: str | None = None
    # Speed multiplier. Kokoro uses this directly; VibeVoice ignores it.
    speed: float | None = Field(default=None, ge=0.25, le=4.0)
    # --- Chatterbox Multilingual V3 only (other engines ignore) ---
    # Classifier-free guidance weight (0.0–1.0). Default 0.5.
    cfg_weight: float | None = Field(default=None, ge=0.0, le=2.0)
    # Voice expressiveness / exaggeration (0.0–2.0). Default 0.5.
    exaggeration: float | None = Field(default=None, ge=0.0, le=2.0)
    # BCP-47-ish short language code (e.g. "en", "fr", "ur", "zh"). When
    # omitted, Chatterbox uses the voice's `language` metadata or the
    # server's `chatterbox_default_language_id` setting.
    language_id: str | None = None
    # --- Qwen3-TTS CustomVoice only (other engines ignore) ---
    temperature: float | None = Field(default=None, ge=0.1, le=2.0)
    top_p: float | None = Field(default=None, ge=0.0, le=1.0)
    top_k: int | None = Field(default=None, ge=0, le=200)
    repetition_penalty: float | None = Field(default=None, ge=1.0, le=2.0)
    seed: int | None = Field(default=None, ge=0)


class SynthBase64Response(BaseModel):
    audio_b64: str
    sample_rate: int
    duration_sec: float
    inference_ms: int
    voice_id: str
