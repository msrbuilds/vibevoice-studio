"""Tests for engine uninstall / delete-weights services + Chatterbox downloaded()."""

import sys
import time
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT))


def test_chatterbox_downloaded_probes_cache(monkeypatch):
    from backend.core.engines import chatterbox_engine as ce

    eng = ce.ChatterboxEngine()
    # Patch the model_cache probe the override delegates to.
    import backend.core.model_cache as mc
    monkeypatch.setattr(mc, "model_downloaded", lambda repo_id: repo_id == "ResembleAI/chatterbox")
    assert eng.downloaded() is True

    monkeypatch.setattr(mc, "model_downloaded", lambda repo_id: False)
    assert eng.downloaded() is False


# ---------------------------------------------------------------------------
# ModelDeleter
# ---------------------------------------------------------------------------

def _wait_deleter(d, timeout=5.0):
    deadline = time.time() + timeout
    while time.time() < deadline and d.status()["state"] == "deleting":
        time.sleep(0.02)


def test_model_deleter_initial_idle():
    from backend.services.model_delete import ModelDeleter
    d = ModelDeleter(em=None, repo_dir_resolver=lambda r: None, remover=lambda p: None)
    assert d.status()["state"] == "idle"


def test_model_deleter_deletes_existing_dir(tmp_path):
    from backend.services.model_delete import ModelDeleter
    target = tmp_path / "models--vibevoice--VibeVoice-1.5B"
    target.mkdir()
    removed = []
    d = ModelDeleter(
        em=None,
        repo_dir_resolver=lambda repo_id: target,
        remover=lambda p: removed.append(p),
    )
    d.start("vibevoice")
    _wait_deleter(d)
    s = d.status()
    assert s["state"] == "deleted"
    assert removed == [target]
    assert s["error"] is None


def test_model_deleter_missing_dir_is_idempotent():
    from backend.services.model_delete import ModelDeleter
    removed = []
    d = ModelDeleter(
        em=None,
        repo_dir_resolver=lambda repo_id: None,  # not cached
        remover=lambda p: removed.append(p),
    )
    d.start("kokoro")
    _wait_deleter(d)
    assert d.status()["state"] == "deleted"
    assert removed == []  # nothing to remove


def test_model_deleter_error_state():
    from backend.services.model_delete import ModelDeleter

    def boom(p):
        raise OSError("permission denied")

    d = ModelDeleter(
        em=None,
        repo_dir_resolver=lambda repo_id: Path("/fake/dir"),
        remover=boom,
    )
    d.start("omnivoice")
    _wait_deleter(d)
    s = d.status()
    assert s["state"] == "error"
    assert "permission denied" in (s["error"] or "")


def test_model_deleter_rejects_unknown_engine():
    from backend.services.model_delete import ModelDeleter
    import pytest
    d = ModelDeleter(em=None, repo_dir_resolver=lambda r: None, remover=lambda p: None)
    with pytest.raises(ValueError):
        d.start("not-an-engine")


def test_model_deleter_rejects_concurrent_different_engine():
    from backend.services.model_delete import ModelDeleter
    import pytest, threading

    gate = threading.Event()

    def slow_remove(p):
        gate.wait(2.0)  # hold the first delete open

    d = ModelDeleter(
        em=None,
        repo_dir_resolver=lambda r: Path("/x"),
        remover=slow_remove,
    )
    d.start("vibevoice")
    # While vibevoice delete is in flight, a different engine must be rejected.
    try:
        with pytest.raises(ValueError):
            d.start("kokoro")
        # Same engine coalesces (no raise).
        d.start("vibevoice")
    finally:
        gate.set()
    _wait_deleter(d)
    assert d.status()["engine"] == "vibevoice"


def test_model_deleter_unloads_loaded_engine():
    from backend.services.model_delete import ModelDeleter

    class FakeEngine:
        def __init__(self):
            self.unloaded = False
        def is_loaded(self):
            return True
        def unload(self):
            self.unloaded = True

    fake = FakeEngine()

    class FakeEM:
        def get_engine(self, name):
            return fake

    d = ModelDeleter(
        em=FakeEM(),
        repo_dir_resolver=lambda r: None,
        remover=lambda p: None,
    )
    d.start("vibevoice")
    _wait_deleter(d)
    assert fake.unloaded is True


# ---------------------------------------------------------------------------
# EngineEnvUninstaller
# ---------------------------------------------------------------------------

def _wait_uninstaller(u, timeout=5.0):
    deadline = time.time() + timeout
    while time.time() < deadline and u.status()["state"] == "uninstalling":
        time.sleep(0.02)


def test_uninstaller_initial_idle():
    from backend.services.engine_uninstall import EngineEnvUninstaller
    u = EngineEnvUninstaller("chatterbox", em=None, venv_dir=Path("/nope"), remover=lambda p: None)
    assert u.status()["state"] == "idle"


def test_uninstaller_removes_existing_venv(tmp_path):
    from backend.services.engine_uninstall import EngineEnvUninstaller
    venv = tmp_path / "venv-chatterbox"
    venv.mkdir()
    removed = []
    u = EngineEnvUninstaller(
        "chatterbox", em=None, venv_dir=venv, remover=lambda p: removed.append(p)
    )
    u.start()
    _wait_uninstaller(u)
    s = u.status()
    assert s["state"] == "uninstalled"
    assert removed == [venv]


def test_uninstaller_missing_venv_is_idempotent(tmp_path):
    from backend.services.engine_uninstall import EngineEnvUninstaller
    removed = []
    u = EngineEnvUninstaller(
        "omnivoice", em=None, venv_dir=tmp_path / "absent", remover=lambda p: removed.append(p)
    )
    u.start()
    _wait_uninstaller(u)
    assert u.status()["state"] == "uninstalled"
    assert removed == []


def test_uninstaller_error_state(tmp_path):
    from backend.services.engine_uninstall import EngineEnvUninstaller
    venv = tmp_path / "venv-chatterbox"
    venv.mkdir()

    def boom(p):
        raise OSError("file in use")

    u = EngineEnvUninstaller("chatterbox", em=None, venv_dir=venv, remover=boom)
    u.start()
    _wait_uninstaller(u)
    s = u.status()
    assert s["state"] == "error"
    assert "file in use" in (s["error"] or "")


def test_uninstaller_unloads_loaded_engine(tmp_path):
    from backend.services.engine_uninstall import EngineEnvUninstaller

    class FakeEngine:
        def __init__(self):
            self.unloaded = False
        def is_loaded(self):
            return True
        def unload(self):
            self.unloaded = True

    fake = FakeEngine()

    class FakeEM:
        def get_engine(self, name):
            return fake

    venv = tmp_path / "venv-chatterbox"
    venv.mkdir()
    u = EngineEnvUninstaller("chatterbox", em=FakeEM(), venv_dir=venv, remover=lambda p: None)
    u.start()
    _wait_uninstaller(u)
    assert fake.unloaded is True


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------

def _make_app(deleter=None, uninstallers=None):
    from fastapi import FastAPI
    from backend.api.engines import router
    app = FastAPI()
    app.include_router(router)
    if deleter is not None:
        app.state.model_deleter = deleter
    if uninstallers is not None:
        app.state.engine_uninstallers = uninstallers
    return app


def test_delete_weights_endpoints():
    from fastapi.testclient import TestClient
    from backend.services.model_delete import ModelDeleter
    d = ModelDeleter(em=None, repo_dir_resolver=lambda r: None, remover=lambda p: None)
    client = TestClient(_make_app(deleter=d))

    assert client.get("/api/engines/vibevoice/delete-weights").json()["state"] == "idle"
    r = client.post("/api/engines/vibevoice/delete-weights")
    assert r.status_code == 200
    _wait_deleter(d)
    body = client.get("/api/engines/vibevoice/delete-weights").json()
    assert body["state"] == "deleted"
    assert body["engine"] == "vibevoice"


def test_delete_weights_rejects_unknown_engine():
    from fastapi.testclient import TestClient
    from backend.services.model_delete import ModelDeleter
    d = ModelDeleter(em=None, repo_dir_resolver=lambda r: None, remover=lambda p: None)
    client = TestClient(_make_app(deleter=d))
    assert client.get("/api/engines/bogus/delete-weights").status_code == 400
    assert client.post("/api/engines/bogus/delete-weights").status_code == 400


def test_uninstall_endpoints(tmp_path):
    from fastapi.testclient import TestClient
    from backend.services.engine_uninstall import EngineEnvUninstaller
    venv = tmp_path / "venv-chatterbox"
    venv.mkdir()
    u = EngineEnvUninstaller("chatterbox", em=None, venv_dir=venv, remover=lambda p: None)
    client = TestClient(_make_app(uninstallers={"chatterbox": u}))

    assert client.get("/api/engines/chatterbox/uninstall").json()["state"] == "idle"
    assert client.post("/api/engines/chatterbox/uninstall").status_code == 200
    _wait_uninstaller(u)
    assert client.get("/api/engines/chatterbox/uninstall").json()["state"] == "uninstalled"


def test_uninstall_rejects_non_isolated_engine(tmp_path):
    from fastapi.testclient import TestClient
    from backend.services.engine_uninstall import EngineEnvUninstaller
    u = EngineEnvUninstaller("chatterbox", em=None, venv_dir=tmp_path / "v", remover=lambda p: None)
    client = TestClient(_make_app(uninstallers={"chatterbox": u}))
    # vibevoice has no isolated env → 400
    assert client.get("/api/engines/vibevoice/uninstall").status_code == 400
    assert client.post("/api/engines/vibevoice/uninstall").status_code == 400
