"""CLI entrypoint: `python -m backend.cli --engine kokoro --device cuda …`."""

from __future__ import annotations

# IMPORTANT: import order matters. Configure the HF cache BEFORE any
# import that might pull in transformers / kokoro / huggingface_hub,
# so the cache directory is set before the first download attempt.
import sys
from pathlib import Path as _Path

# CLI flag defaults must be parsed here without depending on Settings
# (which would in turn import pydantic). Define them inline.
_DEFAULT_MODELS_DIR = (
    _Path(__file__).resolve().parent / "models"
)

# Best-effort: honor an explicit --models-dir flag from argv before
# any heavy import. Real parsing happens below.
_pre_models = _Path(__file__).resolve().parent / "models"
for _i, _a in enumerate(sys.argv):
    if _a == "--models-dir" and _i + 1 < len(sys.argv):
        _pre_models = _Path(sys.argv[_i + 1]).expanduser().resolve()
        break
    if _a.startswith("--models-dir="):
        _pre_models = _Path(_a.split("=", 1)[1]).expanduser().resolve()
        break

from .core.hf_paths import configure_hf_cache as _configure_hf_cache
_configure_hf_cache(_pre_models)

import argparse
import logging

import uvicorn

from .app import create_app
from .config import Settings

log = logging.getLogger(__name__)


def _parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(
        prog="voice-studio",
        description="Voice Studio by MSR — local multi-engine TTS server",
    )
    p.add_argument(
        "--engine",
        choices=["vibevoice", "kokoro", "chatterbox", "omnivoice"],
        help="TTS engine to activate on startup. Persists across restarts.",
    )
    p.add_argument("--model", help="HF model id or local path (overrides settings.model_id, VibeVoice only)")
    p.add_argument(
        "--device",
        choices=["auto", "cuda", "cpu", "mps"],
        help="Inference device (default: auto-detect)",
    )
    p.add_argument(
        "--kokoro-lang",
        choices=["a", "b", "j", "z"],
        help="Kokoro lang_code (a=American English, b=British, j=Japanese, z=Mandarin)",
    )
    p.add_argument(
        "--chatterbox-lang",
        help="Default Chatterbox language_id (e.g. en, fr, ur, zh, ja). "
             "Used when a voice has no language metadata. "
             "Must be one of Chatterbox's 23 supported codes.",
    )
    p.add_argument(
        "--no-chatterbox-watermark",
        action="store_true",
        help="Disable Chatterbox's built-in Perth watermark (off by default)",
    )
    p.add_argument(
        "--models-dir",
        help="Where HuggingFace model weights are cached (default: backend/models/). "
             "Override with HF_HOME env var to bypass this flag.",
    )
    p.add_argument("--host", help="Bind host (default: 0.0.0.0)")
    p.add_argument("--port", type=int, help="Bind port (default: 8880)")
    p.add_argument("--voices-dir", help="Directory of built-in voice .wav files")
    p.add_argument("--uploads-dir", help="Directory to store user-uploaded voices")
    p.add_argument("--log-level", default=None, help="uvicorn log level (debug/info/warning/error)")
    p.add_argument("--reload", action="store_true", help="Enable autoreload (dev only)")
    return p.parse_args()


def main() -> None:
    args = _parse_args()
    overrides: dict = {}
    if args.engine is not None:
        overrides["default_engine"] = args.engine
    if args.model is not None:
        overrides["model_id"] = args.model
    if args.device is not None:
        overrides["device"] = args.device
    if args.kokoro_lang is not None:
        overrides["kokoro_lang_code"] = args.kokoro_lang
    if args.chatterbox_lang is not None:
        overrides["chatterbox_default_language_id"] = args.chatterbox_lang
    if args.no_chatterbox_watermark:
        overrides["chatterbox_watermark"] = False
    if args.host is not None:
        overrides["host"] = args.host
    if args.port is not None:
        overrides["port"] = args.port
    if args.voices_dir is not None:
        overrides["voices_dir"] = args.voices_dir
    if args.uploads_dir is not None:
        overrides["uploads_dir"] = args.uploads_dir
    if args.log_level is not None:
        overrides["log_level"] = args.log_level

    settings = Settings(**overrides)
    app = create_app(settings)

    uvicorn.run(
        app,
        host=settings.host,
        port=settings.port,
        log_level=settings.log_level,
        reload=args.reload,
    )


if __name__ == "__main__":
    main()
