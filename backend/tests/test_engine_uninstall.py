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
