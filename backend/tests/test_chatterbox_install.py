"""Tests for the Chatterbox install manager using an injected fake runner."""

import sys
import time
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT))

from backend.services.chatterbox_install import ChatterboxInstaller  # noqa: E402


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
