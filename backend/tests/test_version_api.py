import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT))

from fastapi.testclient import TestClient  # noqa: E402

from backend.app import create_app  # noqa: E402
from backend.core.version import get_version  # noqa: E402


def test_health_and_config_report_get_version():
    client = TestClient(create_app())
    v = get_version()
    assert client.get("/api/health").json()["version"] == v
    assert client.get("/api/config").json()["version"] == v
