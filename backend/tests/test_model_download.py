"""Tests for model-download cache detection, the ModelDownloader service,
and the /download API. Uses injected fakes — no network, no real weights."""

import sys
import time
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT))

import huggingface_hub  # noqa: E402

from backend.core import model_cache  # noqa: E402


def test_model_downloaded_true_when_snapshot_resolves(monkeypatch):
    monkeypatch.setattr(huggingface_hub, "snapshot_download", lambda *a, **k: "/cache/x")
    assert model_cache.model_downloaded("org/repo") is True


def test_model_downloaded_false_when_snapshot_raises(monkeypatch):
    def _boom(*a, **k):
        raise RuntimeError("not cached")
    monkeypatch.setattr(huggingface_hub, "snapshot_download", _boom)
    assert model_cache.model_downloaded("org/repo") is False


from backend.core.engines import Engine, EngineResult, EngineSynthRequest  # noqa: E402


class _StubEngine(Engine):
    """Minimal concrete Engine for exercising base-class behavior."""

    name = "stub"

    def __init__(self, downloaded=True):
        self._downloaded = downloaded

    def load(self): ...
    def unload(self): ...
    def is_loaded(self): return False
    def synthesize(self, req): raise NotImplementedError
    def sample_rate(self): return 24000
    def max_speakers(self): return 1
    def supports_voice_cloning(self): return False
    def default_cfg_scale(self): return None
    def available_voices(self): return []
    def downloaded(self): return self._downloaded


def test_engine_info_includes_downloaded_default_true():
    info = _StubEngine().info()
    assert info["downloaded"] is True


def test_engine_info_reflects_overridden_downloaded():
    assert _StubEngine(downloaded=False).info()["downloaded"] is False


import pytest  # noqa: E402

from backend.services.model_download import ModelDownloader, Progress  # noqa: E402


def _wait(dl, timeout=5.0):
    deadline = time.time() + timeout
    while time.time() < deadline and dl.status()["state"] == "downloading":
        time.sleep(0.02)


def test_download_success_sets_done_and_percent():
    def runner(repo_id, prog):
        prog.set_total(100)
        prog.add_bytes(50, "model.safetensors")
        prog.add_bytes(50, "model.safetensors")
    dl = ModelDownloader(runner=runner)
    dl.start("vibevoice")
    _wait(dl)
    s = dl.status()
    assert s["state"] == "done"
    assert s["returncode"] == 0
    assert s["engine"] == "vibevoice"
    assert s["downloaded_bytes"] == 100
    assert s["percent"] == 100.0


def test_download_error_sets_error_state():
    def runner(repo_id, prog):
        raise RuntimeError("network down")
    dl = ModelDownloader(runner=runner)
    dl.start("kokoro")
    _wait(dl)
    s = dl.status()
    assert s["state"] == "error"
    assert s["returncode"] == -1
    assert "network down" in s["error"]


def test_start_rejects_non_downloadable_engine():
    dl = ModelDownloader(runner=lambda r, p: None)
    with pytest.raises(ValueError):
        dl.start("chatterbox")


def test_start_coalesces_while_downloading():
    started = {"n": 0}
    def runner(repo_id, prog):
        started["n"] += 1
        time.sleep(0.2)
    dl = ModelDownloader(runner=runner)
    dl.start("vibevoice")
    dl.start("vibevoice")  # must NOT launch a second download
    _wait(dl)
    assert started["n"] == 1
    assert dl.status()["state"] == "done"


def test_speed_and_eta_from_injected_clock():
    seq = iter([10.0, 11.0])  # two add_bytes calls -> two timestamped samples
    dl = ModelDownloader(runner=lambda r, p: None, clock=lambda: next(seq))
    prog = Progress(dl)
    prog.set_total(800)
    prog.add_bytes(200, "f")  # t=10, total dl=200
    prog.add_bytes(200, "f")  # t=11, total dl=400
    s = dl.status()
    assert s["downloaded_bytes"] == 400
    assert s["percent"] == 50.0
    assert s["speed_bps"] == 200.0           # (400-200)/(11-10)
    assert s["eta_sec"] == 2.0               # remaining 400 / 200 bps
