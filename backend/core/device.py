"""Device + dtype resolution."""

from __future__ import annotations

import logging

import torch

log = logging.getLogger(__name__)


def resolve_device(name: str) -> tuple[torch.device, torch.dtype, str]:
    """
    Resolve the requested device to (torch.device, dtype, attention_impl).

    Falls back to CPU on unsupported requests so the app never crashes on startup.
    """
    requested = name.lower()

    if requested == "auto":
        if torch.cuda.is_available():
            device = torch.device("cuda")
            dtype = torch.bfloat16 if torch.cuda.is_bf16_supported() else torch.float16
            return device, dtype, "sdpa"
        if getattr(torch.backends, "mps", None) is not None and torch.backends.mps.is_available():
            return torch.device("mps"), torch.float16, "sdpa"
        return torch.device("cpu"), torch.float32, "sdpa"

    if requested == "cuda":
        if not torch.cuda.is_available():
            log.warning("CUDA requested but not available; falling back to CPU.")
            return torch.device("cpu"), torch.float32, "sdpa"
        dtype = torch.bfloat16 if torch.cuda.is_bf16_supported() else torch.float16
        return torch.device("cuda"), dtype, "sdpa"

    if requested == "mps":
        if not (getattr(torch.backends, "mps", None) is not None and torch.backends.mps.is_available()):
            log.warning("MPS requested but not available; falling back to CPU.")
            return torch.device("cpu"), torch.float32, "sdpa"
        return torch.device("mps"), torch.float16, "sdpa"

    if requested == "cpu":
        return torch.device("cpu"), torch.float32, "sdpa"

    log.warning("Unknown device %r; falling back to CPU.", name)
    return torch.device("cpu"), torch.float32, "sdpa"
