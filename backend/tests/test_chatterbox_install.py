"""Tests for the Chatterbox install manager using an injected fake runner."""

import sys
import time
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT))

from backend.services.chatterbox_install import (  # noqa: E402
    ChatterboxInstaller,
    EngineEnvInstaller,
    _format_progress,
)


def _fake_runner(lines, rc):
    def run():
        for ln in lines:
            yield ln, None
        yield None, rc
    return run


def _wait(inst, timeout=5.0):
    deadline = time.time() + timeout
    while time.time() < deadline and inst.status()["state"] == "installing":
        time.sleep(0.02)


def test_initial_state_not_installed():
    inst = ChatterboxInstaller(runner=_fake_runner([], 0))
    assert inst.status()["state"] == "not_installed"


def test_install_success_accumulates_log():
    inst = ChatterboxInstaller(runner=_fake_runner(["a", "b"], 0))
    inst.start()
    _wait(inst)
    s = inst.status()
    assert s["state"] == "installed"
    assert s["returncode"] == 0
    assert s["log"] == ["a", "b"]


def test_install_failure_sets_error():
    inst = ChatterboxInstaller(runner=_fake_runner(["boom"], 1))
    inst.start()
    _wait(inst)
    s = inst.status()
    assert s["state"] == "error"
    assert s["returncode"] == 1


def test_start_is_idempotent_while_running():
    started = {"n": 0}
    def run():
        started["n"] += 1
        time.sleep(0.2)
        yield "x", None
        yield None, 0
    inst = ChatterboxInstaller(runner=run)
    inst.start()
    inst.start()  # second call while installing must NOT launch a second run
    _wait(inst)
    assert started["n"] == 1
    assert inst.status()["state"] == "installed"


def _make_client(installer):
    from fastapi import FastAPI
    from fastapi.testclient import TestClient
    from backend.api.engines import router
    app = FastAPI()
    app.include_router(router)
    app.state.engine_installers = {"chatterbox": installer}
    return TestClient(app)


def test_install_endpoint_rejects_non_chatterbox():
    client = _make_client(ChatterboxInstaller(runner=_fake_runner([], 0)))
    assert client.get("/api/engines/kokoro/install").status_code == 400
    assert client.post("/api/engines/kokoro/install").status_code == 400


def test_install_endpoint_status_and_start():
    inst = ChatterboxInstaller(runner=_fake_runner(["hello"], 0))
    client = _make_client(inst)
    assert client.get("/api/engines/chatterbox/install").json()["state"] == "not_installed"
    r = client.post("/api/engines/chatterbox/install")
    assert r.status_code == 200
    _wait(inst)
    s = client.get("/api/engines/chatterbox/install").json()
    assert s["state"] == "installed"
    assert "hello" in s["log"]


def test_format_progress_parses_pip_raw():
    assert _format_progress("Progress 524288000 of 1048576000") == "  downloading 50% (500.0 / 1000.0 MB)"
    assert _format_progress("Collecting torch") is None
    assert _format_progress("Progress 5 of 0") is None


def test_progress_lines_collapse_to_one_updating_line():
    runner = _fake_runner(
        [
            "Collecting torch",
            "Progress 262144000 of 1048576000",
            "Progress 524288000 of 1048576000",
            "Progress 1048576000 of 1048576000",
            "Successfully installed torch",
        ],
        0,
    )
    inst = ChatterboxInstaller(runner=runner)
    inst.start()
    _wait(inst)
    log = inst.status()["log"]
    prog = [ln for ln in log if ln.startswith("  downloading ")]
    assert len(prog) == 1  # collapsed into a single updating line
    assert prog[0] == "  downloading 100% (1000.0 / 1000.0 MB)"
    assert "Collecting torch" in log
    assert "Successfully installed torch" in log


def test_engine_env_installer_runs_given_subcommand():
    seen = {}
    def runner():
        seen["ran"] = True
        yield "line", None
        yield None, 0
    inst = EngineEnvInstaller("install-omnivoice", runner=runner)
    inst.start()
    _wait(inst)
    assert seen.get("ran") is True
    assert inst.status()["state"] == "installed"


def test_install_endpoint_supports_omnivoice():
    omni = EngineEnvInstaller("install-omnivoice", runner=_fake_runner(["hi"], 0))
    cb = ChatterboxInstaller(runner=_fake_runner([], 0))
    from fastapi import FastAPI
    from fastapi.testclient import TestClient
    from backend.api.engines import router
    app = FastAPI()
    app.include_router(router)
    app.state.engine_installers = {"chatterbox": cb, "omnivoice": omni}
    client = TestClient(app)
    assert client.get("/api/engines/omnivoice/install").json()["state"] == "not_installed"
    assert client.post("/api/engines/omnivoice/install").status_code == 200
    _wait(omni)
    assert "hi" in client.get("/api/engines/omnivoice/install").json()["log"]
    # Unknown / non-installable engine still 400s.
    assert client.get("/api/engines/kokoro/install").status_code == 400


def test_install_endpoint_supports_voxcpm():
    vx = EngineEnvInstaller("install-voxcpm", runner=_fake_runner(["hi"], 0))
    from fastapi import FastAPI
    from fastapi.testclient import TestClient
    from backend.api.engines import router
    app = FastAPI()
    app.include_router(router)
    app.state.engine_installers = {"voxcpm": vx}
    client = TestClient(app)
    assert client.get("/api/engines/voxcpm/install").json()["state"] == "not_installed"
    assert client.post("/api/engines/voxcpm/install").status_code == 200
    _wait(vx)
    assert "hi" in client.get("/api/engines/voxcpm/install").json()["log"]


def test_install_endpoint_supports_qwen():
    q = EngineEnvInstaller("install-qwen", runner=_fake_runner(["hi"], 0))
    from fastapi import FastAPI
    from fastapi.testclient import TestClient
    from backend.api.engines import router
    app = FastAPI()
    app.include_router(router)
    app.state.engine_installers = {"qwen": q}
    client = TestClient(app)
    assert client.get("/api/engines/qwen/install").json()["state"] == "not_installed"
    assert client.post("/api/engines/qwen/install").status_code == 200
    _wait(q)
    assert "hi" in client.get("/api/engines/qwen/install").json()["log"]
