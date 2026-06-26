"""Stdlib-only environment detection for the Voice Studio launcher.

Imported by ``studio.py`` BEFORE any venv exists, so it must not import
any third-party package.
"""

from __future__ import annotations

import re
import shutil
import subprocess

CUDA_TAG_TO_INDEX: dict[str, str] = {
    "cu124": "https://download.pytorch.org/whl/cu124",
    "cu121": "https://download.pytorch.org/whl/cu121",
    "cu118": "https://download.pytorch.org/whl/cu118",
}


def parse_nvidia_smi_cuda_version(text: str) -> str | None:
    """Extract the ``CUDA Version: X.Y`` field from nvidia-smi output."""
    m = re.search(r"CUDA Version:\s*([0-9]+\.[0-9]+)", text)
    return m.group(1) if m else None


def cuda_version_to_tag(version: str | None) -> str | None:
    """Map a CUDA runtime version (e.g. '12.4') to a PyTorch wheel tag."""
    if not version:
        return None
    try:
        major, minor = (int(p) for p in version.split(".")[:2])
    except ValueError:
        return None
    if major >= 12:
        return "cu124" if minor >= 4 else "cu121"
    if major == 11:
        return "cu118"
    return None


def torch_index_url(tag: str | None) -> str | None:
    """Map a wheel tag to a ``--index-url``; None means the default wheel."""
    if tag in (None, "cpu", "mps"):
        return None
    return CUDA_TAG_TO_INDEX.get(tag)


def _run_nvidia_smi() -> str | None:
    if shutil.which("nvidia-smi") is None:
        return None
    try:
        out = subprocess.run(
            ["nvidia-smi"], capture_output=True, text=True, timeout=15
        )
    except (OSError, subprocess.SubprocessError):
        return None
    return out.stdout if out.returncode == 0 else None


def detect_cuda_tag(runner=None) -> str | None:
    """Detect the best CUDA wheel tag. ``runner`` is injectable for tests."""
    run = runner or _run_nvidia_smi
    text = run()
    if text is None:
        return None
    return cuda_version_to_tag(parse_nvidia_smi_cuda_version(text))
