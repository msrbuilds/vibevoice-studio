import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT))

from fastapi.testclient import TestClient  # noqa: E402

from backend.app import create_app  # noqa: E402


def test_engines_list_exposes_voice_mode_flags():
    client = TestClient(create_app())
    data = client.get("/api/engines").json()
    by_name = {e["name"]: e for e in data["engines"]}
    assert by_name["voxcpm"]["supports_voice_modes"] is True
    assert by_name["voxcpm"]["supports_style_clone"] is True
    assert by_name["omnivoice"]["supports_voice_modes"] is True
    assert by_name["omnivoice"]["supports_style_clone"] is False
    assert by_name["vibevoice"]["supports_voice_modes"] is False
    assert by_name["vibevoice"]["supports_style_clone"] is False


def test_engines_expose_style_prompt_flag():
    from fastapi.testclient import TestClient
    from backend.app import create_app
    client = TestClient(create_app())
    by_name = {e["name"]: e for e in client.get("/api/engines").json()["engines"]}
    assert by_name["qwen"]["supports_style_prompt"] is True
    assert by_name["vibevoice"]["supports_style_prompt"] is False
    assert by_name["voxcpm"]["supports_style_prompt"] is False
