import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT))

from backend.core.version import get_version  # noqa: E402


def test_get_version_reads_root_version_file():
    # The repo-root VERSION file is the single source of truth.
    expected = (REPO_ROOT / "VERSION").read_text(encoding="utf-8").strip()
    assert get_version() == expected
    # Must look like semver X.Y.Z.
    parts = get_version().split(".")
    assert len(parts) == 3 and all(p.isdigit() for p in parts)
