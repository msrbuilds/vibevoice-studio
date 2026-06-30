"""Single source of truth for the application version.

Reads the repo-root VERSION file (the same string GitHub release tags use).
Cached after first read; falls back to "0.0.0" if the file is missing so the
app never crashes on a malformed checkout.
"""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parents[2]  # backend/core/.. -> repo root
_FALLBACK = "0.0.0"


@lru_cache(maxsize=1)
def get_version() -> str:
    try:
        text = (_REPO_ROOT / "VERSION").read_text(encoding="utf-8").strip()
    except OSError:
        return _FALLBACK
    return text or _FALLBACK
