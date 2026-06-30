"""Per-engine language metadata for the UI language dropdown."""
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT))

from backend.core.engines.chatterbox_engine import ChatterboxEngine  # noqa: E402
from backend.core.engines.kokoro_engine import KokoroEngine  # noqa: E402


def test_chatterbox_languages_cover_supported_ids():
    eng = ChatterboxEngine(worker_python=Path("x"), worker_script=Path("y"))
    langs = eng.languages()
    codes = {l["code"] for l in langs}
    # All 23 Chatterbox language ids are present, each with a non-empty label.
    assert "en" in codes and "sw" in codes and "zh" in codes
    assert len(codes) == 23
    assert all(l["label"] for l in langs)


def test_kokoro_languages_are_its_voice_groups():
    eng = KokoroEngine()
    codes = {l["code"] for l in eng.languages()}
    # Kokoro language == the distinct languages of its built-in voice catalog.
    assert codes == {"en-us", "en-gb", "ja", "zh"}


def test_languages_in_info_dict():
    eng = KokoroEngine()
    assert "languages" in eng.info()
    assert isinstance(eng.info()["languages"], list)


def test_engines_endpoint_includes_languages(monkeypatch):
    # The /api/engines payload must carry the languages list per engine.
    from fastapi.testclient import TestClient
    from backend.app import create_app

    app = create_app()
    with TestClient(app) as client:
        resp = client.get("/api/engines")
        assert resp.status_code == 200
        engines = resp.json()["engines"] if isinstance(resp.json(), dict) else resp.json()
        by_name = {e["name"]: e for e in engines}
        assert "languages" in by_name["kokoro"]
        assert {l["code"] for l in by_name["kokoro"]["languages"]} == {"en-us", "en-gb", "ja", "zh"}
