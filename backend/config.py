"""Application settings, sourced from env vars, .env file, and CLI overrides."""

from __future__ import annotations

from pathlib import Path
from typing import Literal

from pydantic_settings import BaseSettings, SettingsConfigDict

# Project root = backend/ directory (this file's parent)
BACKEND_ROOT = Path(__file__).resolve().parent


class Settings(BaseSettings):
    """Runtime settings for the multi-engine TTS backend."""

    model_config = SettingsConfigDict(
        env_file=str(BACKEND_ROOT / ".env"),
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    # Active TTS engine. "vibevoice" (default), "kokoro", or "chatterbox".
    # The user's last choice is persisted in backend/.last_engine and
    # overrides this on next start.
    default_engine: Literal["vibevoice", "kokoro", "chatterbox", "omnivoice", "voxcpm"] = "vibevoice"

    # Model
    # Default: the community-maintained mirror at vibevoice/VibeVoice-1.5B
    # (Microsoft's `microsoft/VibeVoice-1.5B` still works but isn't actively updated).
    model_id: str = "vibevoice/VibeVoice-1.5B"
    # Use "auto" to pick the best available device, or pin cuda/cpu/mps
    device: Literal["auto", "cuda", "cpu", "mps"] = "auto"

    # Kokoro language code. "a" = American English (default),
    # "b" = British English, "j" = Japanese (needs misaki[ja]),
    # "z" = Mandarin Chinese (needs misaki[zh]).
    kokoro_lang_code: Literal["a", "b", "j", "z"] = "a"

    # --- Chatterbox Multilingual V3 ---
    # HuggingFace model id. The Multilingual V3 checkpoint is selected by
    # passing t3_model="v3" at load time (handled in ChatterboxEngine).
    chatterbox_model_id: str = "ResembleAI/chatterbox"
    # Default language_id used when a voice has no language metadata.
    # Must be one of Chatterbox's 23 supported codes: ar, da, de, el, en,
    # es, fi, fr, he, hi, it, ja, ko, ms, nl, no, pl, pt, ru, sv, sw, tr, zh.
    chatterbox_default_language_id: str = "en"
    # Generation defaults (per Chatterbox README).
    chatterbox_default_cfg_weight: float = 0.5
    chatterbox_default_exaggeration: float = 0.5
    # PerTh watermarking. On by default per Resemble AI's responsible-AI
    # policy. Set to false in .env to disable.
    chatterbox_watermark: bool = True

    omnivoice_model_id: str = "k2-fsa/OmniVoice"
    omnivoice_num_step: int = 32

    voxcpm_model_id: str = "openbmb/VoxCPM2"
    # Diffusion inference timesteps (5 fast … 25 high quality). Default 10.
    voxcpm_inference_timesteps: int = 10

    # Server
    host: str = "0.0.0.0"
    port: int = 8880

    # Filesystem
    voices_dir: Path = BACKEND_ROOT / "voices"
    uploads_dir: Path = BACKEND_ROOT / "uploads"
    cache_dir: Path = BACKEND_ROOT / "cache"
    # Where HuggingFace model weights are cached. Defaults to
    # `<project>/backend/models/` so everything (code + data) lives in
    # the repo. Override with `MODELS_DIR` env var or this `.env` entry;
    # `HF_HOME` is also honored as a global override by the
    # huggingface_hub library itself.
    models_dir: Path = BACKEND_ROOT / "models"

    # Limits
    max_text_chars: int = 5000
    synth_timeout_s: int = 600

    # Generation defaults
    default_cfg_scale: float = 1.3

    # Cache
    cache_enabled: bool = True
    cache_max_entries: int = 500

    # Logging
    log_level: str = "info"


def get_settings() -> Settings:
    """Factory so tests can override."""
    return Settings()
