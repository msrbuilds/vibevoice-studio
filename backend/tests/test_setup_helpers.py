"""Unit tests for the Voice Studio setup/launch pure helpers."""

import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT))

from tools import envdetect  # noqa: E402

_SAMPLE_SMI = """
+-----------------------------------------------------------------------------+
| NVIDIA-SMI 552.22       Driver Version: 552.22       CUDA Version: 12.4      |
|-------------------------------+----------------------+----------------------+
"""


def test_parse_cuda_version_found():
    assert envdetect.parse_nvidia_smi_cuda_version(_SAMPLE_SMI) == "12.4"


def test_parse_cuda_version_missing():
    assert envdetect.parse_nvidia_smi_cuda_version("no cuda here") is None


def test_cuda_version_to_tag():
    assert envdetect.cuda_version_to_tag("12.4") == "cu124"
    assert envdetect.cuda_version_to_tag("12.6") == "cu124"
    assert envdetect.cuda_version_to_tag("12.1") == "cu121"
    assert envdetect.cuda_version_to_tag("12.0") == "cu121"
    assert envdetect.cuda_version_to_tag("11.8") == "cu118"
    assert envdetect.cuda_version_to_tag("10.2") is None
    assert envdetect.cuda_version_to_tag(None) is None


def test_torch_index_url():
    assert envdetect.torch_index_url("cu124") == "https://download.pytorch.org/whl/cu124"
    assert envdetect.torch_index_url("cu118") == "https://download.pytorch.org/whl/cu118"
    assert envdetect.torch_index_url(None) is None
    assert envdetect.torch_index_url("cpu") is None
    assert envdetect.torch_index_url("mps") is None


def test_detect_cuda_tag_with_injected_runner():
    assert envdetect.detect_cuda_tag(runner=lambda: _SAMPLE_SMI) == "cu124"
    assert envdetect.detect_cuda_tag(runner=lambda: None) is None


from backend.scripts import download_models as dm  # noqa: E402


def test_parse_model_selection_basic():
    assert dm.parse_model_selection("kokoro,chatterbox") == ["kokoro", "chatterbox"]


def test_parse_model_selection_dedupes_and_lowercases():
    assert dm.parse_model_selection("Kokoro, kokoro , VIBEVOICE") == ["kokoro", "vibevoice"]


def test_parse_model_selection_rejects_unknown():
    import pytest
    with pytest.raises(ValueError):
        dm.parse_model_selection("kokoro,bogus")


def test_catalog_has_expected_engines():
    assert set(dm.MODEL_CATALOG) == {"vibevoice", "kokoro", "chatterbox"}
    assert dm.MODEL_CATALOG["kokoro"]["repo_id"] == "hexgrad/Kokoro-82M"


def test_mount_frontend_serves_index_when_dist_present(tmp_path):
    from fastapi import FastAPI
    from fastapi.testclient import TestClient
    from backend.app import _mount_frontend

    dist = tmp_path / "dist"
    dist.mkdir()
    (dist / "index.html").write_text("<html>voice studio</html>", encoding="utf-8")

    app = FastAPI()

    @app.get("/api/health")
    def health():
        return {"status": "ok"}

    _mount_frontend(app, dist)
    client = TestClient(app)

    assert client.get("/api/health").json() == {"status": "ok"}
    root = client.get("/")
    assert root.status_code == 200
    assert "voice studio" in root.text


def test_mount_frontend_noop_when_dist_absent(tmp_path):
    from fastapi import FastAPI
    from fastapi.testclient import TestClient
    from backend.app import _mount_frontend

    app = FastAPI()

    @app.get("/api/health")
    def health():
        return {"status": "ok"}

    _mount_frontend(app, tmp_path / "missing-dist")
    client = TestClient(app)

    assert client.get("/api/health").json() == {"status": "ok"}
    assert client.get("/").status_code == 404


import studio  # noqa: E402


def test_venv_python_path_shape():
    repo = Path("/repo")
    p = studio.venv_python(repo)
    # Either Scripts/python.exe (Windows) or bin/python (POSIX)
    assert p.name in ("python.exe", "python")
    assert "venv" in p.parts


def test_build_backend_cmd_forwards_passthrough():
    cmd = studio.build_backend_cmd(Path("/repo/backend/venv/bin/python"),
                                   ["--device", "cuda", "--port", "9000"])
    assert cmd[:3] == ["/repo/backend/venv/bin/python", "-m", "backend.cli"]
    assert cmd[-4:] == ["--device", "cuda", "--port", "9000"]


def test_chatterbox_venv_python_path_shape():
    repo = Path("/repo")
    p = studio.chatterbox_venv_python(repo)
    assert p.name in ("python.exe", "python")
    assert "venv-chatterbox" in p.parts


def test_install_chatterbox_subcommand_success(monkeypatch):
    calls = {"n": 0}
    def _fake():
        calls["n"] += 1
        return True
    monkeypatch.setattr(studio, "_ensure_chatterbox_env", _fake)
    assert studio.main(["install-chatterbox"]) == 0
    assert calls["n"] == 1


def test_install_chatterbox_subcommand_failure(monkeypatch):
    monkeypatch.setattr(studio, "_ensure_chatterbox_env", lambda: False)
    assert studio.main(["install-chatterbox"]) == 1
