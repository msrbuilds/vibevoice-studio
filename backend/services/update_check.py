"""GitHub-release update detection.

Pure helpers (`parse_semver`, `is_newer`, `build_snapshot`) are unit-tested in
isolation. `UpdateChecker` compares the local version against the latest GitHub
release and caches the result. The fetcher is injectable so tests never hit the
network. All failures are swallowed into the snapshot's `error` field — checking
for updates must never crash or block the app.
"""

from __future__ import annotations

import json
import logging
import re
import threading
import time
import urllib.request
from typing import Callable, Optional

log = logging.getLogger(__name__)

_REPO = "msrbuilds/voice-studio"
_API_URL = f"https://api.github.com/repos/{_REPO}/releases/latest"
_TIMEOUT_SEC = 8
# Re-check at most this often unless force=True (avoids hammering the API).
_CACHE_TTL_SEC = 600

_SEMVER_RE = re.compile(r"^v?(\d+)\.(\d+)\.(\d+)(?:[-+].*)?$")

Fetcher = Callable[[], dict]


def parse_semver(s: str) -> Optional[tuple[int, int, int, int]]:
    """(major, minor, patch, release_rank) or None if unparseable.

    release_rank is 1 for a final release and 0 for a pre-release (anything with
    a '-' suffix), so a release sorts above the same X.Y.Z pre-release.
    """
    m = _SEMVER_RE.match((s or "").strip())
    if not m:
        return None
    is_pre = "-" in (s or "")
    return (int(m.group(1)), int(m.group(2)), int(m.group(3)), 0 if is_pre else 1)


def is_newer(latest: str, current: str) -> bool:
    """True iff `latest` is a strictly newer semver than `current`. Fail-safe:
    any unparseable input returns False."""
    pl, pc = parse_semver(latest), parse_semver(current)
    if pl is None or pc is None:
        return False
    return pl > pc


def build_snapshot(
    payload: Optional[dict],
    *,
    current: str,
    checked_at: float,
    error: Optional[str] = None,
) -> dict:
    """Normalize a GitHub release payload into the API snapshot dict."""
    if error is not None or not payload:
        return {
            "current": current,
            "latest": None,
            "update_available": False,
            "html_url": None,
            "published_at": None,
            "body": None,
            "checked_at": checked_at,
            "error": error,
        }
    tag = str(payload.get("tag_name") or "")
    return {
        "current": current,
        "latest": tag.removeprefix("v") or None,
        "update_available": is_newer(tag, current),
        "html_url": payload.get("html_url"),
        "published_at": payload.get("published_at"),
        "body": payload.get("body"),
        "checked_at": checked_at,
        "error": None,
    }


def _default_fetcher() -> dict:
    """GET the latest release from GitHub (unauthenticated). Raises on failure."""
    req = urllib.request.Request(
        _API_URL,
        headers={
            "Accept": "application/vnd.github+json",
            "User-Agent": "VoiceStudio-Updater",
        },
    )
    with urllib.request.urlopen(req, timeout=_TIMEOUT_SEC) as resp:  # noqa: S310
        return json.loads(resp.read().decode("utf-8"))


class UpdateChecker:
    """Caches the latest-release comparison. Thread-safe; failure-tolerant."""

    def __init__(self, current: str, *, fetcher: Fetcher | None = None) -> None:
        self._current = current
        self._fetcher = fetcher or _default_fetcher
        self._lock = threading.Lock()
        self._snapshot: dict | None = None

    def snapshot(self) -> dict:
        """Last result, or an 'unchecked' default (never None, never raises)."""
        with self._lock:
            if self._snapshot is not None:
                return dict(self._snapshot)
        return build_snapshot(
            None, current=self._current, checked_at=0.0, error="not checked yet"
        )

    def check(self, *, force: bool = False) -> dict:
        """Return a fresh snapshot, fetching from GitHub unless a recent cached
        result exists (and force is False)."""
        now = time.time()
        with self._lock:
            cached = self._snapshot
            if (
                not force
                and cached is not None
                and cached.get("error") is None
                and now - float(cached.get("checked_at", 0.0)) < _CACHE_TTL_SEC
            ):
                return dict(cached)
        try:
            payload = self._fetcher()
            snap = build_snapshot(payload, current=self._current, checked_at=now)
        except Exception as exc:  # noqa: BLE001
            log.info("Update check failed: %s", exc)
            snap = build_snapshot(
                None, current=self._current, checked_at=now, error=str(exc)
            )
        with self._lock:
            self._snapshot = snap
        return dict(snap)

    def refresh_async(self) -> None:
        """Kick off a background check; swallow all errors. Used at startup."""
        threading.Thread(
            target=lambda: self.check(force=True), daemon=True
        ).start()
