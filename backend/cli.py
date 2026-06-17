"""CLI entrypoint: `python cli.py --device cuda --port 8880 …`."""

from __future__ import annotations

import argparse
import logging

import uvicorn

from .app import create_app
from .config import Settings

log = logging.getLogger(__name__)


def _parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(
        prog="vibevoice-backend",
        description="Local FastAPI server for microsoft/VibeVoice-1.5B",
    )
    p.add_argument("--model", help="HF model id or local path (overrides settings.model_id)")
    p.add_argument(
        "--device",
        choices=["auto", "cuda", "cpu", "mps"],
        help="Inference device (default: auto-detect)",
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
    if args.model is not None:
        overrides["model_id"] = args.model
    if args.device is not None:
        overrides["device"] = args.device
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
