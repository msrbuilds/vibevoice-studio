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


def test_start_rejects_other_engine_while_downloading():
    def runner(repo_id, prog):
        time.sleep(0.2)
    dl = ModelDownloader(runner=runner)
    dl.start("vibevoice")
    with pytest.raises(ValueError):
        dl.start("kokoro")  # different engine while one is in flight
    _wait(dl)
    assert dl.status()["engine"] == "vibevoice"


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


def test_speed_window_includes_start_anchor():
    # start() seeds an anchor sample (t_start, 0). Mirror that here, then
    # report bytes, so the speed/ETA window is computed across the anchor —
    # the path a real download takes — without spawning a thread.
    seq = iter([0.0, 1.0, 2.0])
    dl = ModelDownloader(runner=lambda r, p: None, clock=lambda: next(seq))
    dl._samples.append((dl._clock(), 0))  # anchor at t=0, as start() does
    prog = Progress(dl)
    prog.set_total(800)
    prog.add_bytes(200, "f")  # t=1, total dl=200
    prog.add_bytes(200, "f")  # t=2, total dl=400
    s = dl.status()
    assert s["downloaded_bytes"] == 400
    assert s["speed_bps"] == 200.0   # (400-0)/(2-0), window spans the anchor
    assert s["eta_sec"] == 2.0       # remaining 400 / 200 bps



def _make_client(downloader):
    from fastapi import FastAPI
    from fastapi.testclient import TestClient
    from backend.api.engines import router
    from backend.api.deps import get_model_downloader

    app = FastAPI()
    app.include_router(router)
    app.state.model_downloader = downloader
    app.dependency_overrides[get_model_downloader] = lambda: downloader
    return TestClient(app)


def test_download_endpoint_rejects_non_downloadable():
    client = _make_client(ModelDownloader(runner=lambda r, p: None))
    assert client.get("/api/engines/chatterbox/download").status_code == 400
    assert client.post("/api/engines/chatterbox/download").status_code == 400


def test_download_endpoint_start_and_status():
    def runner(repo_id, prog):
        prog.set_total(10)
        prog.add_bytes(10, "f")
    dl = ModelDownloader(runner=runner)
    client = _make_client(dl)

    assert client.get("/api/engines/vibevoice/download").json()["state"] == "idle"
    r = client.post("/api/engines/vibevoice/download")
    assert r.status_code == 200
    _wait(dl)
    s = client.get("/api/engines/vibevoice/download").json()
    assert s["state"] == "done"
    assert s["downloaded_bytes"] == 10
    assert s["percent"] == 100.0


def test_start_accepts_omnivoice():
    captured = {}
    def runner(repo_id, prog):
        captured["repo_id"] = repo_id
    dl = ModelDownloader(runner=runner)
    dl.start("omnivoice")
    _wait(dl)
    s = dl.status()
    assert s["engine"] == "omnivoice"
    assert s["state"] == "done"
    assert captured["repo_id"] == "k2-fsa/OmniVoice"


def test_download_endpoint_accepts_omnivoice():
    def runner(repo_id, prog):
        prog.set_total(10)
        prog.add_bytes(10, "f")
    dl = ModelDownloader(runner=runner)
    client = _make_client(dl)
    assert client.get("/api/engines/omnivoice/download").json()["state"] == "idle"
    assert client.post("/api/engines/omnivoice/download").status_code == 200
    _wait(dl)
    assert client.get("/api/engines/omnivoice/download").json()["state"] == "done"
