"""Application settings, sourced from env vars, .env file, and CLI overrides."""

from __future__ import annotations

from pathlib import Path
from typing import Literal

from pydantic_settings import BaseSettings, SettingsConfigDict

# Project root = backend/ directory (this file's parent)
BACKEND_ROOT = Path(__file__).resolve().parent


class Settings(BaseSettings):
    """Runtime settings for the VibeVoice backend."""

    model_config = SettingsConfigDict(
        env_file=str(BACKEND_ROOT / ".env"),
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    # Model
    # Default: the community-maintained mirror at vibevoice/VibeVoice-1.5B
    # (Microsoft's `microsoft/VibeVoice-1.5B` still works but isn't actively updated).
    model_id: str = "vibevoice/VibeVoice-1.5B"
    # Use "auto" to pick the best available device, or pin cuda/cpu/mps
    device: Literal["auto", "cuda", "cpu", "mps"] = "auto"

    # Server
    host: str = "0.0.0.0"
    port: int = 8880

    # Filesystem
    voices_dir: Path = BACKEND_ROOT / "voices"
    uploads_dir: Path = BACKEND_ROOT / "uploads"
    cache_dir: Path = BACKEND_ROOT / "cache"

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
